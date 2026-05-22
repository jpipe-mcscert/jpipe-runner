"""
jpipe_runner.runner
~~~~~~~~~~~~~~~~~~~

This module contains the entrypoint of jPipe Runner.
"""

import argparse
import glob
import importlib.metadata
import logging
import os
import shutil
import sys
from typing import Iterable

from jpipe_runner.enums import StatusType
from jpipe_runner.exceptions import RuntimeException
from jpipe_runner.framework.engine import PipelineEngine
from jpipe_runner.framework.logger import GLOBAL_LOGGER, log_buffer
from jpipe_runner.runtime import PythonRuntime
from jpipe_runner.utils.append_else_default_action import AppendElseDefaultAction
from jpipe_runner.utils.terminal import colored

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

# https://patorjk.com/software/taag/#p=display&f=Ivrit&t=STDERR%20OUTPUT%20BEGIN
STDERR_OUTPUT_BEGIN = r"""

  _____ ____  ____   ___  ____    _     ___   ____ 
 | ____|  _ \|  _ \ / _ \|  _ \  | |   / _ \ / ___|
 |  _| | |_) | |_) | | | | |_) | | |  | | | | |  _ 
 | |___|  _ <|  _ <| |_| |  _ <  | |__| |_| | |_| |
 |_____|_| \_\_| \_\\___/|_| \_\ |_____\___/ \____|
                                                   

"""

IMAGE_EXPORT_FORMAT = ["dot", "gif", "jpeg", "jpg", "pdf", "png", "svg"]


