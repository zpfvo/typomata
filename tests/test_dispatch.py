import unittest
from typing import Annotated
from unittest.mock import patch

from typomata import (
    BaseAction,
    BaseState,
    BaseStateMachine,
    generate_state_machine_diagram,
    transition,
)


class Idle(BaseState):
    pass


class Ready(BaseState):
    pass


class Start(BaseAction):
    pass


class Reset(BaseAction):
    pass


class TestDispatch(unittest.TestCase):
    def test_duplicate_pairs_are_rejected(self):
        with self.assertRaisesRegex(TypeError, "Duplicate.*Idle.*Start.*first.*second"):
            class Duplicate(BaseStateMachine):
                @transition
                def first(self, state: Idle, action: Start) -> Ready:
                    return Ready()

                @transition
                def second(self, state: Idle, action: Start) -> Idle:
                    return state

    def test_duplicates_exposed_by_unions_are_rejected(self):
        with self.assertRaisesRegex(TypeError, "Duplicate.*Idle.*Start.*first.*second"):
            class Duplicate(BaseStateMachine):
                @transition
                def first(self, state: Idle | Ready, action: Start | Reset) -> Ready:
                    return Ready()

                @transition
                def second(self, state: Idle, action: Start) -> Idle:
                    return state

    def test_overlapping_handlers_are_ambiguous_regardless_of_names(self):
        for broad_name, narrow_name in (("a_broad", "z_narrow"), ("z_broad", "a_narrow")):
            with self.subTest(broad_name=broad_name):
                calls = []

                @transition
                def broad(self, state: BaseState, action: BaseAction) -> Idle:
                    calls.append("broad")
                    return Idle()

                @transition
                def narrow(self, state: Idle, action: Start) -> Ready:
                    calls.append("narrow")
                    return Ready()

                machine = type("Overlap", (BaseStateMachine,), {
                    broad_name: broad, narrow_name: narrow,
                })()
                with self.assertRaisesRegex(ValueError, "Ambiguous.*Overlap.*Idle.*Start") as error:
                    machine.run(Idle(), Start())
                self.assertIn(broad_name, str(error.exception))
                self.assertIn(narrow_name, str(error.exception))
                self.assertEqual(calls, [])
                self.assertIsInstance(getattr(machine, narrow_name)(Idle(), Start()), Ready)
                self.assertEqual(calls, ["narrow"])

    def test_action_subclasses_can_cause_ambiguity(self):
        class Machine(BaseStateMachine):
            @transition
            def broad(self, state: Idle, action: BaseAction) -> Idle:
                return state

            @transition
            def narrow(self, state: Idle, action: Start) -> Ready:
                return Ready()

        with self.assertRaisesRegex(ValueError, "Ambiguous"):
            Machine().run(Idle(), Start())
        self.assertIsInstance(Machine().run(Idle(), Reset()), Idle)

    def test_later_multiple_inheritance_can_cause_ambiguity(self):
        class Machine(BaseStateMachine):
            @transition
            def left(self, state: Idle, action: Start) -> Idle:
                return state

            @transition
            def right(self, state: Ready, action: Reset) -> Ready:
                return state

        class BothStates(Idle, Ready):
            pass

        class BothActions(Start, Reset):
            pass

        with self.assertRaisesRegex(ValueError, "Ambiguous.*BothStates.*BothActions"):
            Machine().run(BothStates(), BothActions())

    def test_overlapping_members_of_one_union_invoke_once(self):
        calls = []

        class Machine(BaseStateMachine):
            @transition
            def go(self, state: BaseState | Idle, action: BaseAction | Start) -> BaseState:
                calls.append(state)
                return state

        state = Idle()
        self.assertIs(Machine().run(state, Start()), state)
        self.assertEqual(calls, [state])

    def test_no_match_error_identifies_machine_and_input_types(self):
        with self.assertRaisesRegex(ValueError, "BaseStateMachine.*Idle.*Start"):
            BaseStateMachine().run(Idle(), Start())


