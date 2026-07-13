import logging
import sys
from datetime import datetime
from pathlib import Path

LOG_DIR = Path(__file__).parent.parent.parent / "logs"
LOG_DIR.mkdir(exist_ok=True)

LOG_FILE = LOG_DIR / f"ayxan_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"

formatter = logging.Formatter(
    fmt="%(asctime)s | %(levelname)-8s | %(name)-12s | %(message)s",
    datefmt="%H:%M:%S"
)

file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
file_handler.setFormatter(formatter)

console_handler = logging.StreamHandler(sys.stdout)
console_handler.setFormatter(formatter)

def get_logger(name: str) -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.DEBUG)
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        logger.propagate = False
    return logger

def log_latency(logger: logging.Logger, stage: str, seconds: float):
    logger.info(f"⏱  {stage} latency: {seconds * 1000:.1f} ms")