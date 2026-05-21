import argparse
import unittest
from unittest.mock import MagicMock

from jpipe_runner.utils.append_else_default_action import AppendElseDefaultAction, _copy_items


class TestAppendElseDefaultAction(unittest.TestCase):
    """Test suite for AppendElseDefaultAction specific initializations and behavior."""

    def test_init_success(self):
        """Test that initialization succeeds with valid parameters."""
        action = AppendElseDefaultAction(
            option_strings=["--foo", "-f"], dest="foo", default=["a", "b"], help="test help"
        )
        self.assertEqual(action.option_strings, ["--foo", "-f"])
        self.assertEqual(action.dest, "foo")
        self.assertEqual(action.default, ["a", "b"])
        self.assertEqual(action.help, "test help")

    def test_init_raises_value_error_on_invalid_nargs(self):
        with self.assertRaisesRegex(
            ValueError, "nargs for append_else_default actions must be != 0"
        ):
            AppendElseDefaultAction(option_strings=["--foo"], dest="foo", nargs=0, default=["a"])

    def test_init_raises_value_error_if_const_without_optional_nargs(self):
        with self.assertRaisesRegex(ValueError, r"nargs must be '\?' to supply const"):
            AppendElseDefaultAction(
                option_strings=["--foo"], dest="foo", const="constant", nargs=1, default=["a"]
            )

    def test_init_raises_value_error_on_missing_default(self):
        with self.assertRaisesRegex(
            ValueError, "append_else_default action requires a default value"
        ):
            AppendElseDefaultAction(option_strings=["--foo"], dest="foo", default=None)

    def test_argparse_integration_uses_default(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--foo", action=AppendElseDefaultAction, default=["D"])

        args = parser.parse_args([])
        self.assertEqual(args.foo, ["D"])

    def test_argparse_integration_overrides_default(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--foo", action=AppendElseDefaultAction, default=["D"])

        args = parser.parse_args(["--foo", "A"])
        self.assertEqual(args.foo, ["A"])

    def test_argparse_integration_appends_multiple(self):
        parser = argparse.ArgumentParser()
        parser.add_argument("--foo", action=AppendElseDefaultAction, default=["D"])

        args = parser.parse_args(["--foo", "A", "--foo", "B"])
        self.assertEqual(args.foo, ["A", "B"])

    def test_argparse_integration_with_const(self):
        parser = argparse.ArgumentParser()
        parser.add_argument(
            "--foo", action=AppendElseDefaultAction, nargs="?", const="C", default=["D"]
        )

        args = parser.parse_args([])
        self.assertEqual(args.foo, ["D"])

        args = parser.parse_args(["--foo"])
        self.assertEqual(args.foo, ["C"])

        args = parser.parse_args(["--foo", "A"])
        self.assertEqual(args.foo, ["A"])

        args = parser.parse_args(["--foo", "--foo", "B"])
        self.assertEqual(args.foo, ["C", "B"])

    def test_direct_call_appends_values(self):
        """Direct test of the __call__ method"""
        default_list = ["D"]
        action = AppendElseDefaultAction(option_strings=["--foo"], dest="foo", default=default_list)
        namespace = argparse.Namespace(foo=default_list)
        mock_parser = MagicMock(spec=argparse.ArgumentParser)

        # Initial state uses default
        self.assertEqual(namespace.foo, ["D"])

        # Default list is replaced
        action(parser=mock_parser, namespace=namespace, values="A")
        self.assertEqual(namespace.foo, ["A"])

        # Extended without dropping
        action(parser=mock_parser, namespace=namespace, values="B")
        self.assertEqual(namespace.foo, ["A", "B"])

        self.assertEqual(default_list, ["D"], "Default list should not be mutated")


class TestCopyItems(unittest.TestCase):
    """Test suite for the internal _copy_items function."""

    def test_copy_items_none(self):
        self.assertEqual(_copy_items(None), [])

    def test_copy_items_list(self):
        """Test that a list is copied and not just referenced."""
        original = [1, 2, 3]
        copied = _copy_items(original)
        self.assertEqual(copied, original)
        self.assertIsNot(copied, original)

    def test_copy_items_set(self):
        """Test that a set is copied and not just referenced."""
        original = {1, 2, 3}
        copied = _copy_items(original)
        self.assertEqual(copied, original)
        self.assertIsNot(copied, original)
        self.assertIsInstance(copied, set)
