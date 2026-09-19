from __future__ import annotations

from collections import Counter
from html import escape
from typing import Type

from .state_machine import BaseState, BaseStateMachine


def generate_state_machine_diagram(
    state_machine_class: Type[BaseStateMachine], filename: str = "state_machine_diagram"
) -> None:
    """Generate a state machine diagram using Graphviz with annotated edge conditions."""
    try:
        from graphviz import Digraph
    except ModuleNotFoundError as exc:
        if exc.name != "graphviz":
            raise
        raise ModuleNotFoundError(
            "Diagram generation requires Graphviz: install 'typomata[diagrams]' "
            "(from a checkout: uv sync --extra diagrams). "
            "Rendering also requires the system Graphviz dot executable.",
            name="graphviz",
        ) from exc

    transitions = state_machine_class._transitions
    dot = Digraph(comment="State Machine")

    font_family = "DejaVu Sans"
    dot.attr(fontname=font_family)

    # Assign IDs in declaration traversal order, independently of display names.
    state_ids: dict[type[BaseState], str] = {}
    for t in transitions:
        for state in (*t.sources, *t.destinations):
            if state not in state_ids:
                state_ids[state] = f"state_{len(state_ids)}"

    name_counts = Counter(state.__name__ for state in state_ids)
    for index, (state, node_id) in enumerate(state_ids.items()):
        label = state.__name__
        if name_counts[label] > 1:
            label = f"{label} ({index + 1})"
        dot.node(node_id, label=label, fontname=font_family)

    # Add transitions as edges
    for t in transitions:
        for source in t.sources:
            for action in t.actions:
                action_name = action.__name__
                for dest in t.destinations:

                    # Prepare multi-line label for the edge
                    label = f"<<FONT POINT-SIZE='12'>{escape(action_name)}</FONT>"
                    for text in t.destination_metadata[dest]:
                        for line in text.split("\n"):
                            label += f"<BR/><FONT POINT-SIZE='10'>{escape(line)}</FONT>"
                    label += ">"

                    dot.edge(
                        state_ids[source],
                        state_ids[dest],
                        label=label,
                        fontname=font_family,
                        fontsize="12",
                    )

    dot.render(f"{filename}.gv", view=False)
