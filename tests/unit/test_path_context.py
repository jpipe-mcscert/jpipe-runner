import sys
import unittest

from jpipe_runner.utils.syspath import path_context


class TestPathContext(unittest.TestCase):
    def setUp(self):
        self.original_sys_path = sys.path.copy()

    def tearDown(self):
        sys.path[:] = self.original_sys_path

    def test_path_context_adds_paths_and_restores(self):
        """
        Verify that `path_context` correctly adds a given path to `sys.path`
        for the duration of the context block and completely restores the
        original `sys.path` when exiting the context.
        """
        test_path = "/dummy/test_path_1"
        self.assertNotIn(test_path, sys.path)

        with path_context([test_path]):
            self.assertIn(test_path, sys.path)
            self.assertEqual(sys.path[0], test_path)

        self.assertNotIn(test_path, sys.path)
        self.assertEqual(sys.path, self.original_sys_path)

    def test_path_context_handles_exceptions(self):
        """
        Ensure that `sys.path` is properly restored to its original state
        even if an exception is raised inside the `path_context` block.
        """
        test_path = "/dummy/test_path_ex"

        with self.assertRaises(ValueError):
            with path_context([test_path]):
                self.assertIn(test_path, sys.path)
                raise ValueError("Test error")

        self.assertNotIn(test_path, sys.path)
        self.assertEqual(sys.path, self.original_sys_path)

    def test_path_context_prevents_duplicate_paths(self):
        """
        Verify that if a path is already present in `sys.path`, the
        `path_context` does not add it again,
        and safely restores the normal state afterwards.
        """
        test_path = "/dummy/test_path_dup"

        sys.path.append(test_path)

        initial_count = sys.path.count(test_path)
        expected_sys_path_during = sys.path.copy()

        with path_context([test_path]):
            self.assertEqual(sys.path.count(test_path), initial_count)
            self.assertEqual(sys.path, expected_sys_path_during)

        self.assertEqual(sys.path, expected_sys_path_during)

    def test_path_context_adds_multiple_paths_in_order(self):
        """
        Verify that when multiple paths are provided, they are prepended
        to `sys.path` in the exact order they were given.
        """
        paths_to_add = ["/dummy/path_a", "/dummy/path_b", "/dummy/path_c"]
        for p in paths_to_add:
            self.assertNotIn(p, sys.path)

        with path_context(paths_to_add):
            self.assertEqual(sys.path[: len(paths_to_add)], paths_to_add)

        for p in paths_to_add:
            self.assertNotIn(p, sys.path)
        self.assertEqual(sys.path, self.original_sys_path)

    def test_path_context_with_internal_duplicates(self):
        """
        Verify that if the provided list of paths contains duplicates,
        the path is only added once to `sys.path`.
        """
        paths_to_add = ["/dummy/path_dup", "/dummy/path_other", "/dummy/path_dup"]

        for p in set(paths_to_add):
            self.assertNotIn(p, sys.path)

        with path_context(paths_to_add):
            expected_added = ["/dummy/path_dup", "/dummy/path_other"]
            self.assertEqual(sys.path[: len(expected_added)], expected_added)
            self.assertEqual(sys.path.count("/dummy/path_dup"), 1)

        for p in set(paths_to_add):
            self.assertNotIn(p, sys.path)
        self.assertEqual(sys.path, self.original_sys_path)
