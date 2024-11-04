from dataclasses import dataclass
from typing_extensions import Annotated, Union

from typomata import (
    BaseAction,
    BaseState,
    BaseStateMachine,
    generate_state_machine_diagram,
    transition,
)


# Define states
@dataclass(frozen=True)
class StateA(BaseState):
    data: int


@dataclass(frozen=True)
class StateB(BaseState):
    data: str


# Define actions
@dataclass(frozen=True)
class IncrementAction(BaseAction):
    pass


@dataclass(frozen=True)
class ToUpperAction(BaseAction):
    pass


@dataclass(frozen=True)
class ResetAction(BaseAction):
    pass


# Define the state machine
class MyStateMachine(BaseStateMachine):
    @transition
    def increment_or_reset(
        self, state: StateA, action: Union[IncrementAction, ResetAction]
    ) -> Annotated[StateA, "if data > 0"]:
        if isinstance(action, IncrementAction):
            return StateA(state.data + 1)
        elif isinstance(action, ResetAction):
            return StateA(0)
        else:
            raise ValueError(f"Invalid action {action} for state {state}")

    @transition
    def to_upper(
        self, state: Union[StateA, StateB], action: ToUpperAction
    ) -> Union[StateA, StateB]:
        if isinstance(state, StateA):
            return StateB("A" * state.data)
        elif isinstance(state, StateB):
            return StateB(state.data.upper())
        else:
            raise ValueError(f"Invalid state {state} for action {action}")

    @transition
    def reset_from_b(self, state: StateB, action: ResetAction) -> StateA:
        return StateA(0)


# Usage example
def main():
    state_machine = MyStateMachine()
    state = StateA(1)
    actions = [
        IncrementAction(),
        ToUpperAction(),
        ToUpperAction(),
        ResetAction(),
        IncrementAction(),
        ToUpperAction(),
        ToUpperAction(),
        ResetAction(),
    ]
    for action in actions:
        new_state = state_machine.run(state, action)
        print(f"Action: {action}, Transitioned from {state} to {new_state}")
        state = new_state

    # Generate the state machine diagram
    generate_state_machine_diagram(MyStateMachine)


if __name__ == "__main__":
    main()
