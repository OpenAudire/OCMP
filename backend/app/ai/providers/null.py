"""The Null provider: AI is off. It has no network code at all."""

from app.ai.errors import AIDisabledError
from app.ai.privacy import GuardedRequest
from app.ai.providers.base import Completion


class NullProvider:
    name = "null"

    async def generate_structured(self, request: GuardedRequest) -> Completion:
        raise AIDisabledError
