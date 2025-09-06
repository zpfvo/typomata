from dataclasses import dataclass
from pprint import pprint
from typing_extensions import Union

from typomata import (
    BaseAction,
    BaseState,
    BaseStateMachine,
    generate_state_machine_diagram,
    transition,
)


# --- States ---
@dataclass(frozen=True)
class Idle(BaseState):
    coffee_stock: int


@dataclass(frozen=True)
class Brewing(BaseState):
    coffee_stock: int


@dataclass(frozen=True)
class OutOfCoffee(BaseState):
    pass


# --- Actions ---
@dataclass(frozen=True)
class InsertCoin(BaseAction):
    pass


@dataclass(frozen=True)
class BrewCoffee(BaseAction):
    pass


@dataclass(frozen=True)
class Refill(BaseAction):
    amount: int


# --- State Machine ---
class CoffeeMachine(BaseStateMachine):
    @transition
    def start_brewing(self, state: Idle, action: InsertCoin) -> Brewing:
        return Brewing(state.coffee_stock)

    @transition
    def finish_brewing(self, state: Brewing, action: BrewCoffee) -> Union[Idle, OutOfCoffee]:
        new_stock = state.coffee_stock - 1
        if new_stock > 0:
            return Idle(new_stock)
        else:
            return OutOfCoffee()

    @transition
    def refill_machine(self, state: Union[Idle, OutOfCoffee], action: Refill) -> Idle:
        if isinstance(state, OutOfCoffee):
            return Idle(action.amount)
        else:
            return Idle(state.coffee_stock + action.amount)


# --- Usage Example ---
def main():
    machine = CoffeeMachine()

    # Generate state machine diagram
    generate_state_machine_diagram(CoffeeMachine)

    # Print transition map
    pprint(machine.transition_map())

    # Explicit state change
    state = machine.start_brewing(Idle(1), InsertCoin())
    print(type(state)) # <class '__main__.Brewing'>

    # Runtime Exception if there is no transition
    try:
        state = machine.start_brewing(OutOfCoffee(), InsertCoin())
    except Exception as e:
        print(repr(e)) # ValueError("Invalid state OutOfCoffee for start_brewing, expected one of ['Idle']")

    # Pass any combination of State and Action to
    # machine.run  and it will find the correct transition by itself
    state = Idle(coffee_stock=2)
    actions = [
        InsertCoin(),
        BrewCoffee(),
        InsertCoin(),
        BrewCoffee(),
        Refill(amount=3),
        InsertCoin(),
        BrewCoffee(),
    ]

    for action in actions:
        new_state = machine.run(state, action)
        print(f"Action: {action}, Transitioned from {state} to {new_state}")
        state = new_state



if __name__ == "__main__":
    main()
