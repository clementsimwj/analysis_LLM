"""
gemini.py - Google Gemini API provider.
Requires: pip install google-genai
Set env var: GEMINI_API_KEY, or configure api_key_env in config.yaml.
"""
from .base import BaseProvider
from .env import get_api_key


class GeminiProvider(BaseProvider):
    def __init__(self, model: str, api_key_env: str = "GEMINI_API_KEY"):
        self.model = model
        api_key = get_api_key(
            provider="gemini",
            api_key_env=api_key_env,
            defaults=["GEMINI_API_KEY", "GOOGLEGEMINI_API_KEY"],
            example="your_google_ai_studio_key",
        )

        try:
            from google import genai
            from google.genai import types

            self._mode = "genai"
            self._client = genai.Client(api_key=api_key)
            self._types = types
        except ImportError:
            import google.generativeai as genai

            self._mode = "generativeai"
            genai.configure(api_key=api_key)
            self._client = genai.GenerativeModel(model)

    def complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        prompt = f"{system}\n\n{user}"

        if self._mode == "genai":
            response = self._client.models.generate_content(
                model=self.model,
                contents=prompt,
                config=self._types.GenerateContentConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )
        else:
            response = self._client.generate_content(
                prompt,
                generation_config={
                    "max_output_tokens": max_tokens,
                    "temperature": temperature,
                },
            )

        text = getattr(response, "text", None)
        if not text:
            raise RuntimeError("Gemini returned an empty response.")
        return text.strip()

    def unload(self):
        pass

    @property
    def name(self) -> str:
        return f"gemini ({self.model})"
