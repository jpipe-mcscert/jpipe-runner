"""A run with more than one job: independent steps run together (#174, ADR-0038).

``test_execution_properties.py`` checks that a run's result does not depend on the number
of jobs; these tests check what only a concurrent run does.
"""

import threading
import time
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from jpipe_runner import Fail, Outcome, Pass, engine, evidence, strategy
from jpipe_runner.engine import STEP_RAISED, ElementResult, RunResult, Status, Verdict
from jpipe_runner.model import Element
from jpipe_runner.steps import StepRegistry, step_of
from jpipe_runner.validation import ValidationReport
from tests.anchored import run
from tests.unit.validation.builders import (
    CONCLUSION,
    EVIDENCE,
    STRATEGY,
    SUB_CONCLUSION,
    element,
    model,
)

# e1, e2 and e3 support s, which supports c.
THREE = model(
    element("c", CONCLUSION),
    element("s", STRATEGY),
    element("e1", EVIDENCE),
    element("e2", EVIDENCE),
    element("e3", EVIDENCE),
    relations=[("s", "c"), ("e1", "s"), ("e2", "s"), ("e3", "s")],
)

WAIT = 10.0
"""How long a step waits for another, in seconds, before the test fails: never, when the
run does what it should."""


def _registry(*functions: Callable[..., Outcome]) -> StepRegistry:
    steps = [step_of(function) for function in functions]
    assert all(steps)
    return StepRegistry(step for step in steps if step is not None)


@pytest.fixture
def root(tmp_path: Path) -> Path:
    for name in ("e1", "e2", "e3"):
        (tmp_path / f"{name}.txt").write_text(name, encoding="utf-8")
    return tmp_path


def _library(
    e1: Callable[[], Outcome], e2: Callable[[], Outcome], e3: Callable[[], Outcome]
) -> StepRegistry:
    """Three evidence steps that do what they are given, each producing the name of the file
    it observes when it passes, and a strategy that passes."""

    def produced(outcome: Outcome, name: str, log: Path) -> Outcome:
        return Pass({name: log.name}) if isinstance(outcome, Pass) else outcome

    @evidence("e1", observes={"log": "e1.txt"}, produces=["v1"])
    def first(log: Path) -> Outcome:
        return produced(e1(), "v1", log)

    @evidence("e2", observes={"log": "e2.txt"}, produces=["v2"])
    def second(log: Path) -> Outcome:
        return produced(e2(), "v2", log)

    @evidence("e3", observes={"log": "e3.txt"}, produces=["v3"])
    def third(log: Path) -> Outcome:
        return produced(e3(), "v3", log)

    @strategy("s", consumes=["v1", "v2", "v3"])
    def gates(v1: str, v2: str, v3: str) -> Outcome:
        return Pass() if (v1, v2, v3) == ("e1.txt", "e2.txt", "e3.txt") else Fail("mixed up")

    return _registry(first, second, third, gates)


def _together(barrier: threading.Barrier) -> Callable[[], Outcome]:
    def step() -> Outcome:
        barrier.wait()
        return Pass()

    return step


def test_independent_steps_run_together(root: Path) -> None:
    # Each evidence waits until all three are running: a run that calls one at a time
    # would break the barrier, and fail them.
    together = _together(threading.Barrier(3, timeout=WAIT))

    result = run(THREE, _library(together, together, together), root=root, jobs=3)

    assert result.verdict is Verdict.PASS, result.diagnostics


def test_no_more_steps_run_at_a_time_than_jobs(root: Path) -> None:
    # Each step waits until two have started, so two run together; a third at once would
    # make three.
    condition = threading.Condition()
    started, running, most = 0, 0, 0

    def counted() -> Outcome:
        nonlocal started, running, most
        with condition:
            started += 1
            running += 1
            most = max(most, running)
            condition.notify_all()
            assert condition.wait_for(lambda: started >= 2, WAIT)
            running -= 1
        return Pass()

    result = run(THREE, _library(counted, counted, counted), root=root, jobs=2)

    assert result.verdict is Verdict.PASS
    assert most == 2


