"""The provider interface and what adapters share."""

import re
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.ai.errors import ProviderError
from app.ai.privacy import GuardedRequest

REQUEST_TIMEOUT_SECONDS = 60.0


@dataclass(frozen=True)
class ProviderConfig:
    """What an adapter needs, decrypted for the moment of the call."""

    model: str
    base_url: str | None = None
    api_key: str | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class Completion:
    """A provider's answer, with the counts used for budgets."""

    text: str
    input_tokens: int
    output_tokens: int
    model: str
    request_id: str | None = None


class LLMProvider(Protocol):
    """Adapter for one provider. It accepts only requests the privacy guard sealed."""

    name: str

    async def generate_structured(self, request: GuardedRequest) -> Completion:
        """Send a guarded request and return the text of the answer."""
        ...


def client_for(transport: httpx.AsyncBaseTransport | None) -> httpx.AsyncClient:
    """An HTTP client that never follows redirects (a redirect would carry the key along)."""
    return httpx.AsyncClient(
        transport=transport, timeout=REQUEST_TIMEOUT_SECONDS, follow_redirects=False
    )


def scrub(text: str, secret: str | None) -> str:
    """Shorten provider text for messages and logs, removing the key if it was echoed."""
    if secret:
        text = text.replace(secret, "[key]")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:300]


def int_or_zero(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) and value >= 0 else 0


async def post_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    headers: dict[str, str],
    body: dict[str, object],
    api_key: str | None,
) -> httpx.Response:
    """POST and turn transport failures and error statuses into ``ProviderError``."""
    try:
        response = await client.post(url, headers=headers, json=body)
    except httpx.TimeoutException:
        raise ProviderError("The provider did not answer in time.") from None
    except httpx.HTTPError as exc:
        raise ProviderError(f"The provider could not be reached ({type(exc).__name__}).") from None
    if response.status_code >= 300:
        detail = ""
        try:
            data = response.json()
            error = data.get("error") if isinstance(data, dict) else None
            if isinstance(error, dict):
                detail = str(error.get("message") or "")
            elif isinstance(error, str):
                detail = error
        except ValueError:
            pass
        message = f"The provider answered with status {response.status_code}."
        if detail:
            message += " " + scrub(detail, api_key)
        raise ProviderError(message, status_code=response.status_code)
    return response


def json_body(response: httpx.Response) -> dict[str, object]:
    try:
        data = response.json()
    except ValueError:
        raise ProviderError("The provider's answer was not JSON.") from None
    if not isinstance(data, dict):
        raise ProviderError("The provider's answer had an unexpected shape.")
    return data
