"""The engine: statuses, propagation, run-time diagnostics and the verdict (#120, #144)."""

from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner import (
    Fail,
    Outcome,
    Pass,
    Skip,
    conclusion,
    engine,
    evidence,
    strategy,
    sub_conclusion,
)
from jpipe_runner.artifacts import UNREACHABLE_ARTIFACT
from jpipe_runner.diagnostics import Severity
from jpipe_runner.engine import (
    DECLARED_VALUE_MISSING,
    STEP_RAISED,
    UNDECLARED_VALUE,
    RunResult,
    Status,
    Verdict,
    run,
)
from jpipe_runner.model import Justification
from jpipe_runner.outcomes import NOT_AN_OUTCOME
from jpipe_runner.steps import StepRegistry, step_of
from jpipe_runner.validation import RuleSet
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    SUB_CONCLUSION,
    element,
    model,
)

# e1 and e2 support s, which supports c: the release example's shape.
RELEASE = model(
    element("c", CONCLUSION),
    element("s", STRATEGY),
    element("e1", EVIDENCE),
    element("e2", EVIDENCE),
    relations=[("s", "c"), ("e1", "s"), ("e2", "s")],
)


def _registry(*functions: Callable[..., Outcome]) -> StepRegistry:
    steps = [step_of(function) for function in functions]
    assert all(steps)
    return StepRegistry(step for step in steps if step is not None)


def _statuses(result: RunResult) -> dict[str, tuple[Status, tuple[str, ...]]]:
    return {r.element.id: (r.status, r.blocked_by) for r in result}


class Release:
    """A library for ``RELEASE``, whose steps return what a test sets, and record calls."""

    def __init__(self, tmp_path: Path) -> None:
        (tmp_path / "e1.txt").write_text("one", encoding="utf-8")
        (tmp_path / "e2.txt").write_text("two", encoding="utf-8")
        self.root = tmp_path
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.returns: dict[str, Callable[[], Any]] = {}

    def _answer(self, name: str, default: Outcome, **arguments: Any) -> Any:
        self.calls.append((name, arguments))
        return self.returns.get(name, lambda: default)()

    def registry(self) -> StepRegistry:
        @evidence("e1", observes={"log": "e1.txt"}, produces=["a"])
        def first(log: Path) -> Outcome:
            return self._answer("e1", Pass(a=log.read_text(encoding="utf-8")), log=log)

        @evidence("e2", observes={"logs": "*.txt"}, produces=["b"])
        def second(logs: list[Path]) -> Outcome:
            return self._answer("e2", Pass(b=len(logs)), logs=logs)

        @strategy("s", consumes=["a", "b"])
        def gates(a: str, b: int) -> Outcome:
            return self._answer("s", Pass(), a=a, b=b)

        return _registry(first, second, gates)

    def run(self, justification: Justification = RELEASE, **options: Any) -> RunResult:
        return run(justification, self.registry(), root=self.root, **options)

    def called(self) -> list[str]:
        return [name for name, _ in self.calls]


@pytest.fixture
def release(tmp_path: Path) -> Release:
    return Release(tmp_path)


def test_every_step_runs_supporters_first_with_what_it_consumes_and_observes(
    release: Release,
) -> None:
    result = release.run()

    assert result.verdict is Verdict.PASS
    assert release.calls == [
        ("e1", {"log": release.root / "e1.txt"}),
        ("e2", {"logs": [release.root / "e1.txt", release.root / "e2.txt"]}),
        ("s", {"a": "one", "b": 2}),
    ]
    assert [r.element.id for r in result] == ["e1", "e2", "s", "c"]
    assert {r.status for r in result} == {Status.PASS}
    assert result.diagnostics == ()


def test_what_each_element_did_is_recorded(release: Release) -> None:
    result = release.run()

    e1, e2, s, c = result.elements
    assert (e1.ran, e1.outcome, dict(e1.produced)) == (True, Pass(a="one"), {"a": "one"})
    assert [(o.path, o.size) for o in e1.observed] == [("e1.txt", 3)]
    assert [o.path for o in e2.observed] == ["e1.txt", "e2.txt"]
    assert e1.binding is not None
    assert e1.binding.designators == ("e1",)
    assert (s.ran, s.produced, s.observed) == (True, {}, ())
    assert (c.ran, c.binding, c.reason, c.outcome) == (False, None, None, None)
    assert result.values.produced_by("a") == "e1"


