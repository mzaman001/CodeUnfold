import logging
import os
from logging.handlers import RotatingFileHandler

def setup_logging():
    logger = logging.getLogger('codeunfold')
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

        # File handler -- best-effort. Some deployment platforms (certain
        # containerized PaaS setups, read-only filesystems) don't allow
        # writing next to the app source. Since this module's `log`
        # object is created at import time, an unguarded FileHandler
        # here would crash the entire app before a single page loads.
        # Console logging alone is still useful (most platforms capture
        # stdout/stderr), so fall back to that instead of failing hard.
        #
        # RotatingFileHandler (not plain FileHandler) caps the log at
        # 1MB with 3 rotated backups (~4MB total ceiling) -- a plain
        # FileHandler has no size limit at all, so a popular long-running
        # deployment would otherwise grow codeunfold.log without bound.
        try:
            log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'codeunfold.log')
            # encoding="utf-8" is required on Windows -- without it this
            # defaults to the system codepage (cp1252), which raises
            # UnicodeEncodeError the moment a logged message contains a
            # character outside it (common in AI-generated text: em
            # dashes, smart quotes, arrows).
            fh = RotatingFileHandler(log_file, maxBytes=1_000_000, backupCount=3, encoding="utf-8")
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except OSError:
            pass

        # Console handler. errors="backslashreplace" on the stream itself
        # means a stray unencodable character degrades to an escaped
        # sequence in the console instead of crashing the request that
        # triggered the log line -- logging should never be why a feature
        # breaks.
        ch = logging.StreamHandler()
        try:
            ch.stream.reconfigure(errors="backslashreplace")
        except (AttributeError, ValueError):
            pass
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    
    return logger

log = setup_logging()
