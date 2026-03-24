import os
import re
from pathlib import Path

import yaml
from dotenv import load_dotenv

_ENV_VAR_PATTERN = re.compile(r"\$\{([^}]+)\}")

DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "benchmark.yaml"


def _interpolate_env(value):
    """Recursively replace ${ENV_VAR} placeholders with environment variable values."""
    if isinstance(value, str):
        def replacer(match):
            var_name = match.group(1)
            env_val = os.environ.get(var_name)
            if env_val is None:
                raise ValueError(f"Environment variable {var_name!r} referenced in config but not set")
            return env_val
        return _ENV_VAR_PATTERN.sub(replacer, value)
    elif isinstance(value, dict):
        return {k: _interpolate_env(v) for k, v in value.items()}
    elif isinstance(value, list):
        return [_interpolate_env(item) for item in value]
    return value


def load_config(config_path: Path | str | None = None) -> dict:
    """Load benchmark.yaml, interpolate ${ENV_VAR} references, and return config dict."""
    load_dotenv()

    if config_path is None:
        config_path = DEFAULT_CONFIG_PATH
    config_path = Path(config_path)

    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")

    with open(config_path) as f:
        raw = yaml.safe_load(f)

    return _interpolate_env(raw)
