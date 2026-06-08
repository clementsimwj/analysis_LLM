"""
providers/__init__.py
Factory function — builds the right provider from config.
Adding a new provider: create providers/yourprovider.py,
subclass BaseProvider, then add it to the factory below.
"""
from .base import BaseProvider

SUPPORTED_PROVIDERS = ("local", "anthropic", "openai", "gemini", "groq")

DEFAULT_MODELS = {
    "local": "./models/Llama-3.2-3B-Instruct-Q4_K_M.gguf",
    "anthropic": "claude-sonnet-4-20250514",
    "openai": "gpt-4o-mini",
    "gemini": "gemini-2.5-flash",
    "groq": "llama-3.3-70b-versatile",
}


def build_provider(cfg: dict) -> BaseProvider:
    """
    Build a provider from a config dict.
    Expected keys: provider, model, and provider-specific options.
    """
    provider_type = cfg.get("provider", "local").lower()
    model = cfg.get("model") or DEFAULT_MODELS.get(provider_type)
    if not model:
        raise ValueError(f"Missing model for provider '{provider_type}'.")

    if provider_type == "local":
        from .local import LocalProvider
        return LocalProvider(
            model_path   = model,
            n_ctx        = cfg.get("n_ctx", 4096),
            n_gpu_layers = cfg.get("n_gpu_layers", -1),
            n_batch      = cfg.get("n_batch", 256),
            n_threads    = cfg.get("n_threads", 4),
        )

    elif provider_type == "anthropic":
        from .anthropic import AnthropicProvider
        return AnthropicProvider(
            model       = model,
            api_key_env = cfg.get("api_key_env", "ANTHROPIC_API_KEY"),
            base_url    = cfg.get("base_url"),
        )

    elif provider_type == "openai":
        from .openai import OpenAIProvider
        return OpenAIProvider(
            model       = model,
            api_key_env = cfg.get("api_key_env", "OPENAI_API_KEY"),
            base_url    = cfg.get("base_url"),
        )

    elif provider_type == "gemini":
        from .gemini import GeminiProvider
        return GeminiProvider(
            model       = model,
            api_key_env = cfg.get("api_key_env", "GEMINI_API_KEY"),
        )

    elif provider_type == "groq":
        from .groq import GroqProvider
        return GroqProvider(
            model       = model,
            api_key_env = cfg.get("api_key_env", "GROQ_API_KEY"),
            base_url    = cfg.get("base_url", "https://api.groq.com/openai/v1"),
        )

    else:
        raise ValueError(
            f"Unknown provider: '{provider_type}'. "
            f"Supported: {', '.join(SUPPORTED_PROVIDERS)}. "
            f"To add a new one, create providers/{provider_type}.py."
        )
