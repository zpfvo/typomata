import unittest
from unittest.mock import patch

from typomata import BaseAction, BaseState, BaseStateMachine, transition
from typomata import generate_state_machine_diagram


class Go(BaseAction):
    pass


class DiagramIdentityTests(unittest.TestCase):
    def test_same_named_classes_have_distinct_nodes_and_correct_edges(self):
        # Even module and qualified names can coincide for separate classes.
        def make_state():
            class Idle(BaseState):
                pass
            return Idle

        first, second = make_state(), make_state()
        self.assertEqual(first.__qualname__, second.__qualname__)
        self.assertEqual(first.__module__, second.__module__)

        class Machine(BaseStateMachine):
            @transition
            def forward(self, state: first, action: Go) -> second:
                return second()

            @transition
            def reverse(self, state: second, action: Go) -> first:
                return first()

        captured = []
        with patch('graphviz.Digraph.render',
                   lambda graph, *args, **kwargs: captured.append(graph.source)):
            generate_state_machine_diagram(Machine)
            generate_state_machine_diagram(Machine)

        source = captured[0]
        self.assertEqual(source, captured[1])
        self.assertEqual(source.count('label="Idle ('), 2)
        self.assertIn('state_0 [label="Idle (1)"', source)
        self.assertIn('state_1 [label="Idle (2)"', source)
        self.assertIn('state_0 -> state_1', source)
        self.assertIn('state_1 -> state_0', source)
        self.assertNotIn('state_0 -> state_0', source)

    def test_repeated_state_uses_one_node_and_keeps_simple_label(self):
        class Ready(BaseState):
            pass

        class Machine(BaseStateMachine):
            @transition
            def stay(self, state: Ready, action: Go) -> Ready:
                return state

        captured = []
        with patch('graphviz.Digraph.render',
                   lambda graph, *args, **kwargs: captured.append(graph.source)):
            generate_state_machine_diagram(Machine)
        self.assertEqual(captured[0].count('state_0 [label=Ready'), 1)
        self.assertIn('state_0 -> state_0', captured[0])
        self.assertNotIn('state_1', captured[0])
