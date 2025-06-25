"""
jpipe_runner.runner
~~~~~~~~~~~~~~~~~~~

This module contains the entrypoint of jPipe Runner.
"""

import argparse
import glob
import logging
import shutil
import sys
from typing import Iterable

from termcolor import colored

from jpipe_runner.enums import StatusType
from jpipe_runner.framework.engine import PipelineEngine
from jpipe_runner.framework.logger import GLOBAL_LOGGER
from jpipe_runner.runtime import PythonRuntime

# Generate:
# - https://patorjk.com/software/taag/#p=display&f=Ivrit&t=jPipe%20%20Runner%0A
JPIPE_RUNNER_ASCII = r"""
    _ ____  _               ____                              
   (_)  _ \(_)_ __   ___   |  _ \ _   _ _ __  _ __   ___ _ __ 
   | | |_) | | '_ \ / _ \  | |_) | | | | '_ \| '_ \ / _ \ '__|
   | |  __/| | |_) |  __/  |  _ <| |_| | | | | | | |  __/ |   
  _/ |_|   |_| .__/ \___|  |_| \_\\__,_|_| |_|_| |_|\___|_|   
 |__/        |_|                                                                                     
"""


def parse_args(argv: list[str] | None = None):
    """
    Parses command-line arguments for the jPipe Runner.

    Available arguments:
        --variable, -v: Define variables in the format NAME:VALUE (can be used multiple times).\n
        --library, -l: Path pattern to Python libraries to load (can be used multiple times).\n
        --diagram, -d: Wildcard pattern for diagram selection.\n
        --output, -o: Output path for the generated diagram image (optional).\n
        --dry-run: Simulate execution without performing actual justifications.\n
        --verbose, -V: Enable verbose logging.\n
        --config-file: Path to a YAML configuration file.\n
        jd_file: Path to the justification (.jd) file.\n

    :param argv: Optional list of command-line arguments (defaults to `sys.argv[1:]`).
    :type argv: list[str] or None
    :return: Parsed arguments namespace.
    :rtype: argparse.Namespace
    """
    parser = argparse.ArgumentParser(prog="jpipe-runner",
                                     description=("McMaster University - McSCert (c) 2023-..."
                                                  + JPIPE_RUNNER_ASCII),
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument("--variable", "-v", action="append", default=[],
                        help="Define a variable in the format NAME:VALUE")
    parser.add_argument("--library", "-l", action="append", default=[],
                        help="Specify a Python library to load")
    parser.add_argument("--diagram", "-d", metavar="PATTERN", default="*",
                        help="Specify diagram pattern or wildcard")
    parser.add_argument("--output", "-o", metavar="FILE",
                        help="Output file for generated diagram image")
    parser.add_argument("--dry-run", action="store_true",
                        help="Perform a dry run without actually executing justifications")
    parser.add_argument("--verbose", "-V", action="store_true",
                        help="Enable verbose (debug) output")
    parser.add_argument("--config-file",
                        help="Path to the config .yaml file")
    parser.add_argument("jd_file",
                        help="Path to the justification .jd file")

    return parser.parse_args(argv)


def pretty_display(diagrams: Iterable[tuple[str, Iterable[dict]]]) -> [int, int, int, int]:
    """
    Prints a formatted, colorized summary of justification results to the terminal.

    For each justification:
    - Displays variable name, label, status (PASS, FAIL, SKIP)
    - Counts totals and returns summary statistics

    :param diagrams: Iterable of tuples containing justification names and result data.
    :type diagrams: Iterable[tuple[str, Iterable[dict]]]
    :return: Tuple containing total, passed, failed, and skipped justification counts.
    :rtype: tuple[int, int, int, int]
    """
    terminal_width, _ = shutil.get_terminal_size((78, 30))
    width = 78 if terminal_width > 78 else terminal_width

    colored_statuses = {
        StatusType.PASS: colored(StatusType.PASS.value, color="green"),
        StatusType.FAIL: colored(StatusType.FAIL.value, color="red"),
        StatusType.SKIP: colored(StatusType.SKIP.value, color="yellow"),
    }

    jpipe_title = colored("jPipe Files", color=None, attrs=[])

    total_justifications = 0
    passed_justifications = 0
    failed_justifications = 0
    skipped_justifications = 0

    print("=" * width)
    print(f"{jpipe_title}".ljust(width))
    print("=" * width)

    for name, result in diagrams:

        total_justifications += 1

        print(f"{jpipe_title}.Justification :: {name}".ljust(width))
        print("=" * width)

        for data in result:
            var_type = data['var_type']
            var_name = data['name']
            label = data['label']
            exception = data.get('exception')
            status = data['status']
            len_status = len(f"| {status.value} |")
            status_bar = f"| {colored_statuses[status]} |"

            if exception:
                print(exception.ljust(width))

            print(f"{var_type}<{var_name}> :: {label}".ljust(width - len_status) + status_bar)
            print("-" * width)

            if status == StatusType.PASS:
                passed_justifications += 1

            if status == StatusType.FAIL:
                failed_justifications += 1

            if status == StatusType.SKIP:
                skipped_justifications += 1

    print(f"{jpipe_title}")
    print(f"{total_justifications} justification{'s' if total_justifications > 1 else ''},",
          f"{passed_justifications} passed,",
          f"{failed_justifications} failed,",
          f"{skipped_justifications} skipped",
          )
    print("=" * width)

    return total_justifications, passed_justifications, failed_justifications, skipped_justifications


def main():
    args = parse_args(sys.argv[1:])

    # if verbose
    if args.verbose:
        GLOBAL_LOGGER.setLevel(logging.INFO)

    runtime = PythonRuntime(libraries=[i for l in args.library
                                       for i in glob.glob(l)],
                            variables=[i.split(':', maxsplit=1)
                                       for i in args.variable
                                       if i.find(':')])

    jpipe = PipelineEngine(config_path=args.config_file, justification_path=args.jd_file)

    diagrams = [(jpipe.justification_name, jpipe.graph)]

    if not diagrams:
        print(f"No justification diagram found: {args.diagram}", file=sys.stderr)
        sys.exit(1)

    if args.output:
        print("Output is set, generating diagram image...", file=sys.stderr)
        match args.output:
            case "stdout" | "STDOUT":
                args.output = sys.stdout.buffer
            case "stderr" | "STDERR":
                args.output = sys.stderr.buffer
        # jpipe.export_to_image(path=args.output, format="png")
        raise NotImplementedError("Image generation not implemented yet")
        sys.exit(1)

    # This mirrors the old logic: justify each diagram and collect results
    m, n, _, s = pretty_display([
        (jpipe.justification_name, jpipe.justify(dry_run=args.dry_run, runtime=runtime))
    ])

    # exit 0 only when all justifications passed/skipped
    sys.exit(m - n - s)


if __name__ == '__main__':
    main()
