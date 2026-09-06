"""Static-only fixtures, checked by mypy rather than executed.

assert_type checks prevent a decorator from silently degrading to Any.
Expected errors use specific ignores; warn_unused_ignores makes a missing
diagnostic fail the check as well.
"""

from typing import Annotated, Protocol

from typing_extensions import assert_type

from typomata import BaseAction, BaseState, BaseStateMachine, transition


class Idle(BaseState):
    pass


class Ready(BaseState):
    pass


class Start(BaseAction):
    pass


class Choose(BaseAction):
    pass


class Finish(BaseAction):
    pass


class Machine(BaseStateMachine):
    @transition
    def start(self, state: Idle, action: Start) -> Annotated[Ready, "started"]:
        return Ready()

    @transition
    def choose(machine, current: Idle | Ready, event: Choose) -> Idle | Ready:
        return current

    @transition
    def finish(self, state: Ready, action: Finish, /) -> Idle:
        return Idle()


class Child(Machine):
    @transition
    def start(self, state: Idle, action: Start) -> Ready:
        return super().start(state=state, action=action)


class StartHandler(Protocol):
    def __call__(self, state: Idle, action: Start) -> Ready: ...


machine = Machine()

# Parameter names, method binding, and concrete return types are preserved.
assert_type(machine.start(Idle(), Start()), Ready)
assert_type(machine.start(state=Idle(), action=Start()), Ready)
assert_type(machine.start(Idle(), action=Start()), Ready)
assert_type(Machine.start(machine, state=Idle(), action=Start()), Ready)
assert_type(Machine.start(self=machine, state=Idle(), action=Start()), Ready)
assert_type(Child().start(state=Idle(), action=Start()), Ready)
handler: StartHandler = machine.start
assert_type(handler(state=Idle(), action=Start()), Ready)

# Alternate names, unions, and positional-only parameters retain their meaning.
assert_type(machine.choose(current=Idle(), event=Choose()), Idle | Ready)
assert_type(machine.choose(current=Ready(), event=Choose()), Idle | Ready)
assert_type(machine.finish(Ready(), Finish()), Idle)

# run() remains dynamically dispatched with a broad static result.
assert_type(machine.run(Idle(), Start()), BaseState)

# Invalid calls must continue to produce these specific diagnostics.
machine.start(state=Ready(), action=Start())  # type: ignore[arg-type]
machine.start(state=Idle(), action=Choose())  # type: ignore[arg-type]
machine.start(Ready(), Start())  # type: ignore[arg-type]
machine.start(Idle(), Choose())  # type: ignore[arg-type]
machine.start(Idle())  # type: ignore[call-arg]
machine.start(Idle(), Start(), None)  # type: ignore[call-arg]
machine.start(current=Idle(), action=Start())  # type: ignore[call-arg]
machine.finish(state=Ready(), action=Finish())  # type: ignore[call-arg]


@transition  # type: ignore[type-var]
def invalid_result(self: Machine, state: Idle, action: Start) -> int:
    return 1
