import logging
import sys
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Optional

def setup_logger(
    name: str = "claude_lit_workflow",
    log_file: str = "system.log",
    level: int = logging.INFO,
    max_bytes: int = 5 * 1024 * 1024,  # 5MB
    backup_count: int = 3
) -> logging.Logger:
    """
    Setup a logger with console and rotating file handlers.
    
    Args:
        name: Logger name
        log_file: Log filename (relative to project root/logs)
        level: Logging level
        max_bytes: Maximum size of log file before rotation
        backup_count: Number of backup files to keep
        
    Returns:
        Configured logger instance
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # Prevent adding handlers multiple times if logger is already configured
    if logger.handlers:
        return logger

    # Create logs directory if it doesn't exist
    project_root = Path(__file__).resolve().parent.parent.parent
    log_dir = project_root / "logs"
    log_dir.mkdir(exist_ok=True)
    
    log_path = log_dir / log_file

    # Formatter
    formatter = logging.Formatter(
        '[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    # File Handler (Rotating)
    try:
        file_handler = RotatingFileHandler(
            log_path,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8'
        )
        file_handler.setFormatter(formatter)
        file_handler.setLevel(level)
        logger.addHandler(file_handler)
    except Exception as e:
        print(f"Failed to setup file logging: {e}", file=sys.stderr)

    # Console Handler (Stream)
    # Only log WARNING and above to console to keep UI clean, 
    # unless debug is enabled (which we might want to control via arg later)
    console_handler = logging.StreamHandler(sys.stdout)
    console_formatter = logging.Formatter('[%(levelname)s] %(message)s')
    console_handler.setFormatter(console_formatter)
    console_handler.setLevel(logging.WARNING) # Default to WARNING for console
    logger.addHandler(console_handler)

    return logger

# Create a default instance for easy import
# Usage: from src.utils.logger import logger
logger = setup_logger()
