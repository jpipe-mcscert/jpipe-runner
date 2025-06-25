import logging

# Configure the GLOBAL_LOGGER
logging.basicConfig(
    level=logging.WARNING,
    format='%(levelname)s - %(funcName)s():%(lineno)s - %(asctime)5s - %(message)s',
)
GLOBAL_LOGGER = logging.getLogger(__name__)