def parse_args(argv: list[str] | None = None):
    """
    Parses command-line arguments for the jPipe Runner.

    Available arguments:
        --variable, -v: Define variables in the format NAME:VALUE (can be used multiple times).\n
        --library, -l: Path pattern to Python libraries to load (can be used multiple times).\n
        --diagram, -d: Wildcard pattern for diagram selection.\n
        --format, -f: Image format for the generated diagram (dot, gif, jpeg, jpg, png, svg).\n
        --output-path, -o: Output path for the generated diagram image.\n
        --dry-run: Simulate execution without performing actual justifications.\n
        --verbose, -V: Enable verbose logging.\n
        --config-file: Path to a YAML configuration file.\n
        --python-path, -p: Extra folders to search for Python files/modules.
                If not specified, defaults to the current directory (".").
                If at least one path is provided, only those paths are used.\n
        jd_file: Path to the justification (.json) file.\n

    :param argv: Optional list of command-line arguments (defaults to `sys.argv[1:]`).
    :type argv: list[str] or None
    :return: Parsed arguments namespace.
    :rtype: argparse.Namespace
    """
    try:
        version = importlib.metadata.version("jpipe-runner")
        version_info = f" - Version {version}"
    except (ImportError, importlib.metadata.PackageNotFoundError):
        version_info = ""

    parser = argparse.ArgumentParser(
        prog="jpipe-runner",
        description=(
            "McMaster University - McSCert (c) 2023-..." + version_info + JPIPE_RUNNER_ASCII
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    # Register a custom AppendElseDefaultAction,
    # This is not yet a built‑in argparse action; if the upstream PR
    # (proposing `append_else_default`) is accepted and released,
    # this registration line can be removed.
    parser.register("action", "append_else_default", AppendElseDefaultAction)

    parser.add_argument(
        "--variable",
        "-v",
        action="append",
        default=[],
        help="Define a variable in the format NAME:VALUE",
    )
    parser.add_argument(
        "--library", "-l", action="append", default=[], help="Specify a Python library to load"
    )
    parser.add_argument(
        "--diagram",
        "-d",
        metavar="PATTERN",
        default="*",
        help="Specify diagram pattern or wildcard",
    )
    parser.add_argument(
        "--format",
        "-f",
        choices=IMAGE_EXPORT_FORMAT,
        help=(
            "Format for the generated diagram image. \n"
            "Supported formats include: dot, gif, jpeg, jpg, png, svg"
        ),
    )
    parser.add_argument(
        "--output-path",
        "-o",
        metavar="PATH",
        default=".",
        help="Path to save the generated diagram image. ",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Perform a dry run without actually executing justifications",
    )
    parser.add_argument("--verbose", "-V", action="store_true", help="Enable verbose (info) output")
    parser.add_argument("--config-file", help="Path to the config .yaml file")
    parser.add_argument(
        "--python-path",
        "-p",
        action="append_else_default",
        default=["."],
        help=(
            "Extra folders to search for your Python files/modules. \n"
            'If not specified, defaults to the current directory ("."). \n'
            "If at least one path is provided, only those paths are used."
        ),
    )

    parser.add_argument("jd_file", help="Path to the justification .json file")

    return parser.parse_args(argv)


def pretty_display(diagrams: Iterable[tuple[str, Iterable[dict]]]) -> tuple[int, int, int, int]:
    """
    Prints a formatted, colorized summary of justification results to the terminal.

    For each justification:
    - Displays variable name, label, status (PASS, FAIL, SKIP)
    - Wraps long lines based on terminal width
    - Counts totals and returns summary statistics

    :param diagrams: Iterable of tuples containing justification names and result data.
    :type diagrams: Iterable[tuple[str, Iterable[dict]]]
    :return: Tuple containing total, passed, failed, and skipped justification counts.
    :rtype: tuple[int, int, int, int]
    """
    terminal_width, _ = shutil.get_terminal_size((78, 30))
    width = 78 if terminal_width > 78 else terminal_width  # Enforce minimum width

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
            var_type = data["var_type"]
            var_name = data["name"]
            label = data["label"]
            exception = data.get("exception")
            status = data["status"]
            status_bar = f"| {colored_statuses[status]} |"
            status_bar_visual_len = len(f"| {status.value} |")

            # Format the main line, truncating with "..." if it exceeds available width
            line_prefix = f"{var_type}<{var_name}> :: "
            full_line = f"{line_prefix}{label}"
            max_content = width - status_bar_visual_len - 1
            if len(full_line) > max_content:
                if max_content <= 0:
                    full_line = ""
                elif max_content <= 3:
                    full_line = "..."[:max_content]
                else:
                    full_line = full_line[: max_content - 3] + "..."
            print(full_line.ljust(width - status_bar_visual_len) + status_bar)

            if exception:
                GLOBAL_LOGGER.warning(exception)

            print("-" * width)

            # Count statuses
            if status == StatusType.PASS:
                passed_justifications += 1
            elif status == StatusType.FAIL:
                failed_justifications += 1
            elif status == StatusType.SKIP:
                skipped_justifications += 1

    # Print final summary
    print(f"{jpipe_title}")
    print(
        f"{total_justifications} justification{'s' if total_justifications != 1 else ''},",
        f"{passed_justifications} passed,",
        f"{failed_justifications} failed,",
        f"{skipped_justifications} skipped",
    )
    print("=" * width)

    return (
        total_justifications,
        passed_justifications,
        failed_justifications,
        skipped_justifications,
    )


def run_workflow_logic():
    args = parse_args(sys.argv[1:])

    if args.verbose:
        GLOBAL_LOGGER.setLevel(logging.INFO)

    if not args.jd_file:
        print("No justification json file provided. Please specify a .json file.", file=sys.stderr)
        sys.exit(1)

    if not args.jd_file.endswith(".json"):
        print("The provided justification file is not a .json file.", file=sys.stderr)
        sys.exit(1)

    # Check that each library path exists
    not_matched_files = []
    for lib_pattern in args.library:
        matched_files = glob.glob(lib_pattern)
        if not matched_files:
            not_matched_files.append(lib_pattern)

    if not_matched_files:
        print(f"No library found for path(s): {', '.join(not_matched_files)}", file=sys.stderr)
        print("Please check the provided library paths.", file=sys.stderr)
        sys.exit(1)

    try:
        runtime = PythonRuntime(
            libraries=[i for lib in args.library for i in glob.glob(lib)],
            additional_paths=args.python_path,
        )
    except RuntimeException as e:
        print(str(e), file=sys.stderr)
        sys.exit(1)

    jpipe = PipelineEngine(
        config_path=args.config_file,
        justification_path=args.jd_file,
        variables=args.variable,
    )

    diagrams = [(jpipe.justification_name, jpipe.graph)]

    if not diagrams:
        print(f"No justification diagram found: {args.diagram}", file=sys.stderr)
        sys.exit(1)

    # Run justification logic and gather results
    justification_result = list(jpipe.justify(dry_run=args.dry_run, runtime=runtime))

    if args.dry_run or not justification_result:
        if log_buffer.has_errors():
            print(STDERR_OUTPUT_BEGIN, file=sys.stderr)
            log_buffer.dump_to_stderr()
            exit(1)
        exit(0)

    print(JPIPE_RUNNER_ASCII)
    _, _, total_fail, _ = pretty_display([(jpipe.justification_name, justification_result)])

    if args.format:
        if args.output_path.lower() in {"stdout", "stderr"}:
            print("Streamed diagram output is not supported yet.", file=sys.stderr)
            sys.exit(1)

        status_dict = {item["name"]: item["status"].value for item in justification_result}

        if args.format in IMAGE_EXPORT_FORMAT:
            jpipe.export_to_format(
                status_dict=status_dict,
                output_path=args.output_path,
                filename=jpipe.justification_name,
                format=args.format,
            )
            if args.output_path in [".", "./"]:
                output_location = f"{jpipe.justification_name}.{args.format}"
            else:
                output_location = os.path.join(
                    args.output_path, f"{jpipe.justification_name}.{args.format}"
                )

            print(f"{jpipe.justification_name} diagram saved to: {output_location}")
        else:
            print(
                f"Unsupported output format: {args.format}. Supported formats are: {', '.join(IMAGE_EXPORT_FORMAT)}",
                file=sys.stderr,
            )
            print(STDERR_OUTPUT_BEGIN, file=sys.stderr)
            log_buffer.dump_to_stderr()
            sys.exit(1)

    # if errors on buffer show them
    if log_buffer.has_errors():
        print(STDERR_OUTPUT_BEGIN, file=sys.stderr)
        log_buffer.dump_to_stderr()

    sys.exit(0 if total_fail == 0 else 1)  # Exit with 0 if all passed, otherwise 1


def main():
    run_workflow_logic()


if __name__ == "__main__":
    main()