def test_the_result_is_in_topological_order_whatever_ends_first(root: Path) -> None:
    second_done = threading.Event()

    def first() -> Outcome:
        assert second_done.wait(WAIT)
        return Fail("first")

    def second() -> Outcome:
        second_done.set()
        return Fail("second")

    result = run(THREE, _library(first, second, Pass), root=root, jobs=3)

    assert [r.element.id for r in result] == ["e1", "e2", "e3", "s", "c"]
    assert result.result("s").blocked_by == ("e1", "e2")


def test_the_values_are_in_the_order_of_their_producers_whatever_ends_first(
    root: Path,
) -> None:
    second_done = threading.Event()

    def first() -> Outcome:
        assert second_done.wait(WAIT)
        return Pass()

    def second() -> Outcome:
        second_done.set()
        return Pass()

    result = run(THREE, _library(first, second, Pass), root=root, jobs=3)

    assert [(name, value.produced_by) for name, value in result.values.entries()] == [
        ("v1", "e1"),
        ("v2", "e2"),
        ("v3", "e3"),
    ]


# e4 supports s2, which supports the sub-conclusion k; k, e1 and e2 support s, which
# supports c. The topological order is e4, e1, e2, s2, k, s, c: with two jobs, e4 and e1
# start; once e4 fails, e2 takes its thread, ahead of s2, which needs none.
BRANCHES = model(
    element("c", CONCLUSION),
    element("e4", EVIDENCE),
    element("e1", EVIDENCE),
    element("e2", EVIDENCE),
    element("s", STRATEGY),
    element("k", SUB_CONCLUSION),
    element("s2", STRATEGY),
    relations=[("s", "c"), ("k", "s"), ("e1", "s"), ("e2", "s"), ("s2", "k"), ("e4", "s2")],
)


def test_what_needs_no_step_is_decided_while_every_thread_is_busy(root: Path) -> None:
    k_decided = threading.Event()

    class Watching(_Watching):
        def element_decided(self, result: ElementResult) -> None:
            if result.element.id == "k":
                k_decided.set()

    @evidence("e4", observes={"log": "e3.txt"}, produces=["v4"])
    def fails_at_once(log: Path) -> Outcome:
        return Fail(f"{log.name} says no")

    @strategy("s2", consumes=["v4"])
    def judges(v4: str) -> Outcome:
        return Pass() if v4 else Fail("no")

    @evidence("e1", observes={"log": "e1.txt"}, produces=["v1"])
    def first(log: Path) -> Outcome:
        # Runs while e2 does, so both threads are busy until k is decided.
        return Pass(v1=log.name) if k_decided.wait(WAIT) else Fail("k waited for a thread")

    @evidence("e2", observes={"log": "e2.txt"}, produces=["v2"])
    def second(log: Path) -> Outcome:
        return Pass(v2=log.name) if k_decided.wait(WAIT) else Fail("k waited for a thread")

    @strategy("s", consumes=["v1", "v2"])
    def gates(v1: str, v2: str) -> Outcome:
        return Pass() if v1 and v2 else Fail("no")

    registry = _registry(fails_at_once, judges, first, second, gates)
    result = run(BRANCHES, registry, root=root, jobs=2, listener=Watching())

    assert result.result("e1").status is Status.PASS
    assert result.result("e2").status is Status.PASS
    assert result.result("k").blocked_by == ("e4",)


def test_one_job_calls_each_step_on_the_thread_that_runs_the_run(root: Path) -> None:
    threads: list[threading.Thread] = []

    def where() -> Outcome:
        threads.append(threading.current_thread())
        return Pass()

    run(THREE, _library(where, where, where), root=root)
    assert threads == [threading.main_thread()] * 3

    threads.clear()
    run(THREE, _library(where, where, where), root=root, jobs=2)
    assert threading.main_thread() not in threads


