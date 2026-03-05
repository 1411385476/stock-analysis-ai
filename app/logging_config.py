import logging
import sys

from app.config import CONFIG


def setup_logging() -> None:
    logging.basicConfig(
        level=getattr(logging, CONFIG.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        stream=sys.stderr,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