def test_a_failure_skips_what_it_supports_without_calling_it(release: Release) -> None:
    release.returns["e1"] = lambda: Fail("the log reports a failure")

    result = release.run()

    assert result.verdict is Verdict.FAIL
    assert release.called() == ["e1", "e2"]
    assert _statuses(result) == {
        "e1": (Status.FAIL, ()),
        "e2": (Status.PASS, ()),
        "s": (Status.SKIP, ("e1",)),
        "c": (Status.SKIP, ("e1",)),
    }
    assert result.result("e1").reason == "the log reports a failure"
    assert "e1" in (result.result("c").reason or "")
    assert "a" not in result.values


def test_a_skip_propagates_like_a_failure_and_the_verdict_is_skip(release: Release) -> None:
    release.returns["s"] = lambda: Skip("not on this platform")

    result = release.run()

    assert result.verdict is Verdict.SKIP
    assert _statuses(result)["s"] == (Status.SKIP, ())
    assert _statuses(result)["c"] == (Status.SKIP, ("s",))
    assert result.result("s").reason == "not on this platform"


def test_a_skip_without_a_reason_has_none(release: Release) -> None:
    release.returns["s"] = Skip

    assert release.run().result("s").reason is None


def test_every_root_cause_is_named_in_model_order(release: Release) -> None:
    release.returns["e2"] = lambda: Skip("no logs today")
    release.returns["e1"] = lambda: Fail("broken")

    result = release.run()

    assert result.verdict is Verdict.FAIL
    assert _statuses(result)["s"] == (Status.SKIP, ("e1", "e2"))
    assert _statuses(result)["c"] == (Status.SKIP, ("e1", "e2"))


def _divide() -> Outcome:
    return Pass(a=str(1 / 0))


def test_an_exception_fails_the_element_with_jp022_and_its_traceback(release: Release) -> None:
    release.returns["e1"] = _divide

    result = release.run()

    e1 = result.result("e1")
    assert (e1.status, e1.ran) == (Status.FAIL, True)
    assert [(d.code, d.severity, d.element) for d in e1.diagnostics] == [
        (STEP_RAISED, Severity.ERROR, "e1")
    ]
    assert e1.error is not None
    assert e1.error.exc_type is ZeroDivisionError
    assert e1.error.stack[-1].name == "_divide"
    assert [Path(frame.filename).name for frame in e1.error.stack] == ["test_engine.py"] * 3
    assert _statuses(result)["s"] == (Status.SKIP, ("e1",))
    assert result.verdict is Verdict.FAIL


def _exit() -> Outcome:
    raise SystemExit(2)


def _interrupt() -> Outcome:
    raise KeyboardInterrupt


def test_a_step_that_exits_fails_and_an_interrupt_stops_the_run(release: Release) -> None:
    release.returns["e1"] = _exit
    assert [d.code for d in release.run().diagnostics] == [STEP_RAISED]

    release.returns["e1"] = _interrupt
    with pytest.raises(KeyboardInterrupt):
        release.run()


def test_a_step_that_returns_no_outcome_fails_with_jp017(release: Release) -> None:
    release.returns["s"] = lambda: True

    result = release.run()

    s = result.result("s")
    assert (s.status, s.ran, s.outcome) == (Status.FAIL, True, None)
    assert [d.code for d in s.diagnostics] == [NOT_AN_OUTCOME]
    assert _statuses(result)["c"] == (Status.SKIP, ("s",))


def test_a_pass_without_a_declared_value_fails_with_jp023_and_stores_nothing(
    release: Release,
) -> None:
    release.returns["e1"] = Pass

    result = release.run()

    e1 = result.result("e1")
    assert (e1.status, e1.outcome, e1.produced) == (Status.FAIL, Pass(), {})
    assert [(d.code, d.severity) for d in e1.diagnostics] == [
        (DECLARED_VALUE_MISSING, Severity.ERROR)
    ]
    assert "a" not in result.values
    assert release.called() == ["e1", "e2"]


