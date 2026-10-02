from abc import ABC, abstractmethod

from app.llm.contracts import ComposeContext, LLMCallResult


class LLMProvider(ABC):
    name = "none"

    @abstractmethod
    def classify_intent(self, question: str, active_siafi: str | None) -> LLMCallResult:
        """Classifica pergunta e contexto mínimo, sem dados financeiros."""

    @abstractmethod
    def friendly(self, structured: str) -> str: ...
    @abstractmethod
    def plan(self, question: str, active_siafi: str | None) -> LLMCallResult: ...

    @abstractmethod
    def compose(self, context: ComposeContext) -> LLMCallResult: ...
