from __future__ import annotations

import sys
from dataclasses import dataclass
from functools import wraps
from inspect import (
    Parameter,
    Signature,
    isasyncgenfunction,
    iscoroutinefunction,
    isfunction,
    isgeneratorfunction,
    signature,
)
from types import MappingProxyType, UnionType
from typing import Any, Callable, Mapping, Type, Union, cast, get_type_hints

from typing_extensions import (
    Annotated,
    ParamSpec,
    TypeVar,
    get_args,
    get_origin,
)


class BaseState:
    """Base class for all states in the state machine."""


class BaseAction:
    """Base class for all actions in the state machine."""


P = ParamSpec("P")
ReturnStateT = TypeVar("ReturnStateT", bound=BaseState)


@dataclass(frozen=True)
class _AnnotationMember:
    type: type
    metadata: tuple[Any, ...]


@dataclass(frozen=True)
class _TransitionDefinition:
    sources: tuple[type, ...]
    actions: tuple[type, ...]
    destinations: tuple[type, ...]
    func: Callable[..., BaseState]
    original: Callable[..., BaseState]
    name: str
    annotations: Mapping[str, Any]
    metadata: str
    destination_metadata: Mapping[type, tuple[str, ...]]

    def matches(self, state: object, action: object) -> bool:
        return isinstance(state, self.sources) and isinstance(action, self.actions)

    def invoke(self, receiver: object, state: object, action: object) -> BaseState:
        for value, role, allowed in (
            (state, "state", self.sources),
            (action, "action", self.actions),
        ):
            if not isinstance(value, allowed):
                raise ValueError(
                    f"Invalid {role} {type(value).__name__} for {self.original.__name__}, "
                    f"expected one of {[item.__name__ for item in allowed]}"
                )
        result = self.original(receiver, state, action)
        if not isinstance(result, self.destinations):
            raise ValueError(
                f"Invalid result {type(result).__name__} for {self.name}, "
                f"expected one of {[item.__name__ for item in self.destinations]}"
            )
        return result

    def snapshot(self) -> dict[str, Any]:
        return {
            "sources": self.sources,
            "actions": self.actions,
            "destinations": self.destinations,
            "func": self.func,
            "name": self.name,
            "annotations": dict(self.annotations),
            "metadata": self.metadata,
            "destination_metadata": dict(self.destination_metadata),
        }


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
) -> _TransitionDefinition:
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
    return _TransitionDefinition(
        sources=tuple(dict.fromkeys(member.type for member in members["state"])),
        actions=tuple(dict.fromkeys(member.type for member in members["action"])),
        destinations=destinations,
        func=decorated,
        original=original,
        name=context,
        annotations=MappingProxyType(annotations),
        metadata="\n".join(item for item in outer_metadata if isinstance(item, str)),
        destination_metadata=MappingProxyType({
            destination: tuple(
                item
                for member in members["return"]
                if member.type is destination
                for item in member.metadata
                if isinstance(item, str)
            )
            for destination in destinations
        }),
    )


def transition(
    func: Callable[P, ReturnStateT],
) -> Callable[P, ReturnStateT]:
    """Mark an instance method as a transition with input and result validation."""
    call_signature = _method_signature(func) if isfunction(func) else None
    definitions: dict[type, _TransitionDefinition] = {}

    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> ReturnStateT:
        if call_signature is None:
            raise TypeError("A transition must be an instance method")
        bound = call_signature.bind(*args, **kwargs)
        receiver, state, action = bound.arguments.values()
        for owner in type(receiver).__mro__:
            if owner in definitions:
                # invoke validates the result against this method's declared
                # destinations before restoring its specific static type.
                return cast(
                    ReturnStateT, definitions[owner].invoke(receiver, state, action)
                )
        raise ValueError(
            f"Function {func.__name__} is not registered for {type(receiver).__qualname__}"
        )

    setattr(wrapper, "__is_transition__", True)
    setattr(wrapper, "__transition_definitions__", definitions)
    return wrapper


def _is_transition(member: Any) -> bool:
    return bool(getattr(member, "__is_transition__", False))


def _method_definitions(method: Callable[..., Any]) -> dict[type, _TransitionDefinition]:
    return cast(
        dict[type, _TransitionDefinition],
        getattr(method, "__transition_definitions__"),
    )


