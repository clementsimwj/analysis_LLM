"""
anthropic.py — Anthropic Claude API provider.
Requires: pip install anthropic
Set env var: ANTHROPIC_API_KEY
"""
from .base import BaseProvider
from .env import get_api_key

class AnthropicProvider(BaseProvider):
    def __init__(self, model: str, api_key_env: str = "ANTHROPIC_API_KEY", base_url: str | None = None):
        self.model = model
        api_key = get_api_key(
            provider="anthropic",
            api_key_env=api_key_env,
            defaults=["ANTHROPIC_API_KEY"],
            example="sk-ant-...",
        )
        import anthropic as _anthropic
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = _anthropic.Anthropic(**kwargs)

    def complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        response = self._client.messages.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            system=system,
            messages=[{"role": "user", "content": user}]
        )
        return response.content[0].text.strip()

    def unload(self):
        pass  # no-op for API providers

    @property
    def name(self) -> str:
        return f"anthropic ({self.model})"
