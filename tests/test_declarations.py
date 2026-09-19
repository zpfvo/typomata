import sys
import unittest
from typing import (
    Annotated,
    Any,
    Generic,
    Literal,
    NewType,
    Optional,
    Protocol,
    TypeVar,
    Union,
)
from unittest.mock import patch

from typing_extensions import Self

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


class StateProtocol(Protocol):
    pass


Payload = TypeVar("Payload")


class GenericState(BaseState, Generic[Payload]):
    pass


def make_machine(method):
    return type("ExampleMachine", (BaseStateMachine,), {"go": transition(method)})


class TestDeclarations(unittest.TestCase):
    def test_parameter_roles_and_keyword_binding(self):
        def go(machine, current: Idle, event: Start) -> Ready:
            return Ready()

        machine = make_machine(go)()
        self.assertIsInstance(machine.go(current=Idle(), event=Start()), Ready)
        self.assertIsInstance(machine.run(Idle(), Start()), Ready)
        with self.assertRaises(TypeError):
            machine.go(Idle(), current=Idle(), event=Start())
        with self.assertRaises(TypeError):
            machine.go(Idle())
        with self.assertRaises(TypeError):
            machine.go(state=Idle(), action=Start())

    def test_positional_only_parameters(self):
        def go(machine, current: Idle, event: Start, /) -> Ready:
            return Ready()

        machine = make_machine(go)()
        self.assertIsInstance(machine.go(Idle(), Start()), Ready)
        self.assertIsInstance(machine.run(Idle(), Start()), Ready)
        with self.assertRaises(TypeError):
            machine.go(current=Idle(), event=Start())

    def test_invalid_signatures_fail_during_class_creation(self):
        signatures = [
            "self, state: Idle",
            "self, state: Idle, action: Start, extra: int",
            "self, state: Idle, action: Start = Start()",
            "self, *, state: Idle, action: Start",
            "self, state: Idle, action: Start, *args",
            "self, state: Idle, action: Start, **kwargs",
        ]
        for parameters in signatures:
            with self.subTest(parameters=parameters):
                namespace = dict(globals())
                exec(f"def go({parameters}) -> Ready: return Ready()", namespace)
                with self.assertRaisesRegex(TypeError, "ExampleMachine.go.*signature"):
                    make_machine(namespace["go"])

    def test_missing_annotations_fail_during_class_creation(self):
        for missing in ("state", "action", "return"):
            with self.subTest(missing=missing):
                def go(self, state: Idle, action: Start) -> Ready:
                    return Ready()

                go.__annotations__.pop(missing)
                with self.assertRaisesRegex(TypeError, f"ExampleMachine.go.*{missing}"):
                    make_machine(go)

    def test_invalid_annotation_forms_fail_early(self):
        unsupported = [
            Any, int, None, Optional[Idle], Literal[1], list[Idle],
            TypeVar("State", bound=BaseState), NewType("NewState", Idle),
            Self, StateProtocol, GenericState[int],
        ]
        for annotation in unsupported:
            for role in ("state", "action", "return"):
                with self.subTest(annotation=annotation, role=role):
                    def go(self, state: Idle, action: Start) -> Ready:
                        return Ready()

                    go.__annotations__[role] = annotation
                    with self.assertRaisesRegex(TypeError, f"ExampleMachine.go.*{role}"):
                        make_machine(go)

    def test_state_and_action_base_classes_are_not_interchangeable(self):
        for role, annotation in (("state", Start), ("action", Idle), ("return", Start)):
            with self.subTest(role=role):
                def go(self, state: Idle, action: Start) -> Ready:
                    return Ready()

                go.__annotations__[role] = annotation
                with self.assertRaisesRegex(TypeError, f"ExampleMachine.go.*{role}"):
                    make_machine(go)

    def test_async_and_generator_methods_fail_early(self):
        async def coroutine(self, state: Idle, action: Start) -> Ready:
            return Ready()

        def generator(self, state: Idle, action: Start) -> Ready:
            yield Ready()

        async def async_generator(self, state: Idle, action: Start) -> Ready:
            yield Ready()

        for method in (coroutine, generator, async_generator):
            with self.subTest(method=method.__name__):
                with self.assertRaisesRegex(TypeError, "ExampleMachine.go.*synchronous"):
                    make_machine(method)

    def test_descriptors_fail_early_in_both_decorator_orders(self):
        for descriptor in (staticmethod, classmethod, property):
            for transition_outermost in (True, False):
                with self.subTest(descriptor=descriptor, outermost=transition_outermost):
                    def go(self, state: Idle, action: Start) -> Ready:
                        return Ready()

                    decorated = (transition(descriptor(go)) if transition_outermost
                                 else descriptor(transition(go)))
                    with self.assertRaisesRegex(TypeError, "ExampleMachine.go.*instance method"):
                        type("ExampleMachine", (BaseStateMachine,), {"go": decorated})

    def test_postponed_module_annotations(self):
        namespace = dict(globals())
        exec(
            "from __future__ import annotations\n"
            "def go(self, state: Idle, action: Start) -> Ready: return Ready()",
            namespace,
        )
        self.assertIsInstance(make_machine(namespace["go"])().run(Idle(), Start()), Ready)

    @unittest.skipIf(sys.version_info < (3, 12), "type statement requires Python 3.12")
    def test_type_statement_alias_is_rejected(self):
        namespace = dict(globals())
        exec("type StateAlias = Idle", namespace)

        def go(self, state: Idle, action: Start) -> Ready:
            return Ready()

        go.__annotations__["state"] = namespace["StateAlias"]
        with self.assertRaisesRegex(TypeError, "ExampleMachine.go.*state"):
            make_machine(go)

    def test_class_namespace_annotations(self):
        class Machine(BaseStateMachine):
            class LocalState(BaseState):
                pass

            @transition
            def go(self, state: "LocalState", action: Start) -> "LocalState":
                return state

        state = Machine.LocalState()
        self.assertIs(Machine().run(state, Start()), state)

        class Child(Machine):
            LocalState = Ready

        self.assertIs(Child().run(state, Start()), state)

    def test_unresolved_annotation_has_context_and_cause(self):
        def go(self, state: "MissingState", action: Start) -> Ready:
            return Ready()

        with self.assertRaisesRegex(TypeError, "ExampleMachine.go.*MissingState") as error:
            make_machine(go)
        self.assertIsInstance(error.exception.__cause__, NameError)

    @unittest.skipIf(sys.version_info < (3, 14), "deferred annotations require Python 3.14")
    def test_deferred_annotation_failure_has_machine_context(self):
        namespace = dict(globals())
        with self.assertRaisesRegex(TypeError, "MissingMachine.go.*MissingState") as error:
            exec(
                "class MissingMachine(BaseStateMachine):\n"
                "    @transition\n"
                "    def go(self, state: MissingState, action: Start) -> Ready:\n"
                "        return Ready()\n",
                namespace,
            )
        self.assertIsInstance(error.exception.__cause__, NameError)

    def test_subclasses_and_base_annotations(self):
        def go(self, state: BaseState, action: BaseAction) -> BaseState:
            return state

        state = Idle()
        self.assertIs(make_machine(go)().run(state, Start()), state)

    def test_union_spellings_and_annotated_members(self):
        for union, actions in (
            (Union[Idle, Ready], Union[Start, Reset]),
            (Idle | Ready, Start | Reset),
            (Union[Annotated[Idle, "source"], Ready],
             Union[Annotated[Start, "event"], Reset]),
        ):
            with self.subTest(union=union):
                def go(self, state, action):
                    return state

                go.__annotations__ = {
                    "state": Annotated[union, "input"],
                    "action": Annotated[actions, "event"],
                    "return": Annotated[union, "result"],
                }
                machine = make_machine(go)()
                for state in (Idle(), Ready()):
                    for action in (Start(), Reset()):
                        self.assertIs(machine.run(state, action), state)
                entry = machine.transition_map()[0]
                self.assertEqual(entry["sources"], (Idle, Ready))
                self.assertEqual(entry["destinations"], (Idle, Ready))
                self.assertEqual(entry["metadata"], "result")
                with self.assertRaisesRegex(ValueError, "Invalid state.*Idle.*Ready"):
                    machine.go(Start(), Start())
                with self.assertRaisesRegex(ValueError, "Invalid action.*Start.*Reset"):
                    machine.go(Idle(), Idle())

    def test_diagram_preserves_and_escapes_return_metadata(self):
        marker = {"description": "retained"}

        def go(self, state: Idle, action: Start) -> Annotated[
            Union[Annotated[Idle, "stock < 1"], Annotated[Ready, "stock > 0"]],
            "paid & ready", marker,
        ]:
            return Ready()

        machine_type = make_machine(go)
        captured = []
        with patch("graphviz.Digraph.render",
                   lambda graph, *args, **kwargs: captured.append(graph.source)):
            generate_state_machine_diagram(machine_type)
        source = captured[0]
        self.assertIn("paid &amp; ready", source)
        self.assertIn("stock &lt; 1", source)
        self.assertIn("stock &gt; 0", source)
        self.assertNotIn("retained", source)
        idle_edge = next(line for line in source.splitlines() if "state_0 -> state_0" in line)
        ready_edge = next(line for line in source.splitlines() if "state_0 -> state_1" in line)
        self.assertNotIn("stock &gt; 0", idle_edge)
        self.assertNotIn("stock &lt; 1", ready_edge)
        self.assertEqual(machine_type().transition_map()[0]["annotations"]["return"],
                         go.__annotations__["return"])