class TestInheritance(unittest.TestCase):
    def test_decorated_override_can_delegate_to_super(self):
        calls = []

        class Parent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                calls.append("parent")
                return Ready()

        class Child(Parent):
            @transition
            def go(self, current: Idle, event: Start) -> Ready:
                calls.append("child")
                return super().go(state=current, action=event)

        child = Child()
        self.assertIsInstance(child.run(Idle(), Start()), Ready)
        self.assertEqual(calls, ["child", "parent"])
        self.assertEqual(len(child.transition_map()), 1)
        self.assertIsInstance(Parent.go(child, Idle(), Start()), Ready)
        self.assertIsInstance(Parent().run(Idle(), Start()), Ready)

    def test_parent_and_override_each_validate_their_own_result(self):
        class Parent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Idle()

        class Child(Parent):
            @transition
            def go(self, state: Idle, action: Start) -> Idle:
                return super().go(state, action)

        with self.assertRaisesRegex(ValueError, "Invalid result.*Parent.go.*Ready"):
            Child().run(Idle(), Start())

        class ValidParent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        class InvalidChild(ValidParent):
            @transition
            def go(self, state: Idle, action: Start) -> Idle:
                return super().go(state, action)

        with self.assertRaisesRegex(ValueError, "Invalid result.*InvalidChild.go.*Idle"):
            InvalidChild().run(Idle(), Start())

    def test_parent_validates_its_own_inputs_during_delegation(self):
        class Parent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        class Child(Parent):
            @transition
            def go(self, state: BaseState, action: BaseAction) -> Ready:
                return super().go(state, action)

        with self.assertRaisesRegex(ValueError, "Invalid state.*Idle"):
            Child().run(Ready(), Start())
        with self.assertRaisesRegex(ValueError, "Invalid action.*Start"):
            Child().run(Idle(), Reset())

    def test_undecorated_override_removes_dispatch_but_allows_super(self):
        class Parent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        class Child(Parent):
            def go(self, state, action):
                return super().go(state, action)

        child = Child()
        self.assertEqual(child.transition_map(), [])
        with self.assertRaises(ValueError):
            child.run(Idle(), Start())
        self.assertIsInstance(child.go(Idle(), Start()), Ready)
        self.assertIsInstance(Parent().run(Idle(), Start()), Ready)

    def test_mro_selects_one_definition_for_a_shared_name(self):
        class Left(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Idle:
                return state

        class Right(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        class Child(Left, Right):
            pass

        self.assertIsInstance(Child().run(Idle(), Start()), Idle)
        self.assertIsInstance(Right.go(Child(), Idle(), Start()), Ready)

    def test_inherited_different_names_still_detect_duplicates(self):
        class Left(BaseStateMachine):
            @transition
            def left(self, state: Idle, action: Start) -> Idle:
                return state

        class Right(BaseStateMachine):
            @transition
            def right(self, state: Idle, action: Start) -> Ready:
                return Ready()

        with self.assertRaisesRegex(TypeError, "Child.*left.*right"):
            class Child(Left, Right):
                pass
        self.assertIsInstance(Left().run(Idle(), Start()), Idle)
        self.assertIsInstance(Right().run(Idle(), Start()), Ready)

    def test_inherited_overlaps_detect_ambiguity(self):
        class Parent(BaseStateMachine):
            @transition
            def broad(self, state: BaseState, action: Start) -> BaseState:
                return state

        class Child(Parent):
            @transition
            def narrow(self, state: Idle, action: Start) -> Ready:
                return Ready()

        with self.assertRaisesRegex(ValueError, "Ambiguous.*broad.*narrow"):
            Child().run(Idle(), Start())
        self.assertIsInstance(Parent().run(Idle(), Start()), Idle)

    def test_diamond_inheritance_registers_common_method_once(self):
        class Parent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        class Left(Parent):
            pass

        class Right(Parent):
            pass

        class Child(Left, Right):
            pass

        self.assertEqual(len(Child().transition_map()), 1)
        self.assertIsInstance(Child().run(Idle(), Start()), Ready)

    def test_undecorated_mixin_override_follows_mro(self):
        class Parent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        class Mixin:
            def go(self, state, action):
                return super().go(state, action)

        class Child(Mixin, Parent):
            pass

        child = Child()
        self.assertEqual(child.transition_map(), [])
        self.assertIsInstance(child.go(Idle(), Start()), Ready)
        with self.assertRaises(ValueError):
            child.run(Idle(), Start())

    def test_decorated_mixin_can_be_called_through_super(self):
        class Mixin:
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        class Machine(Mixin, BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return super().go(state, action)

        self.assertIsInstance(Machine().run(Idle(), Start()), Ready)


class TestRegistry(unittest.TestCase):
    def test_snapshot_mutation_cannot_change_dispatch_or_diagrams(self):
        class Machine(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Annotated[Ready, "ready"]:
                return Ready()

        class Child(Machine):
            pass

        machine = Machine()
        snapshot = machine.transition_map()
        snapshot[0]["sources"] = (Ready,)
        snapshot[0]["actions"] = (Reset,)
        snapshot[0]["destinations"] = (Idle,)
        snapshot[0]["func"] = lambda *args: None
        snapshot[0]["annotations"]["state"] = Ready
        snapshot[0]["destination_metadata"][Ready] = ("changed",)
        snapshot.clear()

        for instance in (machine, Machine(), Child()):
            with self.subTest(machine=type(instance).__name__):
                self.assertIsInstance(instance.run(Idle(), Start()), Ready)
                self.assertIsInstance(instance.go(Idle(), Start()), Ready)
                with self.assertRaises(ValueError):
                    instance.run(Ready(), Reset())
                self.assertEqual(instance.transition_map()[0]["annotations"]["state"], Idle)

        captured = []
        with patch("graphviz.Digraph.render",
                   lambda graph, *args, **kwargs: captured.append(graph.source)):
            generate_state_machine_diagram(Machine)
        self.assertIn("ready", captured[0])
        self.assertNotIn("changed", captured[0])

    def test_later_annotation_changes_do_not_redefine_inherited_handlers(self):
        class Parent(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

        Parent.go.__wrapped__.__annotations__["state"] = Ready

        class Child(Parent):
            pass

        self.assertIsInstance(Parent().run(Idle(), Start()), Ready)
        self.assertIsInstance(Child().run(Idle(), Start()), Ready)

    def test_decorated_method_alias_counts_once(self):
        class Machine(BaseStateMachine):
            @transition
            def go(self, state: Idle, action: Start) -> Ready:
                return Ready()

            alias = go

        machine = Machine()
        self.assertEqual(len(machine.transition_map()), 1)
        self.assertIsInstance(machine.run(Idle(), Start()), Ready)
        self.assertIsInstance(machine.alias(Idle(), Start()), Ready)

    def test_inherited_alias_keeps_the_original_annotation_scope(self):
        class Parent(BaseStateMachine):
            State = Idle

            @transition
            def go(self, state: "State", action: Start) -> Ready:
                return Ready()

        class Child(Parent):
            State = Ready
            alias = Parent.go

        child = Child()
        self.assertEqual(len(child.transition_map()), 1)
        self.assertIsInstance(child.alias(Idle(), Start()), Ready)
        self.assertIsInstance(child.run(Idle(), Start()), Ready)

    def test_unrelated_classes_can_resolve_their_own_shared_method(self):
        @transition
        def go(self, state: "State", action: Start) -> BaseState:
            return state

        first = type("First", (BaseStateMachine,), {"State": Idle, "go": go})()
        second = type("Second", (BaseStateMachine,), {"State": Ready, "go": go})()
        for machine, state in ((first, Idle()), (second, Ready())):
            self.assertIs(machine.run(state, Start()), state)
            self.assertIs(machine.go(state, Start()), state)

        with self.assertRaisesRegex(TypeError, "Combined.*shared") as error:
            type("Combined", (type(first), type(second)), {})
        self.assertIn("First.go", str(error.exception))
        self.assertIn("Second.go", str(error.exception))

    def test_alias_of_unregistered_mixin_uses_mixin_scope(self):
        class Mixin:
            State = Idle

            @transition
            def go(self, state: "State", action: Start) -> Ready:
                return Ready()

        class Machine(Mixin, BaseStateMachine):
            State = Ready
            alias = Mixin.go

        machine = Machine()
        self.assertEqual(len(machine.transition_map()), 1)
        self.assertIsInstance(machine.go(Idle(), Start()), Ready)
        self.assertIsInstance(machine.alias(Idle(), Start()), Ready)
        self.assertIsInstance(machine.run(Idle(), Start()), Ready)
