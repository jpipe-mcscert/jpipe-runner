import networkx as nx

try:
    import tkinter as tk
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
    from matplotlib.patches import Patch
    GUI_AVAILABLE = True
except ImportError:
    GUI_AVAILABLE = False
    tk = None
    plt = None


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
    PREPARE_OUTPUT_PATH = "Prepare output path"
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

    def __init__(self, master):
        if not GUI_AVAILABLE:
            raise ImportError("GUI dependencies not available. Install with: pip install jpipe-runner[gui]")
        print("Initializing GraphWorkflowVisualizer...")
        self.master = master
        self.master.title("Project Workflow Graph")
        self.mode = GraphWorkflowVisualizer.GRAPH
        self.current_node = None
        self.current_path = []

        self.G = nx.DiGraph()
        self.G.add_nodes_from(GraphWorkflowVisualizer.workflow_nodes)
        self.G.add_edges_from(GraphWorkflowVisualizer.workflow_edges)
        self.pos = nx.spring_layout(self.G, seed=42, k=0.25)

        self.fig, self.ax = plt.subplots(figsize=(9, 6))
        self.canvas = FigureCanvasTkAgg(self.fig, master=self.master)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self.status = {node: GraphWorkflowVisualizer.IDLE for node in GraphWorkflowVisualizer.workflow_nodes}
        self.subgraphs = {}
        self.substatus = {}
        self.subgraph_nodes = {}

        self.master.protocol("WM_DELETE_WINDOW", self.on_close)

        self.fig.canvas.mpl_connect("button_press_event", self.on_click)
        self.master.bind("<Escape>", lambda e: self.back_one_level())

        self.close_button = tk.Button(master=self.master, text="Close", command=self.master.quit)
        self.close_button.pack(side="bottom", pady=10)

        self.detail_frame = None

        self.draw_graph()
        print("GraphWorkflowVisualizer initialized with nodes and edges.")

    def draw_graph(self):
        self.ax.clear()
        node_colors = [GraphWorkflowVisualizer.color_map.get(self.status[n], "gray") for n in self.G.nodes()]

        nx.draw(
            self.G,
            pos=self.pos,
            with_labels=True,
            node_color=node_colors,
            node_size=2000,
            font_size=9,
            font_weight='bold',
            arrows=True,
            ax=self.ax
        )
        self.draw_legend()
        self.ax.set_title("Project Workflow Execution", fontsize=14)
        self.canvas.draw()

    def mark_step(self, step_name: str, status: str = DONE):
        if step_name in self.status:
            self.status[step_name] = status
            if self.mode == GraphWorkflowVisualizer.GRAPH:
                self.draw_graph()

    def mark_substep(self, node: str, substep_name: str, status: str):
        if node not in self.subgraphs:
            self.subgraphs[node] = nx.DiGraph()
            self.substatus[node] = {}

        G = self.subgraphs[node]
        G.add_node(substep_name)

        if self.substatus[node] and substep_name not in self.substatus[node]:
            last_substep = list(self.substatus[node].keys())[-1]
            G.add_edge(last_substep, substep_name)

        self.substatus[node][substep_name] = status

        if self.mode == GraphWorkflowVisualizer.DETAIL and self.current_node == node:
            self.show_node_detail(node)

    def mark_node_as_graph(self, parent_node: str, substep_name: str):
        if parent_node not in self.subgraph_nodes:
            self.subgraph_nodes[parent_node] = set()
        self.subgraph_nodes[parent_node].add(substep_name)

    def on_click(self, event):
        if self.mode == GraphWorkflowVisualizer.GRAPH:
            for node, (x, y) in self.pos.items():
                x_disp, y_disp = self.ax.transData.transform((x, y))
                dist = ((event.x - x_disp) ** 2 + (event.y - y_disp) ** 2) ** 0.5
                if dist < 25:
                    self.show_node_detail(node)
                    break
        elif self.mode == GraphWorkflowVisualizer.DETAIL:
            subgraph = self.subgraphs.get(self.current_node)
            if not subgraph:
                return

            pos = nx.spring_layout(subgraph, seed=3)
            for node, (x, y) in pos.items():
                x_disp, y_disp = self.ax.transData.transform((x, y))
                dist = ((event.x - x_disp) ** 2 + (event.y - y_disp) ** 2) ** 0.5
                if dist < 25:
                    if node in self.subgraph_nodes.get(self.current_node, set()):
                        self.show_node_detail(node, parent_path=self.current_path)
                    break

    def show_node_detail(self, node, parent_path=None):
        self.mode = GraphWorkflowVisualizer.DETAIL
        self.current_node = node

        if parent_path is None:
            self.current_path = [node]
        else:
            self.current_path = parent_path + [node]

        self.ax.clear()

        subgraph = self.subgraphs.get(node)
        substatus = self.substatus.get(node, {})

        if subgraph:
            pos = nx.spring_layout(subgraph, seed=3)
            node_colors = []
            for n in subgraph.nodes():
                st = substatus.get(n, GraphWorkflowVisualizer.IDLE)
                node_colors.append(GraphWorkflowVisualizer.color_map.get(st, 'gray'))

            nx.draw(
                subgraph, pos,
                with_labels=True,
                node_color=node_colors,
                node_size=1200,
                font_size=9,
                font_weight='bold',
                arrows=True,
                ax=self.ax
            )
            self.draw_legend()
            self.ax.set_title(f"Subgraph for: {' > '.join(self.current_path)}", fontsize=14)
        else:
            self.ax.set_title(f"No substeps defined for: {node}", fontsize=14)

        self.canvas.draw()

        if not self.detail_frame:
            self.detail_frame = tk.Frame(self.master)
            self.detail_frame.pack(pady=10)
            back_btn = tk.Button(self.detail_frame, text="⬅ Back", command=self.back_one_level)
            back_btn.pack()

    def back_to_graph(self):
        self.mode = GraphWorkflowVisualizer.GRAPH
        self.current_node = None
        if self.detail_frame:
            self.detail_frame.pack_forget()
            self.detail_frame = None
        self.draw_graph()

    def back_one_level(self):
        if len(self.current_path) <= 1:
            self.current_path = []
            self.back_to_graph()
        else:
            self.current_path.pop()  # Remove current
            prev_node = self.current_path[-1]
            self.show_node_detail(prev_node, parent_path=self.current_path[:-1])

    def draw_legend(self):
        legend_elements = [
            Patch(facecolor='lightgray', label='Idle'),
            Patch(facecolor='#1E90FF', label='Current'),
            Patch(facecolor='limegreen', label='Done'),
            Patch(facecolor='red', label='Fail'),
            Patch(facecolor='gold', label='Skipped'),
        ]
        self.ax.legend(handles=legend_elements, loc='lower right')

    def on_close(self):
        self.master.quit()
        self.master.destroy()