class TestInvocation(unittest.TestCase):
    def test_result_subclasses_and_same_instance_are_allowed(self):
        class SpecializedReady(Ready):
            pass

        result = SpecializedReady()

        def go(self, state: Idle, action: Start) -> Ready:
            return result

        machine = make_machine(go)()
        for call in (machine.go, machine.run):
            self.assertIs(call(Idle(), Start()), result)

    def test_invalid_results_are_rejected_by_both_entry_points(self):
        for result in (123, None, Start(), Idle()):
            with self.subTest(result=result):
                def go(self, state: Idle, action: Start) -> Ready:
                    return result

                machine = make_machine(go)()
                for call in (machine.go, machine.run):
                    with self.subTest(call=call.__name__):
                        with self.assertRaisesRegex(ValueError, "result.*go.*Ready"):
                            call(Idle(), Start())

    def test_direct_input_validation_prevents_handler_execution(self):
        calls = []

        def go(self, state: Idle, action: Start) -> Ready:
            calls.append((state, action))
            return Ready()

        machine = make_machine(go)()
        for state, action in ((Ready(), Start()), (Idle(), Reset())):
            with self.subTest(state=state, action=action):
                with self.assertRaises(ValueError):
                    machine.go(state, action)
        self.assertEqual(calls, [])

    def test_handler_exceptions_propagate_unchanged(self):
        error = RuntimeError("application failure")

        def go(self, state: Idle, action: Start) -> Ready:
            raise error

        machine = make_machine(go)()
        for call in (machine.go, machine.run):
            with self.subTest(call=call.__name__):
                with self.assertRaises(RuntimeError) as raised:
                    call(Idle(), Start())
                self.assertIs(raised.exception, error)
