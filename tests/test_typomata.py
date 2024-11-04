import unittest
from dataclasses import dataclass
from typing import Union

from typomata import BaseAction, BaseState, BaseStateMachine, transition


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
    ) -> StateA:
        if isinstance(action, IncrementAction):
            return StateA(state.data + 1)
        elif isinstance(action, ResetAction):
            return StateA(0)
        else:
            raise ValueError(f"Invalid action {action} for state {state}")

    @transition
    def to_upper(self, state: Union[StateA, StateB], action: ToUpperAction) -> StateB:
        if isinstance(state, StateA):
            return StateB("A" * state.data)
        elif isinstance(state, StateB):
            return StateB(state.data.upper())
        else:
            raise ValueError(f"Invalid state {state} for action {action}")

    @transition
    def reset_from_b(self, state: StateB, action: ResetAction) -> StateA:
        return StateA(0)


class TestTypomata(unittest.TestCase):
    def test_state_machine(self):
        state_machine = MyStateMachine()
        state = StateA(1)
        state = state_machine.run(state, IncrementAction())
        self.assertEqual(state, StateA(2))
        state = state_machine.run(state, ToUpperAction())
        self.assertEqual(state, StateB("AA"))
        state = state_machine.run(state, ResetAction())
        self.assertEqual(state, StateA(0))

    def test_invalid_transition(self):
        state_machine = MyStateMachine()
        state = StateA(1)
        with self.assertRaises(ValueError):
            state_machine.run(state, ToUpperAction())  # Valid
            state_machine.run(state, ResetAction())  # Valid
            state_machine.run(state, ToUpperAction())  # Invalid after reset


if __name__ == "__main__":
    unittest.main()
