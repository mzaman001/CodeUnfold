import logging
import os

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
        try:
            log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'codeunfold.log')
            fh = logging.FileHandler(log_file)
            fh.setFormatter(formatter)
            logger.addHandler(fh)
        except OSError:
            pass

        # Console handler
        ch = logging.StreamHandler()
        ch.setFormatter(formatter)
        logger.addHandler(ch)
    
    return logger

log = setup_logging()
