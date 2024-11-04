# Typomata

Typomata is a Python state machine library that leverages type hints to define state transitions. It allows you to create state machines by defining states and actions as classes and transitions as methods with type-annotated parameters and return types.

## Features

- Define states and actions as classes.
- Use type hints to define transitions.
- Automatically collects transitions based on type annotations.
- Generate state machine diagrams using Graphviz.

## Installation

```bash
pip install typomata
```

## Requirements
Python 3.7 or higher.

## Usage
### Defining States and Actions
```python
from dataclasses import dataclass
from typomata import BaseState, BaseAction

@dataclass(frozen=True)
class StateA(BaseState):
    data: int

@dataclass(frozen=True)
class StateB(BaseState):
    data: str

@dataclass(frozen=True)
class IncrementAction(BaseAction):
    pass

@dataclass(frozen=True)
class ToUpperAction(BaseAction):
    pass

@dataclass(frozen=True)
class ResetAction(BaseAction):
    pass
```

### Creating the State Machine
```python
from typomata import StateMachineBase, transition
from typing import Union

class MyStateMachine(StateMachineBase):
    @transition
    def increment_or_reset(self, state: StateA, action: Union[IncrementAction, ResetAction]) -> StateA:
        if isinstance(action, IncrementAction):
            return StateA(state.data + 1)
        elif isinstance(action, ResetAction):
            return StateA(0)

    @transition
    def to_upper(self, state: Union[StateA, StateB], action: ToUpperAction) -> StateB:
        if isinstance(state, StateA):
            return StateB('A' * state.data)
        elif isinstance(state, StateB):
            return StateB(state.data.upper())

    @transition
    def reset_from_b(self, state: StateB, action: ResetAction) -> StateA:
        return StateA(0)
```

### Running the State Machine
```python
state_machine = MyStateMachine()
state = StateA(1)
actions = [IncrementAction(), ToUpperAction(), ToUpperAction(), ResetAction()]
for action in actions:
    state = state_machine.run(state, action)
    print(state)
```

### Generating the State Machine Diagram
```python
from typomata import generate_state_machine_diagram

generate_state_machine_diagram(MyStateMachine)
```
This will create a `state_machine_diagram.gv.pdf` file illustrating your state machine.

## Example
See the examples directory for a complete example.

## License
This project is licensed under the MIT License - see the LICENSE file for details.

## Contributing
Contributions are welcome! Please open an issue or submit a pull request.
