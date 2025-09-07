from __future__ import annotations

from functools import wraps
from typing import (
    Any,
    Callable,
    Concatenate,
    Dict,
    List,
    Type,
    Union,
    get_type_hints,
)

from graphviz import Digraph
from typing_extensions import Annotated, ParamSpec, TypeVar, get_args, get_origin


class BaseState:
    """Base class for all states in the state machine."""

    pass


class BaseAction:
    """Base class for all actions in the state machine."""

    pass


MachineT = TypeVar("MachineT")
StateT = TypeVar("StateT", bound=BaseState)
ActionT = TypeVar("ActionT", bound=BaseAction)
P = ParamSpec("P")
ReturnStateT = TypeVar("ReturnStateT", bound=BaseState)


def transition(
    func: Callable[Concatenate[MachineT, StateT, ActionT, P], ReturnStateT],
) -> Callable[Concatenate[MachineT, StateT, ActionT, P], ReturnStateT]:
    """Decorator to mark methods as transitions and add runtime validation."""
    func.__is_transition__ = True

    @wraps(func)
    def wrapper(self, state, action, *args, **kwargs):
        transitions = type(self)._transitions
        for trans in transitions:
            if trans["func"] is wrapper:
                if not any(isinstance(state, s) for s in trans["sources"]):
                    raise ValueError(
                        f"Invalid state {state.__class__.__name__} for {func.__name__}, "
                        f"expected one of {[s.__name__ for s in trans['sources']]}"
                    )
                if not any(isinstance(action, a) for a in trans["actions"]):
                    raise ValueError(
                        f"Invalid action {action.__class__.__name__} for {func.__name__}, "
                        f"expected one of {[a.__name__ for a in trans['actions']]}"
                    )
                break
        else:
            raise ValueError(
                f"Function {func.__name__} not found in {type(self).__name__}._transitions"
            )

        return func(self, state, action, *args, **kwargs)

    return wrapper


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

    def transition_map(self) -> List[Dict[str, Any]]:
        return self._transitions

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
