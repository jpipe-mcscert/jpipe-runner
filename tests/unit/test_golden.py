import json
from pathlib import Path

import pytest

from tests.golden import assert_matches_golden, normalize, render

REPORT = {"status": "failed", "elements": [{"id": "a", "path": "/tmp/x/steps.py"}, {"id": "b"}]}


def test_render_is_indented_utf8_with_final_newline() -> None:
    assert render({"label": "Prêt"}) == '{\n  "label": "Prêt"\n}\n'


def test_normalize_rewrites_strings_but_not_keys() -> None:
    document = {"/tmp/x": ["/tmp/x/a", {"k": "at /tmp/x/b"}], "n": 1, "t": None}
    assert normalize(document, {"/tmp/x": "<scenario>"}) == {
        "/tmp/x": ["<scenario>/a", {"k": "at <scenario>/b"}],
        "n": 1,
        "t": None,
    }


def test_normalize_replaces_longer_needles_first() -> None:
    replacements = {"/tmp": "<tmp>", "/tmp/x": "<scenario>"}
    assert normalize("/tmp/x/a /tmp/y", replacements) == "<scenario>/a <tmp>/y"


def test_update_writes_the_canonical_rendering(tmp_path: Path) -> None:
    golden = tmp_path / "expected.json"
    assert_matches_golden(REPORT, golden, update=True)
    assert golden.read_text(encoding="utf-8") == render(REPORT)


def test_matching_golden_passes_whatever_the_key_order(tmp_path: Path) -> None:
    golden = tmp_path / "expected.json"
    golden.write_text(json.dumps(dict(reversed(REPORT.items()))), encoding="utf-8")
    assert_matches_golden(REPORT, golden, update=False)


def test_list_order_matters(tmp_path: Path) -> None:
    golden = tmp_path / "expected.json"
    golden.write_text(render({**REPORT, "elements": REPORT["elements"][::-1]}), encoding="utf-8")
    with pytest.raises(pytest.fail.Exception, match="differs"):
        assert_matches_golden(REPORT, golden, update=False)


def test_mismatch_shows_a_diff_and_how_to_update(tmp_path: Path) -> None:
    golden = tmp_path / "expected.json"
    golden.write_text(render({**REPORT, "status": "passed"}), encoding="utf-8")
    with pytest.raises(pytest.fail.Exception) as failure:
        assert_matches_golden(REPORT, golden, update=False)
    message = str(failure.value)
    assert '-  "status": "passed"' in message
    assert '+  "status": "failed"' in message
    assert "--update-goldens" in message


def test_missing_golden_fails_with_instructions(tmp_path: Path) -> None:
    with pytest.raises(pytest.fail.Exception, match="--update-goldens"):
        assert_matches_golden(REPORT, tmp_path / "expected.json", update=False)
