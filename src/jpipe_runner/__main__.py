"""``python -m jpipe_runner``: the command line, as the ``jpipe-runner`` script runs it.

``python -m`` puts the working directory first on ``sys.path``, and the script does not.
It is dropped here, so that a step library imports the same modules however the runner is
started: only the directories ``--python-path`` names are added (ADR-0020).
"""

import sys
from pathlib import Path

from jpipe_runner.cli import main

if __name__ == "__main__":
    if sys.path and Path(sys.path[0] or ".").resolve() == Path.cwd().resolve():
        del sys.path[0]
    raise SystemExit(main())
