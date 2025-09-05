from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    List,
    ParamSpec,
    Type,
    TypeVar,
    Union,
    get_type_hints,
)
from typing_extensions import (
    get_args,
    get_origin,
    Annotated,
)
from graphviz import Digraph

T = TypeVar("T")
P = ParamSpec("P")


class BaseState:
    """Base class for all states in the state machine."""

    pass


class BaseAction:
    """Base class for all actions in the state machine."""

    pass


def transition(func: Callable[P, T]) -> Callable[P, T]:
    """Decorator to mark methods as transitions."""
    func.__is_transition__ = True
    return func


class BaseStateMachine:
    """Base class for creating state machines using type hints and annotations."""

    _transitions: List[Dict[str, Any]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        cls._transitions = []
        for attr_name in dir(cls):
            attr_value = getattr(cls, attr_name)
            if callable(attr_value) and hasattr(attr_value, "__is_transition__"):
                hints = get_type_hints(attr_value)
                source_hint = hints.get("state")
                action_hint = hints.get("action")
                dest_hint = hints.get("return")

                # Process Annotated types to extract metadata
                dest_metadata = ""
                if get_origin(dest_hint) is Annotated:
                    dest_hint, *metadata = get_args(dest_hint)
                    dest_metadata = metadata[0] if metadata else ""

                if source_hint and action_hint and dest_hint:
                    # Handle Union types in source_hint
                    if (
                        hasattr(source_hint, "__origin__")
                        and source_hint.__origin__ is Union
                    ):
                        sources = source_hint.__args__
                    else:
                        sources = (source_hint,)

                    # Handle Union types in action_hint
                    if (
                        hasattr(action_hint, "__origin__")
                        and action_hint.__origin__ is Union
                    ):
                        actions = action_hint.__args__
                    else:
                        actions = (action_hint,)

                    # Handle Union types in dest_hint
                    if (
                        hasattr(dest_hint, "__origin__")
                        and dest_hint.__origin__ is Union
                    ):
                        destinations = dest_hint.__args__
                    else:
                        destinations = (dest_hint,)

                    cls._transitions.append(
                        {
                            "sources": sources,
                            "actions": actions,
                            "destinations": destinations,
                            "func": attr_value,
                            "metadata": dest_metadata,  # Store the edge metadata
                        }
                    )

    def run(self, state: BaseState, action: BaseAction) -> BaseState:
        """Run the state machine with the given state and action."""
        for trans in self.__class__._transitions:
            if any(isinstance(action, action_type) for action_type in trans["actions"]):
                if any(isinstance(state, source) for source in trans["sources"]):
                    return trans["func"](self, state, action)
        raise ValueError(f"Invalid transition from {state} with {action}")


def generate_state_machine_diagram(
    state_machine_class: Type[BaseStateMachine], filename: str = "state_machine_diagram"
):
    """Generate a state machine diagram using Graphviz with annotated edge conditions."""
    transitions = state_machine_class._transitions
    dot = Digraph(comment="State Machine")

    font_family = "DejaVu Sans"
    dot.attr(fontname=font_family)

    # Collect unique state names
    state_names = set()
    for t in transitions:
        for source in t["sources"]:
            state_names.add(source.__name__)
        for dest in t["destinations"]:
            state_names.add(dest.__name__)

    # Add states as nodes
    for state_name in state_names:
        dot.node(state_name, fontname=font_family)

    # Add transitions as edges
    for t in transitions:
        for source in t["sources"]:
            source_name = source.__name__
            for action in t["actions"]:
                action_name = action.__name__
                for dest in t["destinations"]:
                    dest_name = dest.__name__

                    # Prepare multi-line label for the edge
                    label = f"<<FONT POINT-SIZE='12'>{action_name}</FONT>"
                    if t["metadata"]:
                        label += f"<BR/><FONT POINT-SIZE='10'>{t['metadata']}</FONT>>"
                    else:
                        label += ">"

                    dot.edge(
                        source_name,
                        dest_name,
                        label=label,
                        fontname=font_family,
                        fontsize="12",
                    )

    dot.render(f"{filename}.gv", view=False)
