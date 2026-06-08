"""
groq.py - Groq API provider using Groq's OpenAI-compatible endpoint.
Requires: pip install openai
Set env var: GROQ_API_KEY, or configure api_key_env in config.yaml.
"""
from .openai import OpenAIProvider


class GroqProvider(OpenAIProvider):
    def __init__(
        self,
        model: str,
        api_key_env: str = "GROQ_API_KEY",
        base_url: str = "https://api.groq.com/openai/v1",
    ):
        super().__init__(
            model=model,
            api_key_env=api_key_env,
            base_url=base_url,
            provider_name="groq",
            api_key_defaults=["GROQ_API_KEY"],
            api_key_example="gsk_...",
        )

    @property
    def name(self) -> str:
        return f"groq ({self.model})"
