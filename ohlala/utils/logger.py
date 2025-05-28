"""
Logging utilities for Ohlala.
"""
import os
import logging
import traceback
import inspect
from datetime import datetime
from pathlib import Path

log_dir = os.path.expanduser("~/.ohlala/logs")
Path(log_dir).mkdir(parents=True, exist_ok=True)

logger = logging.getLogger("ohlala")
logger.setLevel(logging.DEBUG)

current_date = datetime.now().strftime("%Y-%m-%d")
log_file = os.path.join(log_dir, f"ohlala_{current_date}.log")
file_handler = logging.FileHandler(log_file, encoding='utf-8')
file_handler.setLevel(logging.DEBUG)

formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(lineno)d - %(message)s')
file_handler.setFormatter(formatter)

logger.addHandler(file_handler)

def get_caller_filename():
    """
    Get the filename of the caller.
    
    Returns:
        str: The filename of the caller.
    """

    stack = inspect.stack()
    # The caller is the third frame in the stack (index 2)
    caller_frame = stack[2]

    caller_filename = os.path.basename(caller_frame.filename)
    return caller_filename

def log_error(message, error, context=None):
    """
    Log an error with detailed information.
    
    Args:
        message: The error message
        error: The exception object
        context: Additional context information (optional)
    """
    caller_filename = get_caller_filename()
    error_details = f"[{caller_filename}] {message}: {str(error)}"
    if context:
        error_details += f" | Context: {context}"

    error_details += f"\nTraceback: {traceback.format_exc()}"
    
    logger.error(error_details)

def log_warning(message, context=None):
    """
    Log a warning with context information.
    
    Args:
        message: The warning message
        context: Additional context information (optional)
    """
    caller_filename = get_caller_filename()
    warning_details = f"[{caller_filename}] {message}"
    if context:
        warning_details += f" | Context: {context}"
    
    logger.warning(warning_details)

def log_info(message, context=None):
    """
    Log an info message with context information.
    
    Args:
        message: The info message
        context: Additional context information (optional)
    """
    caller_filename = get_caller_filename()
    info_details = f"[{caller_filename}] {message}"
    if context:
        info_details += f" | Context: {context}"
    
    logger.info(info_details)