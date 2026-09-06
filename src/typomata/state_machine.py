from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import wraps
from html import escape
from inspect import (
    Parameter,
    Signature,
    isasyncgenfunction,
    iscoroutinefunction,
    isfunction,
    isgeneratorfunction,
    signature,
)
from types import UnionType
from typing import Any, Callable, Dict, List, Type, Union, get_type_hints

from graphviz import Digraph
from typing_extensions import (
    Annotated,
    Concatenate,
    ParamSpec,
    TypeVar,
    get_args,
    get_origin,
)


class BaseState:
    """Base class for all states in the state machine."""


class BaseAction:
    """Base class for all actions in the state machine."""


MachineT = TypeVar("MachineT")
StateT = TypeVar("StateT", bound=BaseState)
ActionT = TypeVar("ActionT", bound=BaseAction)
P = ParamSpec("P")
ReturnStateT = TypeVar("ReturnStateT", bound=BaseState)


@dataclass(frozen=True)
class _AnnotationMember:
    type: type
    metadata: tuple[Any, ...]


def _method_signature(func: Callable[..., Any]) -> Signature:
    # Binding does not need annotation values. Resolve them at class creation,
    # where failures can include the machine and method names.
    if sys.version_info >= (3, 14):
        from annotationlib import Format

        return signature(func, annotation_format=Format.STRING)
    return signature(func)


def _normalize_annotation(
    hint: Any,
    base: type,
    context: str,
    metadata: tuple[Any, ...] = (),
) -> tuple[_AnnotationMember, ...]:
    origin = get_origin(hint)
    if origin is Annotated:
        inner, *extras = get_args(hint)
        return _normalize_annotation(inner, base, context, metadata + tuple(extras))
    if origin in (Union, UnionType):
        return tuple(
            member
            for argument in get_args(hint)
            for member in _normalize_annotation(argument, base, context, metadata)
        )
    if (
        not isinstance(hint, type)
        or hint is Any
        or not issubclass(hint, base)
        or getattr(hint, "_is_protocol", False)
    ):
        raise TypeError(
            f"{context}: unsupported annotation {hint!r}; expected "
            f"a {base.__name__} subclass, a union, or Annotated"
        )
    return (_AnnotationMember(hint, metadata),)


def _transition_definition(
    owner: type, name: str, decorated: Callable[..., Any]
) -> Dict[str, Any]:
    context = f"{owner.__qualname__}.{name}"
    original = getattr(decorated, "__wrapped__")
    if not isfunction(original):
        raise TypeError(f"{context}: a transition must be an instance method")
    if (
        iscoroutinefunction(original)
        or isgeneratorfunction(original)
        or isasyncgenfunction(original)
    ):
        raise TypeError(
            f"{context}: a transition must be a synchronous, non-generator method"
        )
    parameters = tuple(_method_signature(original).parameters.values())
    if len(parameters) != 3 or any(
        parameter.kind not in (Parameter.POSITIONAL_ONLY, Parameter.POSITIONAL_OR_KEYWORD)
        or parameter.default is not Parameter.empty
        for parameter in parameters
    ):
        raise TypeError(
            f"{context}: invalid signature; expected exactly three required positional "
            "parameters (receiver, state, action)"
        )
    try:
        hints = get_type_hints(original, localns=dict(vars(owner)), include_extras=True)
    except Exception as error:
        raise TypeError(f"{context}: cannot resolve annotations: {error}") from error

    annotations = {}
    members = {}
    for role, parameter_name, base in (
        ("state", parameters[1].name, BaseState),
        ("action", parameters[2].name, BaseAction),
        ("return", "return", BaseState),
    ):
        if parameter_name not in hints:
            raise TypeError(f"{context}: missing {role} annotation")
        annotations[role] = hints[parameter_name]
        members[role] = _normalize_annotation(
            hints[parameter_name], base, f"{context} {role}"
        )

    destinations = tuple(dict.fromkeys(member.type for member in members["return"]))
    destination_hint = annotations["return"]
    outer_metadata = (
        get_args(destination_hint)[1:]
        if get_origin(destination_hint) is Annotated else ()
    )
    return {
        "sources": tuple(dict.fromkeys(member.type for member in members["state"])),
        "actions": tuple(dict.fromkeys(member.type for member in members["action"])),
        "destinations": destinations,
        "func": decorated,
        "name": context,
        "annotations": annotations,
        "metadata": "\n".join(item for item in outer_metadata if isinstance(item, str)),
        "destination_metadata": {
            destination: tuple(
                item
                for member in members["return"]
                if member.type is destination
                for item in member.metadata
                if isinstance(item, str)
            )
            for destination in destinations
        },
    }


def transition(
    func: Callable[Concatenate[MachineT, StateT, ActionT, P], ReturnStateT],
) -> Callable[Concatenate[MachineT, StateT, ActionT, P], ReturnStateT]:
    """Mark an instance method as a transition with input and result validation."""
    call_signature = _method_signature(func) if isfunction(func) else None

    @wraps(func)
    def wrapper(*args, **kwargs):
        if call_signature is None:
            raise TypeError("A transition must be an instance method")
        bound = call_signature.bind(*args, **kwargs)
        receiver, state, action = bound.arguments.values()
        for definition in type(receiver)._transitions:
            if definition["func"] is wrapper:
                break
        else:
            raise ValueError(
                f"Function {func.__name__} not found in {type(receiver).__name__}._transitions"
            )
        for value, role, allowed in (
            (state, "state", definition["sources"]),
            (action, "action", definition["actions"]),
        ):
            if not isinstance(value, allowed):
                raise ValueError(
                    f"Invalid {role} {type(value).__name__} for {func.__name__}, "
                    f"expected one of {[item.__name__ for item in allowed]}"
                )
        result = func(*args, **kwargs)
        if not isinstance(result, definition["destinations"]):
            raise ValueError(
                f"Invalid result {type(result).__name__} for {definition['name']}, "
                f"expected one of {[item.__name__ for item in definition['destinations']]}"
            )
        return result

    setattr(wrapper, "__is_transition__", True)
    return wrapper


def _is_transition(member: Any) -> bool:
    return bool(getattr(member, "__is_transition__", False))


class BaseStateMachine:
    """Base class for creating state machines using type hints and annotations."""

    _transitions: List[Dict[str, Any]] = []

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        members: dict[str, tuple[type, Any]] = {}
        for owner in cls.__mro__:
            for name, member in vars(owner).items():
                members.setdefault(name, (owner, member))

        definitions = []
        for name in sorted(members):
            owner, member = members[name]
            if isinstance(member, (staticmethod, classmethod, property)):
                underlying = (
                    member.fget if isinstance(member, property) else member.__func__
                )
                if _is_transition(underlying):
                    raise TypeError(
                        f"{cls.__qualname__}.{name}: a transition must be an instance method"
                    )
            elif _is_transition(member):
                definitions.append(_transition_definition(owner, name, member))
        cls._transitions = definitions

    def transition_map(self) -> List[Dict[str, Any]]:
        return self._transitions

    def run(self, state: BaseState, action: BaseAction) -> BaseState:
        """Run the state machine with the given state and action."""
        for definition in self.__class__._transitions:
            if isinstance(action, definition["actions"]) and isinstance(
                state, definition["sources"]
            ):
                return definition["func"](self, state, action)
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
                    label = f"<<FONT POINT-SIZE='12'>{escape(action_name)}</FONT>"
                    for text in t["destination_metadata"][dest]:
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
