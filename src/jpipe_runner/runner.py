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
import threading
import tkinter as tk
from typing import Iterable

from termcolor import colored

from jpipe_runner.GraphWorkflowVisualizer import GraphWorkflowVisualizer
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

IMAGE_EXPORT_FORMAT = ['canon', 'cmap', 'cmapx', 'cmapx_np', 'dia', 'dot',
                       'fig', 'gd', 'gd2', 'gif', 'hpgl', 'imap', 'imap_np',
                       'ismap', 'jpe', 'jpeg', 'jpg', 'mif', 'mp', 'pcl', 'pdf',
                       'pic', 'plain', 'plain-ext', 'png', 'ps', 'ps2', 'svg',
                       'svgz', 'vml', 'vmlz', 'vrml', 'vtx', 'wbmp', 'xdot', 'xlib']


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
                        help=(
                            "Output file for generated diagram image. The format is inferred from the file extension.\n"
                            "Supported formats include: canon, cmap, cmapx, cmapx_np, dia, dot, fig, gd, gd2, gif, hpgl,\n"
                            "imap, imap_np, ismap, jpe, jpeg, jpg, mif, mp, pcl, pdf, pic, plain, plain-ext, png, ps,\n"
                            "ps2, svg, svgz, vml, vmlz, vrml, vtx, wbmp, xdot, xlib."
                        ))
    parser.add_argument("--dry-run", action="store_true",
                        help="Perform a dry run without actually executing justifications")
    parser.add_argument("--verbose", "-V", action="store_true",
                        help="Enable verbose (debug) output")
    parser.add_argument("--config-file",
                        help="Path to the config .yaml file")
    parser.add_argument("jd_file",
                        help="Path to the justification .jd file")
    # argument to enable GUI
    parser.add_argument("--gui", action="store_true",
                        help="Enable GUI mode for visualizing workflow steps")

    return parser.parse_args(argv)


def pretty_display(diagrams: Iterable[tuple[str, Iterable[dict]]]) -> tuple[int, int, int, int]:
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


workflow_ui: GraphWorkflowVisualizer | None = None


def mark_step(step, status):
    global workflow_ui
    if workflow_ui:
        workflow_ui.master.after(0, lambda: workflow_ui.mark_step(step, status=status))


def mark_substep(node, substep_name, status):
    global workflow_ui
    if workflow_ui:
        workflow_ui.master.after(0, lambda: workflow_ui.mark_substep(node, substep_name, status=status))


def mark_node_as_graph(parent_node: str, substep_name: str):
    global workflow_ui
    if workflow_ui:
        workflow_ui.master.after(0, lambda: workflow_ui.mark_node_as_graph(parent_node, substep_name))


def run_workflow_logic():
    mark_step(GraphWorkflowVisualizer.PARSE_CLI_ARGS, status=GraphWorkflowVisualizer.CURRENT)

    args = parse_args(sys.argv[1:])

    mark_step(GraphWorkflowVisualizer.PARSE_CLI_ARGS, status=GraphWorkflowVisualizer.DONE)
    mark_step(GraphWorkflowVisualizer.SET_LOGGER_LEVEL, status=GraphWorkflowVisualizer.CURRENT)

    if args.verbose:
        GLOBAL_LOGGER.setLevel(logging.INFO)

    mark_step(GraphWorkflowVisualizer.SET_LOGGER_LEVEL, status=GraphWorkflowVisualizer.DONE)

    mark_step(GraphWorkflowVisualizer.VALIDATE_ARGUMENTS_FILES, status=GraphWorkflowVisualizer.CURRENT)

    if not args.jd_file:
        print("No justification json file provided. Please specify a .json file.", file=sys.stderr)
        mark_step(GraphWorkflowVisualizer.VALIDATE_ARGUMENTS_FILES, status=GraphWorkflowVisualizer.FAIL)
        sys.exit(1)

    if not args.jd_file.endswith('.json'):
        print("The provided justification file is not a .json file.", file=sys.stderr)
        mark_step(GraphWorkflowVisualizer.VALIDATE_ARGUMENTS_FILES, status=GraphWorkflowVisualizer.FAIL)
        sys.exit(1)

    mark_step(GraphWorkflowVisualizer.VALIDATE_ARGUMENTS_FILES, status=GraphWorkflowVisualizer.DONE)
    mark_step(GraphWorkflowVisualizer.INITIALIZE_RUNTIME, status=GraphWorkflowVisualizer.CURRENT)

    runtime = PythonRuntime(libraries=[i for l in args.library
                                       for i in glob.glob(l)])
    mark_step(GraphWorkflowVisualizer.INITIALIZE_RUNTIME, status=GraphWorkflowVisualizer.DONE)

    jpipe = PipelineEngine(config_path=args.config_file,
                           justification_path=args.jd_file,
                           variables=[i.split(':', maxsplit=1) for i in args.variable if i.find(':')],
                           mark_step=mark_step,
                           mark_substep=mark_substep,
                           mark_node_as_graph=mark_node_as_graph)

    diagrams = [(jpipe.justification_name, jpipe.graph)]

    if not diagrams:
        print(f"No justification diagram found: {args.diagram}", file=sys.stderr)
        sys.exit(1)

    # Run justification logic and gather results
    justification_result = list(jpipe.justify(dry_run=args.dry_run, runtime=runtime))

    mark_step(GraphWorkflowVisualizer.SUMMARIZE_RESULTS, status=GraphWorkflowVisualizer.CURRENT)

    m, n, _, s = pretty_display([(jpipe.justification_name, justification_result)])

    mark_step(GraphWorkflowVisualizer.SUMMARIZE_RESULTS, status=GraphWorkflowVisualizer.DONE)

    if args.output:
        mark_step(GraphWorkflowVisualizer.EXPORT_OUTPUT, status=GraphWorkflowVisualizer.CURRENT)
        output_path = args.output.lower()
        if output_path in {"stdout", "stderr"}:
            print("Streamed diagram output is not supported yet.", file=sys.stderr)
            mark_step(GraphWorkflowVisualizer.EXPORT_OUTPUT, status=GraphWorkflowVisualizer.FAIL)
            sys.exit(1)

        status_dict = {item["name"]: item["status"].value for item in justification_result}

        if output_path.endswith(tuple(IMAGE_EXPORT_FORMAT)):
            jpipe.export_to_format(status_dict=status_dict, output_path=args.output,
                                   format=output_path.split('.')[-1])
            print(f"{output_path.split('.')[-1]} diagram saved to: {args.output}", file=sys.stderr)
            mark_step(GraphWorkflowVisualizer.EXPORT_OUTPUT, status=GraphWorkflowVisualizer.DONE)
        else:
            print(f"Unsupported output format: {args.output}", file=sys.stderr)
            mark_step(GraphWorkflowVisualizer.EXPORT_OUTPUT, status=GraphWorkflowVisualizer.FAIL)
            sys.exit(1)

    sys.exit(m - n - s)


def main():
    if "--gui" in sys.argv:
        root = tk.Tk()
        global workflow_ui
        workflow_ui = GraphWorkflowVisualizer(root)

        root.after(300, lambda: threading.Thread(target=run_workflow_logic, daemon=True).start())

        root.mainloop()
    else:
        run_workflow_logic()


if __name__ == '__main__':
    main()
