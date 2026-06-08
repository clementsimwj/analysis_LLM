"""
app_config.py - Configuration and .env helpers for the analytics pipeline.
"""
import os
import sys
from pathlib import Path
from typing import Any

import yaml


CONFIG_PATH = "config.yaml"


def load_dotenv(path: str = ".env") -> None:
    """
    Load key=value pairs from a local .env file into os.environ.

    Existing environment variables win, so shell exports can override .env.
    This supports the simple format used by this project without adding another
    required dependency.
    """
    env_path = Path(path)
    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue

        if line.startswith("export "):
            line = line[len("export ") :].strip()

        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip("'\"")

        if key and key not in os.environ:
            os.environ[key] = value


def load_config(path: str = CONFIG_PATH) -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        print(f"[ERROR] Config file not found: {path}")
        print("        Make sure config.yaml is in the same folder as analytics.py")
        sys.exit(1)

    with config_path.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def completion_options(
    cfg: dict[str, Any],
    *,
    default_max_tokens: int,
    default_temperature: float,
    max_tokens_key: str = "max_tokens",
) -> dict[str, Any]:
    return {
        "max_tokens": int(cfg.get(max_tokens_key, default_max_tokens)),
        "temperature": float(cfg.get("temperature", default_temperature)),
    }


def runtime_options(cfg: dict[str, Any]) -> dict[str, Any]:
    return {
        "request_delay_seconds": float(cfg.get("request_delay_seconds", 0.0)),
        "max_retries": int(cfg.get("max_retries", 0)),
        "retry_base_delay_seconds": float(cfg.get("retry_base_delay_seconds", 30.0)),
    }
