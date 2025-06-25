from collections import deque
from typing import Iterable, Optional, Callable, Any

import networkx as nx

from jpipe_runner.enums import VariableType
from jpipe_runner.exceptions import JustificationTraverseException


class Justification(nx.DiGraph):
    node_attr_map = {
        VariableType.CONCLUSION: dict(fillcolor="lightgrey",
                                      shape="rect",
                                      style="filled"),
        VariableType.STRATEGY: dict(fillcolor="palegreen",
                                    shape="parallelogram",
                                    style="filled"),
        VariableType.SUB_CONCLUSION: dict(color="dodgerblue",
                                          shape="rect"),
        VariableType.EVIDENCE: dict(fillcolor="lightskyblue2",
                                    shape="rect",
                                    style="filled"),
        VariableType.SUPPORT: dict(fillcolor="lightcoral",
                                   shape="rect",
                                   style="filled"),
    }

    def layered_traverse(self,
                         callback: Optional[Callable[[str, dict], bool]] = None,
                         ) -> None:

        if callback is None:
            callback = lambda n, d: True

        # start with all evidence nodes.
        start_nodes = (n for n in self.nodes(data=False) if self.in_degree(n) == 0)

        visited = set()
        queue = deque(start_nodes)

        while queue:
            node = queue.popleft()

            # node already visited.
            if node in visited:
                continue

            # run callback function.
            if not callback(node, self.nodes[node]):
                raise JustificationTraverseException(
                    f"callback returns false when traversing to '{node}'")

            # save visited node.
            visited.add(node)

            # check successor nodes.
            for child in self.successors(node):
                all_parents_visited = True
                for parent in self.predecessors(child):
                    if parent not in visited:
                        all_parents_visited = False
                        break

                if all_parents_visited and child not in visited:
                    queue.append(child)  # ready to enqueue.

        assert len(visited) == len(self.nodes)

    def export_to_image(self,
                        path: Optional[Any] = None,
                        format: Optional[str] = None,
                        ) -> bytes | None:
        try:
            from networkx.drawing.nx_agraph import to_agraph
        except ImportError as e:
            raise ImportError("pygraphviz is required to enable this feature") from e

        agraph = to_agraph(self)

        agraph.graph_attr.update(
            size="5",
            rankdir="BT",  # Bottom-to-Top
            dpi="500",
            label=self.name,
            fontsize="15",
            labelloc="bottem"
        )
        agraph.edge_attr.update(
            color="black",
            arrowhead="normal",
        )

        for n, d in self.nodes(data=True):
            attr = self.node_attr_map[d["var_type"]]
            agraph_node = agraph.get_node(n)
            agraph_node.attr.update({
                (k, v)
                for k, v in attr.items()
                if v is not None
            })

        return agraph.draw(path=path, format=format, prog="dot")
