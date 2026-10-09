"""Console examples in the documentation, replayed (see tests/README.md).

A page shows a session in a ```` ```console ```` block: each command after ``$ ``, then
what it printed. ``blocks`` finds them, and ``replay`` runs a block's commands in process,
in the working directory the test has set, and writes the block as the commands printed
it. A test compares the two, so the page cannot show output the command does not give.

Two commands can be replayed: ``jpipe-runner …``, run by ``cli.main`` (what it logs on
stderr is shown before what it prints, which is the order it writes them), and
``echo $?``, the exit code of the command before it.
"""

import shlex

import pytest

from jpipe_runner.cli import main

FENCE = "```"
PROMPT = "$ "


def blocks(markdown: str, language: str = "console") -> list[str]:
    """The text of every block of ``markdown`` fenced as ``language``, without its fences."""
    found: list[str] = []
    current: list[str] | None = None
    for line in markdown.splitlines(keepends=True):
        if current is None:
            if line.rstrip() == f"{FENCE}{language}":
                current = []
        elif line.rstrip() == FENCE:
            found.append("".join(current))
            current = None
        else:
            current.append(line)
    return found


def commands(block: str) -> list[str]:
    """The commands of ``block``: each line after the prompt."""
    return [line[len(PROMPT) :] for line in block.splitlines() if line.startswith(PROMPT)]


def replay(block: str, capsys: pytest.CaptureFixture[str]) -> str:
    """``block`` as its commands print it now, run in the working directory."""
    shown: list[str] = []
    code = 0
    for command in commands(block):
        shown.append(f"{PROMPT}{command}\n")
        if command == "echo $?":
            shown.append(f"{code}\n")
            continue
        argv = shlex.split(command)
        if argv[0] != "jpipe-runner":
            raise ValueError(f"cannot replay {command!r}: only jpipe-runner and echo $? can be")
        code = main(argv[1:])
        out, err = capsys.readouterr()
        shown.append(err + out)
    return "".join(shown)
