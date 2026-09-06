from __future__ import annotations

from html import escape
from typing import Type

from .state_machine import BaseStateMachine


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

    # Collect unique state names
    state_names = set()
    for t in transitions:
        for source in t.sources:
            state_names.add(source.__name__)
        for dest in t.destinations:
            state_names.add(dest.__name__)

    # Add states as nodes
    for state_name in state_names:
        dot.node(state_name, fontname=font_family)

    # Add transitions as edges
    for t in transitions:
        for source in t.sources:
            source_name = source.__name__
            for action in t.actions:
                action_name = action.__name__
                for dest in t.destinations:
                    dest_name = dest.__name__

                    # Prepare multi-line label for the edge
                    label = f"<<FONT POINT-SIZE='12'>{escape(action_name)}</FONT>"
                    for text in t.destination_metadata[dest]:
                        for line in text.split("\n"):
                            label += f"<BR/><FONT POINT-SIZE='10'>{escape(line)}</FONT>"
                    label += ">"

                    dot.edge(
                        source_name,
                        dest_name,
                        label=label,
                        fontname=font_family,
                        fontsize="12",
                    )

    dot.render(f"{filename}.gv", view=False)
