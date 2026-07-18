import logging
import unittest

from jpipe_runner.framework.logger import InMemoryLogHandler


class TestInMemoryLogHandler(unittest.TestCase):
    def _make_handler(self):
        handler = InMemoryLogHandler()
        handler.setLevel(logging.WARNING)
        handler.setFormatter(logging.Formatter("%(levelname)s - %(message)s"))
        return handler

    def _emit(self, handler, level, message):
        record = logging.LogRecord(
            name="test", level=level, pathname="", lineno=0, msg=message, args=(), exc_info=None
        )
        handler.emit(record)

    def test_has_errors_empty(self):
        handler = self._make_handler()
        self.assertFalse(handler.has_errors())

    def test_has_errors_with_error(self):
        handler = self._make_handler()
        self._emit(handler, logging.ERROR, "something went wrong")
        self.assertTrue(handler.has_errors())

    def test_has_errors_with_warning(self):
        handler = self._make_handler()
        self._emit(handler, logging.WARNING, "be careful")
        self.assertTrue(handler.has_errors())

    def test_has_errors_with_info_only(self):
        handler = self._make_handler()
        handler.setLevel(logging.DEBUG)
        self._emit(handler, logging.INFO, "all good")
        self.assertFalse(handler.has_errors())

    def test_formatted_logs_is_idempotent(self):
        # A mock formatter that mutates the record's message to test idempotency
        class MutatingFormatter(logging.Formatter):
            def format(self, record):
                record.msg = f"[{record.msg}]"
                return super().format(record)

        handler = self._make_handler()
        handler.setFormatter(MutatingFormatter("%(message)s"))
        handler.setLevel(logging.INFO)

        self._emit(handler, logging.INFO, "test")

        first_access = handler.formatted_logs
        second_access = handler.formatted_logs

        self.assertEqual(first_access, ["[test]"])
        self.assertEqual(second_access, ["[test]"])
