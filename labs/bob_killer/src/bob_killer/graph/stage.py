"""The ``graph`` stage: load a GraphInput for a run, build the CellGraph, save it.

Nothing registers at import time. The host calls ``register_stages`` once it can supply the
run's input and output (``GraphIO``); calling it again is a no-op.
"""

from __future__ import annotations

from typing import Final, Protocol

from bob_killer import registry
from bob_killer.contracts.graph import CellGraph, GraphInput
from bob_killer.graph.dag import build_graph
from bob_killer.registry import Stage

STAGE_NAME: Final = "graph"


class GraphIO(Protocol):
    def load_graph_input(self, run_id: str) -> GraphInput: ...

    def save_cell_graph(self, run_id: str, graph: CellGraph) -> None: ...


def graph_stage(io: GraphIO) -> Stage:
    def run(run_id: str) -> None:
        io.save_cell_graph(run_id, build_graph(io.load_graph_input(run_id)))

    return run


def register_stages(io: GraphIO) -> None:
    if STAGE_NAME not in registry.stages:
        registry.stages.add(STAGE_NAME, graph_stage(io))
