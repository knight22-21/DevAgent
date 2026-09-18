from dataclasses import dataclass
from typing import Literal

from devagent.chat.context import estimate_prompt_tokens


@dataclass
class Message:
    role: Literal["user", "assistant"]
    content: str

class ConversationHistory:
    def __init__(self, system_prompt: str, max_tokens: int = 6000):
        self.system_prompt = system_prompt
        self.max_tokens = max_tokens
        self.messages: list[Message] = []
        self._system_tokens = estimate_prompt_tokens(system_prompt)

    def add_user_message(self, content: str) -> None:
        self.messages.append(Message(role="user", content=content))
        self._trim_if_needed()

    def add_assistant_message(self, content: str) -> None:
        self.messages.append(Message(role="assistant", content=content))

    def to_messages(self) -> list:
        """Returns messages as list of llm.Message for LLMClient.complete()."""
        from devagent.core.llm import Message as LLMMessage
        result = [LLMMessage(role="system", content=self.system_prompt)]
        for msg in self.messages:
            result.append(LLMMessage(role=msg.role, content=msg.content))
        return result

    def _trim_if_needed(self) -> None:
        """
        If total estimated tokens exceed max_tokens, remove the oldest
        user+assistant message pair from the history. Keeps the system
        prompt intact always. Never removes the most recent user message.
        """
        while self._total_tokens() > self.max_tokens and len(self.messages) > 1:
            # Remove oldest pair (user + assistant)
            if len(self.messages) >= 2:
                self.messages.pop(0)  # remove oldest user
                if self.messages and self.messages[0].role == "assistant":
                    self.messages.pop(0)  # remove its response
            else:
                break

    def _total_tokens(self) -> int:
        msg_tokens = sum(estimate_prompt_tokens(m.content) for m in self.messages)
        return self._system_tokens + msg_tokens

    @property
    def message_count(self) -> int:
        return len(self.messages)
