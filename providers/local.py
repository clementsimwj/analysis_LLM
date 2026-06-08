"""
local.py - Local GGUF provider powered by llama-cpp-python.
"""
import gc

from .base import BaseProvider


class LocalProvider(BaseProvider):
    def __init__(
        self,
        model_path: str,
        n_ctx: int = 4096,
        n_gpu_layers: int = -1,
        n_batch: int = 256,
        n_threads: int = 4,
    ):
        self.model_path = model_path
        from llama_cpp import Llama

        self._llm = Llama(
            model_path=model_path,
            n_ctx=n_ctx,
            n_gpu_layers=n_gpu_layers,
            n_batch=n_batch,
            n_threads=n_threads,
            verbose=False,
        )

    def complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        response = self._llm.create_chat_completion(
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
        )
        return response["choices"][0]["message"]["content"].strip()

    def unload(self):
        if hasattr(self, "_llm"):
            del self._llm
        gc.collect()

    @property
    def name(self) -> str:
        return f"local ({self.model_path})"
