from __future__ import annotations

import os
import sys
import logging
import datetime
from typing import Callable, Optional

def get_app_dir() -> str:
    """Returns directory where the executable or main script resides."""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    # If called from src/, go up one level to project root
    src_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.dirname(src_dir)

class GuiLogHandler(logging.Handler):
    """Logging handler that dispatches log records to a GUI callback function."""
    def __init__(self, callback: Optional[Callable[[str, str], None]] = None):
        super().__init__()
        self.callback = callback

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            if self.callback:
                self.callback(msg, record.levelname)
        except Exception:
            self.handleError(record)

# Global logger instance
logger = logging.getLogger("TahoDumper")
gui_handler: Optional[GuiLogHandler] = None

def setup_logger(gui_callback: Optional[Callable[[str, str], None]] = None) -> logging.Logger:
    """Configures application logger with console, file, and optional GUI output."""
    global gui_handler
    logger.setLevel(logging.DEBUG)
    logger.handlers.clear()

    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-5s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. Console handler
    console_h = logging.StreamHandler(sys.stdout)
    console_h.setLevel(logging.DEBUG)
    console_h.setFormatter(formatter)
    logger.addHandler(console_h)

    # 2. File handler in app directory
    app_dir = get_app_dir()
    logs_dir = os.path.join(app_dir, "logs")
    os.makedirs(logs_dir, exist_ok=True)

    today_str = datetime.datetime.now().strftime("%Y%m%d")
    log_filename = os.path.join(logs_dir, f"taho_debug_{today_str}.log")
    main_log = os.path.join(app_dir, "taho_debug.log")

    try:
        # Rotating or append file handler
        fh_dated = logging.FileHandler(log_filename, mode="a", encoding="utf-8")
        fh_dated.setLevel(logging.DEBUG)
        fh_dated.setFormatter(formatter)
        logger.addHandler(fh_dated)

        fh_main = logging.FileHandler(main_log, mode="a", encoding="utf-8")
        fh_main.setLevel(logging.DEBUG)
        fh_main.setFormatter(formatter)
        logger.addHandler(fh_main)
    except Exception as e:
        print(f"Warning: could not initialize file logger: {e}", file=sys.stderr)

    # 3. GUI Handler
    gui_handler = GuiLogHandler(gui_callback)
    gui_handler.setLevel(logging.DEBUG)
    gui_handler.setFormatter(formatter)
    logger.addHandler(gui_handler)

    logger.info("=" * 60)
    logger.info("Tacho Card Reader Dumper Logger Initialized")
    logger.info(f"Application directory: {app_dir}")
    logger.info(f"Log files: {main_log} and {log_filename}")
    logger.info("=" * 60)

    return logger

def set_gui_callback(callback: Callable[[str, str], None]):
    """Update or register GUI log callback."""
    global gui_handler
    if gui_handler:
        gui_handler.callback = callback

def format_hex(data: list[int] | bytes) -> str:
    """Format bytes/ints into spaced hex string: 00 A4 04 ..."""
    if isinstance(data, (bytes, bytearray)):
        return " ".join(f"{b:02X}" for b in data)
    return " ".join(f"{b:02X}" for b in data)
