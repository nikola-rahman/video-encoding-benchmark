import os
from pathlib import Path

import yaml
from dotenv import load_dotenv

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "benchmark.yaml"


def load_config(config_path: Path | str | None = None) -> dict:
    """Load benchmark.yaml and return config dict."""
    load_dotenv()

    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        return yaml.safe_load(f)
