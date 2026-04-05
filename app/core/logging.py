import logging
import os
from logging.handlers import RotatingFileHandler

from app.core.settings import get_settings

settings = get_settings()


def setup_logging() -> None:
    log_dir = os.path.join(settings.STORAGE_PATH, "logs")
    os.makedirs(log_dir, exist_ok=True)

    log_file = os.path.join(log_dir, "app.log")

    handler = RotatingFileHandler(
        log_file,
        maxBytes=5_000_000,
        backupCount=3,
        encoding="utf-8"
    )

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
    )
    handler.setFormatter(formatter)

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)

    if not root_logger.handlers:
        root_logger.addHandler(handler)


logger = logging.getLogger("ai_platform")