def test_an_undeclared_value_is_dropped_with_a_jp024_warning(release: Release) -> None:
    release.returns["e1"] = lambda: Pass(a="one", extra=42)

    result = release.run()

    e1 = result.result("e1")
    assert e1.status is Status.PASS
    assert dict(e1.produced) == {"a": "one"}
    assert [(d.code, d.severity) for d in e1.diagnostics] == [(UNDECLARED_VALUE, Severity.WARNING)]
    assert "extra" not in result.values
    assert result.verdict is Verdict.PASS


def test_missing_and_undeclared_values_are_both_reported(release: Release) -> None:
    release.returns["e1"] = lambda: Pass(extra=42)

    e1 = release.run().result("e1")

    assert [d.code for d in e1.diagnostics] == [UNDECLARED_VALUE, DECLARED_VALUE_MISSING]
    assert e1.status is Status.FAIL


def test_a_produced_none_is_a_value(release: Release) -> None:
    release.returns["e1"] = lambda: Pass(a=None)

    result = release.run()

    assert result.verdict is Verdict.PASS
    assert ("s", {"a": None, "b": 2}) in release.calls


def test_an_unreachable_artifact_fails_the_evidence_with_jp019_without_calling_it(
    release: Release,
) -> None:
    (release.root / "e1.txt").unlink()

    result = release.run()

    e1 = result.result("e1")
    assert (e1.status, e1.ran) == (Status.FAIL, False)
    assert [(d.code, d.element) for d in e1.diagnostics] == [(UNREACHABLE_ARTIFACT, "e1")]
    assert [(o.path, o.reachable) for o in e1.observed] == [("e1.txt", False)]
    assert release.called() == ["e2"]
    assert _statuses(result)["s"] == (Status.SKIP, ("e1",))


def test_an_error_in_validation_runs_nothing(release: Release) -> None:
    @strategy("s", consumes=["a", "nothing_produces_this"])
    def gates(a: str, nothing_produces_this: int) -> Outcome:
        return Pass()

    @evidence("e1", observes={"log": "e1.txt"}, produces=["a"])
    def first(log: Path) -> Outcome:
        raise AssertionError("must not run")

    result = run(RELEASE, _registry(first, gates), root=release.root)

    assert result.verdict is Verdict.INVALID
    assert result.elements == ()
    assert result.validation.errors
    assert result.diagnostics == result.validation.diagnostics


def test_a_strict_run_stops_on_a_warning(release: Release) -> None:
    @evidence("e1", observes={"log": "e1.txt"}, produces=["a", "unused"])
    def first(log: Path) -> Outcome:
        return Pass(a="one", unused=0)

    @evidence("e2", observes={"logs": "*.txt"}, produces=["b"])
    def second(logs: list[Path]) -> Outcome:
        return Pass(b=0)

    @strategy("s", consumes=["a", "b"])
    def gates(a: str, b: int) -> Outcome:
        return Pass()

    registry = _registry(first, second, gates)

    assert run(RELEASE, registry, root=release.root).verdict is Verdict.PASS
    assert run(RELEASE, registry, root=release.root, strict=True).verdict is Verdict.INVALID


# A cross-check (JP008): an evidence step bound to a sub-conclusion argued below it.
REFINED = model(
    element("c", CONCLUSION),
    element("top", STRATEGY),
    element("hook", SUB_CONCLUSION),
    element("below", STRATEGY),
    element("e", EVIDENCE),
    relations=[("top", "c"), ("hook", "top"), ("below", "hook"), ("e", "below")],
)


def _refined_library(order: list[str], below_outcome: Outcome) -> StepRegistry:
    @evidence("e", observes={"log": "log.txt"}, produces=["x"])
    def observed(log: Path) -> Outcome:
        order.append("e")
        return Pass(x=1)

    @strategy("below", consumes=["x"])
    def argued(x: int) -> Outcome:
        order.append("below")
        return below_outcome

    @evidence("hook", observes={"log": "log.txt"}, produces=["checked"])
    def cross_check(log: Path) -> Outcome:
        order.append("hook")
        return Pass(checked=True)

    @strategy("top", consumes=["checked"])
    def judged(checked: bool) -> Outcome:
        order.append("top")
        return Pass()

    return _registry(observed, argued, cross_check, judged)


