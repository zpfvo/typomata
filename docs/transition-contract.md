# Transition contract

This document defines the target contract for the next Typomata release. Implementation is in progress; the current limitations at the end describe where the existing code differs. Use this contract to guide implementation and regression tests.

## States and state ownership

States are instances of `BaseState` subclasses. Actions are instances of `BaseAction` subclasses. Both may carry application data. The base classes themselves are valid annotations for handlers intentionally accepting every state or action.

The caller owns the current state:

```python
state = machine.run(state, action)
```

The machine does not store or advance a current state automatically. Returning the same state instance is allowed. Immutable dataclasses are recommended, but immutability, payload validation, and side-effect control remain application responsibilities. For example, a refill amount being an `int` does not ensure that it is positive.

## Transition methods

A transition is a synchronous instance method marked with `@transition`. It has exactly three required parameters: the instance receiver, a state, and an action. Parameters may be positional-only or positional-or-keyword. Their roles are determined by position; their names need not be `self`, `state`, and `action`.

```python
from typomata import BaseAction, BaseState, BaseStateMachine, transition


class Idle(BaseState):
    pass


class Running(BaseState):
    pass


class Start(BaseAction):
    pass


class Machine(BaseStateMachine):
    @transition
    def start(self, state: Idle, action: Start) -> Running:
        return Running()


machine = Machine()
result = machine.start(Idle(), Start())
```

State, action, and return annotations are required. The receiver needs no annotation. Direct calls preserve the method's parameter names and kinds, including keyword calls when the original signature permits them. `run()` supplies the state and action positionally.

Defaults, additional parameters, keyword-only parameters, `*args`, and `**kwargs` are outside this contract. Put dependencies on the machine instance and event data on actions. Static methods, class methods, coroutine functions, and generator functions are rejected during machine definition. Composing other decorators with `@transition` is outside the supported contract for this release.

## Supported annotations

| Form | Meaning |
| --- | --- |
| State class | That class and its subclasses are valid source or result types |
| Action class | That class and its subclasses are valid action types |
| `Union[A, B]` or `A \| B` | Either member is accepted; both spellings behave identically |
| `Annotated[T, ...]` | Uses `T` for validation and retains metadata for introspection |
| Alias assigned to a supported form | Has the same meaning as the aliased annotation |
| Resolvable string or postponed annotation | Has the same meaning as the resolved annotation |

Every source/destination union member must be a state class, and every action union member must be an action class. Normalization handles unions and `Annotated` recursively. Duplicate class members are treated as one accepted type.

`Any`, `None`/`Optional`, `Literal`, type variables, `Self`, `NewType`, protocols, parameterized generic classes, and Python 3.12 `type` statement aliases are outside this release's annotation subset. Unsupported forms fail during machine definition; they are never silently omitted from dispatch.

Annotations resolve using the defining module's globals and the defining machine's class namespace. Referenced names must already be available when the machine class is created. Function-local names must be supplied as actual class objects, rather than unresolved strings. Names imported only under `TYPE_CHECKING` are not available at runtime. The library does not search caller stack frames for missing names.

String metadata on the outer return annotation describes the whole transition. String metadata on a return union member describes that destination. Multiple strings retain their order and are displayed on separate lines; a destination label includes applicable outer and member strings. Non-string metadata is retained for introspection but is not rendered. Source/action metadata does not affect dispatch or diagram labels.

Metadata is descriptive. It never executes as a guard or changes which handler is selected.

## Dispatch and ambiguity

`run(state, action)` matches source and action types using `isinstance`. A transition matches when at least one source member accepts the state and at least one action member accepts the action. Several matching union members in one method still count as one matching transition.

- No matching transition: raise a no-match error.
- Exactly one matching transition: invoke it and validate its result.
- More than one matching transition: raise an ambiguity error before invoking any handler.

Method names and declaration order have no effect on dispatch. There is no implicit priority or preference for the most specific annotation. A broad handler and a narrow handler that both accept an input are ambiguous.

Registration rejects two different methods declaring the same exact source/action class pair, including duplicates exposed by expanding unions. Overlaps caused by subclass relationships are checked at dispatch time, including multiple inheritance. This keeps behavior defined even when a new state or action subclass is created after the machine.

