import pytest

from jpipe_runner import __version__
from tests.console import blocks, commands, replay

PAGE = """Some text.

```console
$ jpipe-runner --version
jpipe-runner 0
$ echo $?
0
```

```python
print("not a console block")
```

```console
$ jpipe process -i release.jd -f JSON
```
"""


def test_blocks_are_the_console_fences_of_a_page() -> None:
    assert blocks(PAGE) == [
        "$ jpipe-runner --version\njpipe-runner 0\n$ echo $?\n0\n",
        "$ jpipe process -i release.jd -f JSON\n",
    ]


def test_blocks_of_another_language_can_be_found() -> None:
    assert blocks(PAGE, "python") == ['print("not a console block")\n']


def test_commands_are_the_lines_after_the_prompt() -> None:
    assert commands(blocks(PAGE)[0]) == ["jpipe-runner --version", "echo $?"]


def test_replay_shows_what_each_command_prints_and_the_exit_code(
    capsys: pytest.CaptureFixture[str],
) -> None:
    replayed = replay(blocks(PAGE)[0], capsys)

    assert replayed == f"$ jpipe-runner --version\njpipe-runner {__version__}\n$ echo $?\n0\n"


def test_replay_refuses_a_command_it_cannot_run(capsys: pytest.CaptureFixture[str]) -> None:
    block = blocks(PAGE)[1]

    with pytest.raises(ValueError, match="cannot replay"):
        replay(block, capsys)
