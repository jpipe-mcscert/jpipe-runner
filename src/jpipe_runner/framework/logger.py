import logging
import sys

# ANSI escape codes
RESET = "\033[0m"
RED = "\033[91m"
YELLOW = "\033[93m"


# Colored Formatter
class ColoredFormatter(logging.Formatter):
    def format(self, record):
        level = record.levelno
        if level >= logging.ERROR:
            color = RED
        elif level >= logging.WARNING:
            color = YELLOW
        else:
            color = RESET

        # Apply color only to the message part
        record.msg = f"{color}{record.msg}{RESET}"
        return super().format(record)


# Custom handler to collect logs
class InMemoryLogHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.logs = []

    def emit(self, record):
        self.logs.append(record)

    def has_errors(self):
        # Check if any log record is WARNING or higher
        return any(record.levelno >= logging.WARNING for record in self.logs)

    @property
    def formatted_logs(self):
        return [self.format(record) for record in self.logs]

    def dump_to_stderr(self):
        for log_entry in self.formatted_logs:
            print(log_entry, file=sys.stderr)


# Set up in-memory handler
log_buffer = InMemoryLogHandler()
log_buffer.setLevel(logging.WARNING)
formatter = ColoredFormatter(
    "%(levelname)s - %(funcName)s():%(lineno)s - %(asctime)5s - %(message)s"
)
log_buffer.setFormatter(formatter)

# Global logger config
GLOBAL_LOGGER = logging.getLogger(__name__)
GLOBAL_LOGGER.setLevel(logging.WARNING)
GLOBAL_LOGGER.addHandler(log_buffer)
# Avoid duplicate logs on root
GLOBAL_LOGGER.propagate = False
