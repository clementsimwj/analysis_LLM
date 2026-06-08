"""
env.py - Shared environment variable helpers for API providers.
"""
import os
from collections.abc import Iterable


def _as_names(value) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, Iterable):
        return [str(item) for item in value if str(item)]
    return [str(value)]


def get_api_key(provider: str, api_key_env, defaults: list[str], example: str) -> str:
    env_names = []
    for name in _as_names(api_key_env) + defaults:
        if name and name not in env_names:
            env_names.append(name)

    for name in env_names:
        value = os.environ.get(name)
        if value:
            return value

    expected = " or ".join(env_names)
    raise EnvironmentError(
        f"[{provider}] Missing API key. Add {expected} to .env, for example:\n"
        f"  {env_names[0]}={example}"
    )