def test_a_cross_check_runs_after_the_argument_below_it(tmp_path: Path) -> None:
    (tmp_path / "log.txt").write_text("", encoding="utf-8")
    order: list[str] = []

    result = run(REFINED, _refined_library(order, Pass()), root=tmp_path)

    assert order == ["e", "below", "hook", "top"]
    assert result.verdict is Verdict.PASS
    assert [d.code for d in result.diagnostics] == ["JP008"]


def test_a_cross_check_is_not_called_when_the_argument_below_it_fails(tmp_path: Path) -> None:
    (tmp_path / "log.txt").write_text("", encoding="utf-8")
    order: list[str] = []

    result = run(REFINED, _refined_library(order, Fail("no")), root=tmp_path)

    assert order == ["e", "below"]
    hook = result.result("hook")
    assert (hook.status, hook.blocked_by, hook.observed) == (Status.SKIP, ("below",), ())


def test_a_bound_conclusion_runs_last_and_decides(release: Release) -> None:
    @evidence("e1", observes={"log": "e1.txt"}, produces=["a"])
    def first(log: Path) -> Outcome:
        return Pass(a="one")

    @evidence("e2", observes={"logs": "*.txt"}, produces=["b"])
    def second(logs: list[Path]) -> Outcome:
        return Pass(b=2)

    @strategy("s", consumes=["a"])
    def gates(a: str) -> Outcome:
        return Pass()

    @conclusion("c", consumes=["b"])
    def ready(b: int) -> Outcome:
        return Fail(f"only {b} logs")

    result = run(RELEASE, _registry(first, second, gates, ready), root=release.root)

    assert result.verdict is Verdict.FAIL
    assert result.result("c").reason == "only 2 logs"
    assert result.result("c").ran


def test_a_bound_sub_conclusion_is_called_like_any_step(tmp_path: Path) -> None:
    (tmp_path / "log.txt").write_text("", encoding="utf-8")

    @evidence("e", observes={"log": "log.txt"}, produces=["x"])
    def observed(log: Path) -> Outcome:
        return Pass(x=1)

    @strategy("below", consumes=["x"], produces=["y"])
    def argued(x: int) -> Outcome:
        return Pass(y=x + 1)

    @sub_conclusion("hook", consumes=["y"])
    def claimed(y: int) -> Outcome:
        return Skip(f"y is {y}")

    @strategy("top")
    def judged() -> Outcome:
        return Pass()

    result = run(REFINED, _registry(observed, argued, claimed, judged), root=tmp_path)

    assert _statuses(result)["hook"] == (Status.SKIP, ())
    assert _statuses(result)["c"] == (Status.SKIP, ("hook",))


def test_an_unsupported_unbound_claim_is_skipped_on_its_own_account() -> None:
    lonely = model(element("c", CONCLUSION))

    result = run(lonely, StepRegistry([]))

    assert _statuses(result) == {"c": (Status.SKIP, ())}
    assert result.verdict is Verdict.SKIP


def test_a_result_is_looked_up_by_element_id(release: Release) -> None:
    result = release.run()

    assert result.result("s").element.id == "s"
    with pytest.raises(KeyError):
        result.result("nowhere")


def test_without_validation_a_missing_value_is_a_runner_bug_not_a_silent_unset(
    release: Release, monkeypatch: pytest.MonkeyPatch
) -> None:
    # Validation (JP009) guarantees a producer; bypassing it shows the engine checks the
    # invariant rather than passing UNSET to a step.
    monkeypatch.setattr(engine, "RULES", RuleSet([]))

    @strategy("s", consumes=["a"])
    def gates(a: str) -> Outcome:
        return Pass()

    unchecked = model(element("c", CONCLUSION), element("s", STRATEGY), relations=[("s", "c")])
    registry = _registry(gates)
    with pytest.raises(RuntimeError, match="runner bug"):
        run(unchecked, registry, root=release.root)
