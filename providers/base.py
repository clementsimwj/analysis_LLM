"""
base.py — Abstract interface that every provider must implement.
Adding a new provider = subclass BaseProvider and implement complete().
"""
from abc import ABC, abstractmethod

class BaseProvider(ABC):
    """All providers must implement this interface."""

    @abstractmethod
    def complete(self, system: str, user: str, max_tokens: int, temperature: float) -> str:
        """
        Send a prompt and return the response as a string.

        Args:
            system:      System/instruction prompt
            user:        User message
            max_tokens:  Max tokens to generate
            temperature: Sampling temperature (0 = deterministic)

        Returns:
            Response text as a plain string
        """
        pass

    @abstractmethod
    def unload(self):
        """Release any resources (e.g. free model from RAM). No-op for API providers."""
        pass

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable provider name for logging."""
        pass