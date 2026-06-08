"""
openai.py — OpenAI API provider.
Requires: pip install openai
Set env var: OPENAI_API_KEY
"""
from .base import BaseProvider
from .env import get_api_key

class OpenAIProvider(BaseProvider):
    def __init__(
        self,
        model: str,
        api_key_env: str = "OPENAI_API_KEY",
        base_url: str | None = None,
        provider_name: str = "openai",
        api_key_defaults: list[str] | None = None,
        api_key_example: str = "sk-...",
    ):
        self.model = model
        api_key = get_api_key(
            provider=provider_name,
            api_key_env=api_key_env,
            defaults=api_key_defaults or ["OPENAI_API_KEY"],
            example=api_key_example,
        )
        from openai import OpenAI
        kwargs = {"api_key": api_key}
        if base_url:
            kwargs["base_url"] = base_url
        self._client = OpenAI(**kwargs)

    def complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        response = self._client.chat.completions.create(
            model=self.model,
            max_tokens=max_tokens,
            temperature=temperature,
            messages=[
                {"role": "system", "content": system},
                {"role": "user",   "content": user}
            ]
        )
        return response.choices[0].message.content.strip()

    def unload(self):
        pass  # no-op for API providers

    @property
    def name(self) -> str:
        return f"openai ({self.model})"
