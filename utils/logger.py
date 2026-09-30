import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path


def configure(root: Path):
    folder = root / "logs"
    folder.mkdir(parents=True, exist_ok=True)
    logger = logging.getLogger("search_console")
    logger.setLevel(logging.INFO)
    for old in logger.handlers[:]:
        old.close()
        logger.removeHandler(old)
    for filename, level in (("app.log", logging.INFO), ("error.log", logging.ERROR)):
        handler = RotatingFileHandler(folder / filename, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
        handler.setLevel(level)
        handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        logger.addHandler(handler)
    return logger
