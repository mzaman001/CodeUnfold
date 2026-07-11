import importlib
import logging
import sys
from logging.handlers import RotatingFileHandler
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def test_setup_logging_uses_rotating_file_handler():
    """Regression test for B22/W23: a plain FileHandler has no size cap,
    so a popular long-running deployment could grow codeunfold.log
    without bound. Must be a RotatingFileHandler with a real cap."""
    import logger
    importlib.reload(logger)
    file_handlers = [h for h in logger.log.handlers if isinstance(h, RotatingFileHandler)]
    assert len(file_handlers) == 1
    handler = file_handlers[0]
    assert handler.maxBytes > 0
    assert handler.backupCount >= 1


def test_setup_logging_survives_filehandler_oserror(monkeypatch):
    """Regression test for the read-only-filesystem crash: setup_logging()
    used to construct its FileHandler completely unguarded, so any
    OSError (e.g. a read-only app directory on some container platforms)
    would crash the whole app at import time, before a single page
    loaded. Forces RotatingFileHandler construction to raise OSError
    (deterministic -- doesn't depend on actual filesystem permissions,
    which don't apply the same way when tests run as root) and confirms
    setup_logging() still returns a working logger via the console
    handler instead of propagating the exception.
    """
    import logger

    def _raise_oserror(*args, **kwargs):
        raise OSError("simulated read-only filesystem")

    monkeypatch.setattr(logger, "RotatingFileHandler", _raise_oserror)
    logging.getLogger("codeunfold").handlers.clear()

    result_logger = logger.setup_logging()  # must not raise

    assert result_logger is not None
    assert any(
        isinstance(h, logging.StreamHandler) and not isinstance(h, RotatingFileHandler)
        for h in result_logger.handlers
    )
    result_logger.info("still usable after file handler failure")


def test_log_is_usable_without_raising():
    import logger
    logger.log.info("test message")
    logger.log.warning("test warning")
    logger.log.error("test error")  # must never raise
