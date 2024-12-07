import os
import logging

LOGS_DIR = 'logs'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
DATE_FORMAT = '%Y-%m-%d %H:%M:%S'

def ensure_logs_directory():
    """Ensure the logs directory exists."""
    if not os.path.exists(LOGS_DIR):
        os.makedirs(LOGS_DIR)

def setup_logger(logger_name, log_filename):
    """
    Sets up a logger with both file and console handlers.

    Args:
        logger_name (str): The name of the logger.
        log_filename (str): The name of the log file.

    Returns:
        logging.Logger: Configured logger instance.
    """
    ensure_logs_directory()

    logger = logging.getLogger(logger_name)

    # Prevent duplicate handlers
    if not logger.handlers:
        logger.setLevel(logging.INFO)

        # File handler
        log_file = os.path.join(LOGS_DIR, log_filename)
        file_handler = logging.FileHandler(log_file, mode='a')
        file_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(file_handler)

        # Console handler
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(logging.Formatter(LOG_FORMAT, datefmt=DATE_FORMAT))
        logger.addHandler(console_handler)

    return logger
