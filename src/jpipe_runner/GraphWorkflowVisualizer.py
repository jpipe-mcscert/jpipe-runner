#import tkinter as tk

#import matplotlib.pyplot as plt
#import networkx as nx
#from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
#from matplotlib.patches import Patch


class GraphWorkflowVisualizer:
    # Workflow steps
    PARSE_CLI_ARGS = "Parse CLI arguments"
    SET_LOGGER_LEVEL = "Set logger level"
    INITIALIZE_RUNTIME = "Initialize runtime"
    VALIDATE_ARGUMENTS_FILES = "Validate arguments files"
    VALIDATE_JUSTIFICATION_FILE = "Validate justification file"
    LOAD_CONFIGURATION = "Load configuration"
    LOAD_JUSTIFICATION_FILE = "Load justification file"
    PARSE_JUSTIFICATION_GRAPH = "Parse justification graph"
    REGISTER_DECORATORS = "Register decorators"
    VALIDATE_PIPELINE = "Validate pipeline"
    EXECUTE_JUSTIFICATION = "Execute justification"
    SUMMARIZE_RESULTS = "Summarize results"
    EXPORT_OUTPUT = "Export output"

    # Substeps VALIDATE_JUSTIFICATION_FILE
    VALIDATE_STRUCTURE_ELEMENTS = "Validate structure of elements"
    VALIDATE_RELATIONS_STRUCTURES = "Validate relations structure"
    EXTRACTING_JUSTIFICATION_NAME = "Extracting justification name"

    # PARSE_JUSTIFICATION_GRAPH
    ADDING_NODE_TO_GRAPH = "Adding node to graph"
    ADDING_EDGES_TO_GRAPH = "Adding edges to graph"

    # EXECUTE_JUSTIFICATION
    FETCH_EXECUTION_ORDER = "Fetch execution order"
    CALL_FUNCTION = "Call function"
    CHECK_RETURN_TYPE = "Check return type"
    HANDLE_RESULT_STATUS = "Handle result status"

    # EXPORT_OUTPUT
    IMPORTING_PYGRAPHVIZ = "Importing pygraphviz"
    PREPARE_STYLES = "Prepare styles"
    CREATE_GRAPH = "Create graph"
    STYLE_NODES = "Style nodes"
    STYLE_EDGES = "Style edges"
    DRAW_GRAPH = "Draw graph"

    # Statuses
    CURRENT = "current"
    DONE = "done"
    FAIL = "fail"
    IDLE = "idle"
    SKIP = "skip"

    # Modes
    GRAPH = "graph"
    DETAIL = "detail"

    workflow_nodes = [
        PARSE_CLI_ARGS,
        SET_LOGGER_LEVEL,
        INITIALIZE_RUNTIME,
        VALIDATE_ARGUMENTS_FILES,
        VALIDATE_JUSTIFICATION_FILE,
        LOAD_CONFIGURATION,
        LOAD_JUSTIFICATION_FILE,
        PARSE_JUSTIFICATION_GRAPH,
        REGISTER_DECORATORS,
        VALIDATE_PIPELINE,
        EXECUTE_JUSTIFICATION,
        SUMMARIZE_RESULTS,
        EXPORT_OUTPUT
    ]

    workflow_edges = [
        (PARSE_CLI_ARGS, SET_LOGGER_LEVEL),
        (SET_LOGGER_LEVEL, VALIDATE_ARGUMENTS_FILES),
        (VALIDATE_ARGUMENTS_FILES, INITIALIZE_RUNTIME),
        (INITIALIZE_RUNTIME, LOAD_CONFIGURATION),
        (LOAD_CONFIGURATION, LOAD_JUSTIFICATION_FILE),
        (LOAD_JUSTIFICATION_FILE, VALIDATE_JUSTIFICATION_FILE),
        (VALIDATE_JUSTIFICATION_FILE, PARSE_JUSTIFICATION_GRAPH),
        (PARSE_JUSTIFICATION_GRAPH, REGISTER_DECORATORS),
        (REGISTER_DECORATORS, VALIDATE_PIPELINE),
        (VALIDATE_PIPELINE, EXECUTE_JUSTIFICATION),
        (EXECUTE_JUSTIFICATION, SUMMARIZE_RESULTS),
        (SUMMARIZE_RESULTS, EXPORT_OUTPUT)
    ]

    color_map = {
        IDLE: "lightgray",
        CURRENT: "#1E90FF",
        DONE: "limegreen",
        FAIL: "red",
        SKIP: "gold"
    }