class BaseStateMachine:
    """Base class for creating state machines using type hints and annotations."""

    _transitions: tuple[_TransitionDefinition, ...] = ()

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)
        members: dict[str, tuple[type, Any]] = {}
        for owner in cls.__mro__:
            for name, member in vars(owner).items():
                members.setdefault(name, (owner, member))

        definitions: dict[tuple[type, Callable[..., Any]], _TransitionDefinition] = {}
        # Resolve base declarations first, including shadowed mixin methods
        # that may be called through super(). Aliases reuse their definition.
        for owner in reversed(cls.__mro__):
            for name, member in sorted(vars(owner).items()):
                if isinstance(member, (staticmethod, classmethod, property)):
                    underlying = (
                        member.fget if isinstance(member, property) else member.__func__
                    )
                    if _is_transition(underlying):
                        raise TypeError(
                            f"{owner.__qualname__}.{name}: "
                            "a transition must be an instance method"
                        )
                elif _is_transition(member):
                    key = (owner, member)
                    if key not in definitions:
                        registered = _method_definitions(member)
                        definition = None
                        for base in owner.__mro__:
                            definition = definitions.get((base, member), registered.get(base))
                            if definition is not None:
                                break
                        if definition is None:
                            definition = _transition_definition(owner, name, member)
                        definitions[key] = definition

        # A wrapper cannot distinguish two declarations for the same function
        # on one receiver. Reject that combination instead of validating a
        # direct parent call against a different parent's annotations.
        shared_methods: dict[Callable[..., Any], _TransitionDefinition] = {}
        for definition in definitions.values():
            prior = shared_methods.get(definition.func)
            if prior is not None and prior is not definition:
                raise TypeError(
                    f"{cls.__qualname__}: conflicting definitions for a shared "
                    f"decorated method: {prior.name} and {definition.name}; "
                    "declare separate transition methods"
                )
            shared_methods[definition.func] = definition

        # Aliases and diamond inheritance can expose the same definition more
        # than once. Only names visible through the MRO enter dispatch.
        unique_definitions: dict[int, _TransitionDefinition] = {}
        for name in sorted(members):
            owner, member = members[name]
            if _is_transition(member):
                definition = definitions[owner, member]
                unique_definitions[id(definition)] = definition
        pairs: dict[tuple[type, type], _TransitionDefinition] = {}
        for definition in unique_definitions.values():
            for source in definition.sources:
                for action in definition.actions:
                    previous = pairs.get((source, action))
                    if previous is not None:
                        raise TypeError(
                            f"{cls.__qualname__}: duplicate transition for "
                            f"{source.__qualname__} with {action.__qualname__}: "
                            f"{previous.name} and {definition.name}"
                        )
                    pairs[source, action] = definition

        # Publish only after all declarations pass validation. Inherited methods
        # retain the annotation resolution of their defining class.
        for (owner, method), definition in definitions.items():
            _method_definitions(method)[owner] = definition
        cls._transitions = tuple(unique_definitions.values())

    def transition_map(self) -> list[dict[str, Any]]:
        """Return independent registry containers with the declared types and methods."""
        return [definition.snapshot() for definition in self._transitions]

    def run(self, state: BaseState, action: BaseAction) -> BaseState:
        """Run the state machine with the given state and action."""
        matches = [
            definition for definition in self._transitions
            if definition.matches(state, action)
        ]
        context = (
            f"{type(self).__qualname__} from {type(state).__qualname__} "
            f"with {type(action).__qualname__}"
        )
        if not matches:
            raise ValueError(f"Invalid transition in {context}")
        if len(matches) > 1:
            names = ", ".join(definition.name for definition in matches)
            raise ValueError(f"Ambiguous transition in {context}: {names}")
        return matches[0].invoke(self, state, action)


def generate_state_machine_diagram(
    state_machine_class: Type[BaseStateMachine], filename: str = "state_machine_diagram"
) -> None:
    """Render a diagram; requires the diagrams extra and Graphviz's dot executable."""
    from .diagrams import generate_state_machine_diagram as generate

    generate(state_machine_class, filename)