Unions on both input parameters accept their Cartesian product. Return unions describe possible outcomes without correlating each outcome to a specific input. Split handlers when different input combinations have different contracts.

## Invocation and errors

Both direct and dispatched calls validate the input types and the returned state against the method's own declaration. An undeclared result is rejected immediately, even when it is another `BaseState` subclass. Result validation does not undo work or side effects already performed by the method.

A direct call explicitly selects a method and does not perform global dispatch or ambiguity resolution. Ordinary Python argument binding still applies.

| Failure | Exception contract |
| --- | --- |
| Invalid signature, unsupported annotation, unresolved reference, or duplicate registration | `TypeError`, with machine/method context |
| No matching transition or ambiguous dispatch | `ValueError`, with input types and relevant candidates |
| Direct call with invalid state/action types | `ValueError`, with expected and actual types |
| Handler returns an undeclared result type | `ValueError`, identifying the originating handler and expected/actual types |
| Invalid call arity or keyword | Normal Python `TypeError` |
| Exception raised by the handler body | Propagates unchanged |

Dedicated library exception subclasses may refine these categories while preserving their base exception types. Every decorated method is either registered or rejected with an actionable error.

## Inheritance

Machine subclasses inherit transitions according to Python's method resolution order. For a given attribute name, the first definition in the MRO determines whether that name contributes a transition.

- A decorated override replaces the inherited transition under that name.
- An undecorated override removes that name from automatic dispatch.
- Inherited transitions under different names remain candidates and follow the same duplicate/ambiguity rules as locally declared transitions.
- A decorated override may call `super()`. The parent wrapper validates its own declaration; the override validates its final result against the override's declaration.

Each machine class owns its dispatch registry. Introspection returns immutable descriptions or independent snapshots; modifying an introspection result cannot alter dispatch. Validation of an explicitly called parent method does not depend on that method being present in the child's dispatch registry.

Declarations are resolved once in their defining class's namespace, including decorated methods on mixins. A subclass does not reinterpret inherited annotations using its own aliases. Aliases of an inherited decorated method reuse its declaration and count as one transition. Combining unrelated bases that independently registered the same decorated callable is rejected: use separate decorated methods so each parent call has an unambiguous declaration.

`transition_map()` returns a new list of dictionaries, including independent `annotations` and `destination_metadata` dictionaries. Types, callables, and arbitrary annotation metadata retain their identities; these objects are not deep-copied. Dispatch and validation use frozen normalized definitions, so changing the returned registry containers or the original annotation dictionary does not redefine a transition. Diagrams also read these frozen definitions.

## Static typing

The decorator preserves each supported method's callable signature and return annotation. The installed package supplies its typing information to consumers.

For the example above, a type checker should infer `Running` for `machine.start(Idle(), Start())` and reject `machine.start(Running(), Start())`. Runtime validation additionally protects calls from untyped code.

The decorator preserves the whole parameter list, including names and positional-only restrictions. Static call checking follows the method's annotations; state/action base-class requirements and the supported signature shape are validated when the machine class is created.

`run(state: BaseState, action: BaseAction) -> BaseState` has a deliberately broad static signature. Type checkers do not infer valid state/action pairs or specific return types from the runtime registry. An invalid pair of otherwise valid state and action instances may pass static checking and fail during dispatch.

Callers should annotate variables that hold multiple state types accordingly and narrow results before accessing state-specific data. Payload invariants, graph reachability, and completeness are not static guarantees of this API. Precise overloads or generated stubs for `run()` are possible future features.

## Diagrams

Diagrams show declared possible transitions between state categories. They do not prove reachability, exhaustiveness, or input/output correlations within a union. Return metadata supplies descriptive labels, not executable conditions.

Distinct state classes must remain distinct diagram nodes even when they share a name. Visualization reads the same normalized declarations used for validation and introspection.

## Current implementation limitations

The following remain implementation work, rather than guarantees of the current release:

- Diagram nodes use class names as identities and can merge distinct states.

Implementation commits should add behavioral and consumer-typing checks for each guarantee and remove the corresponding limitation here once it is resolved.
