"""``python -m jpipe_runner``: the command line, as the ``jpipe-runner`` script runs it.

``python -m`` puts the working directory first on ``sys.path``, and the script does not.
It is dropped here, before the runner imports its modules and dependencies, so that
neither the runner nor a step library imports a module of the working directory however
the runner is started: only the directories ``--python-path`` names are added (ADR-0020).
The package itself is imported before this runs, and loads only the standard library.
"""

import sys
from pathlib import Path

if __name__ == "__main__":
    if sys.path and Path(sys.path[0] or ".").resolve() == Path.cwd().resolve():
        del sys.path[0]

    from jpipe_runner.cli import main

    raise SystemExit(main())
