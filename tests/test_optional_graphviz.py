"""Verify the core import and execution path without the visualization dependency."""

import subprocess
import sys
import textwrap
import unittest
from unittest.mock import patch

from typomata import BaseStateMachine, generate_state_machine_diagram


class OptionalGraphvizTests(unittest.TestCase):
    def test_core_and_example_work_when_graphviz_is_unavailable(self):
        result = subprocess.run(
            [sys.executable, "-c", textwrap.dedent('''
                import importlib.abc
                import runpy
                import sys

                class BlockGraphviz(importlib.abc.MetaPathFinder):
                    def find_spec(self, fullname, path=None, target=None):
                        if fullname == "graphviz" or fullname.startswith("graphviz."):
                            raise ModuleNotFoundError("blocked for test", name=fullname)

                sys.meta_path.insert(0, BlockGraphviz())
                from typomata import BaseStateMachine, generate_state_machine_diagram
                assert "graphviz" not in sys.modules
                assert "typomata.diagrams" not in sys.modules
                runpy.run_path("examples/example_usage.py", run_name="__main__")
                assert "typomata.diagrams" not in sys.modules
                try:
                    generate_state_machine_diagram(BaseStateMachine)
                except ModuleNotFoundError as exc:
                    assert exc.name == "graphviz"
                    assert "typomata[diagrams]" in str(exc)
                    assert "dot" in str(exc)
                else:
                    raise AssertionError("missing Graphviz should report how to install it")
            ''')],
            capture_output=True, text=True, check=False,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("Transitioned from"), 7)

    def test_unrelated_import_errors_are_preserved(self):
        import builtins

        original_import = builtins.__import__
        failure = ModuleNotFoundError("broken Graphviz dependency", name="other_dependency")

        def import_with_failure(name, *args, **kwargs):
            if name == "graphviz":
                raise failure
            return original_import(name, *args, **kwargs)

        with patch("builtins.__import__", side_effect=import_with_failure):
            with self.assertRaises(ModuleNotFoundError) as caught:
                generate_state_machine_diagram(BaseStateMachine)
        self.assertIs(caught.exception, failure)