def _raises() -> Outcome:
    raise RuntimeError("broken")


def test_a_step_that_raises_on_its_thread_fails_with_jp022_and_its_traceback(
    root: Path,
) -> None:
    result = run(THREE, _library(_raises, Pass, Pass), root=root, jobs=2)

    (raised,) = result.diagnostics
    assert raised.code == STEP_RAISED
    assert raised.message.startswith("the step raised RuntimeError at ")
    assert raised.traceback is not None
    assert raised.traceback.stack[-1].name == "_raises"
    assert result.result("e1").status is Status.FAIL


def _interrupt() -> Outcome:
    raise KeyboardInterrupt


def test_an_interrupt_on_a_step_s_thread_stops_the_run(root: Path) -> None:
    called: list[str] = []

    def recorded() -> Outcome:
        called.append("e3")
        return Pass()

    with pytest.raises(KeyboardInterrupt):
        run(THREE, _library(_interrupt, Pass, recorded), root=root, jobs=1)
    assert called == []


def test_an_interrupted_run_waits_for_the_steps_still_running(root: Path) -> None:
    second_started = threading.Event()
    ended: list[str] = []

    def interrupts() -> Outcome:
        assert second_started.wait(WAIT)
        raise KeyboardInterrupt

    def slow() -> Outcome:
        second_started.set()
        time.sleep(0.05)
        ended.append("e2")
        return Pass()

    with pytest.raises(KeyboardInterrupt):
        run(THREE, _library(interrupts, slow, Pass), root=root, jobs=2)
    # e2 ended before run returned, while its library was still imported; e3 never started.
    assert ended == ["e2"]


def test_a_runner_bug_on_a_step_s_thread_reaches_the_caller(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def broken(*_: Any) -> None:
        raise RuntimeError("a runner bug")

    monkeypatch.setattr(engine, "observe", broken)

    with pytest.raises(RuntimeError, match="a runner bug"):
        run(THREE, _library(Pass, Pass, Pass), root=root, jobs=2)


def test_the_run_looks_again_while_a_step_runs_long(
    root: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(engine, "_WAKE_UP", 0.001)

    def slow() -> Outcome:
        time.sleep(0.05)
        return Pass()

    assert run(THREE, _library(slow, Pass, Pass), root=root, jobs=2).verdict is Verdict.PASS


class _Watching:
    """A listener that records the thread it is told on, and lets e1 go on once its source
    is observed."""

    def __init__(self) -> None:
        self.threads: set[threading.Thread] = set()
        self.observed = threading.Event()

    def validation_ended(self, report: ValidationReport) -> None:
        self.threads.add(threading.current_thread())

    def steps_starting(self, planned: RunResult) -> None:
        self.threads.add(threading.current_thread())

    def element_started(self, element: Element) -> None:
        self.threads.add(threading.current_thread())

    def source_observed(self, element: Element, source: str, reachable: bool) -> None:
        self.threads.add(threading.current_thread())
        if element.id == "e1":
            self.observed.set()

    def element_decided(self, result: ElementResult) -> None:
        self.threads.add(threading.current_thread())


def test_the_listener_is_told_on_the_run_s_thread_and_of_a_source_while_its_step_runs(
    root: Path,
) -> None:
    listener = _Watching()

    def waits_for_its_source() -> Outcome:
        # Passes only if the listener was told of e1's source before e1's step returned.
        return Pass() if listener.observed.wait(WAIT) else Fail("not told")

    registry = _library(waits_for_its_source, Pass, Pass)
    result = run(THREE, registry, root=root, jobs=2, listener=listener)

    assert result.verdict is Verdict.PASS
    assert listener.threads == {threading.main_thread()}


@pytest.mark.parametrize("jobs", [0, -1])
def test_a_run_needs_at_least_one_job(root: Path, jobs: int) -> None:
    with pytest.raises(ValueError, match="at least one job"):
        run(THREE, _library(Pass, Pass, Pass), root=root, jobs=jobs)
