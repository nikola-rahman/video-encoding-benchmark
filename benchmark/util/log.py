import logging


def setup_logging(name: str = "benchmark") -> logging.Logger:
    """Configure and return a logger with consistent formatting."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )
    return logging.getLogger(name)
