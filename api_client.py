import os
import asyncio
import aiohttp
import logging
from typing import Optional

log = logging.getLogger(__name__)

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
API_URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = "openrouter/free"

MAX_RETRIES = 3
BASE_DELAY = 1.0
MAX_DELAY = 8.0
TIMEOUT_TOTAL = 30.0
TIMEOUT_CONNECT = 10.0


class APIError(Exception):
    pass


class RateLimitError(APIError):
    def __init__(self, retry_after: float):
        self.retry_after = retry_after
        super().__init__(f"Rate limited, retry after {retry_after}s")


class AuthError(APIError):
    pass


class ModelError(APIError):
    pass


class NetworkError(APIError):
    pass


class APIClient:
    def __init__(self):
        self._session: Optional[aiohttp.ClientSession] = None
        self._headers = {
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/certified-chad/mr-meow",
            "X-Title": "Mr. Meow",
        }

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            timeout = aiohttp.ClientTimeout(total=TIMEOUT_TOTAL, connect=TIMEOUT_CONNECT)
            self._session = aiohttp.ClientSession(timeout=timeout, headers=self._headers)
        return self._session

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        system_prompt: str,
        max_tokens: int = 300,
    ) -> str:
        session = await self._get_session()

        payload = {
            "model": MODEL,
            "messages": messages,
            "max_tokens": max_tokens,
        }

        if system_prompt:
            payload["system"] = system_prompt

        last_exception = None
        delay = BASE_DELAY

        for attempt in range(MAX_RETRIES):
            try:
                async with session.post(API_URL, json=payload) as response:
                    if response.status == 200:
                        data = await response.json()
                        if "choices" in data and data["choices"]:
                            return data["choices"][0]["message"]["content"]
                        raise ModelError("No choices in response")

                    elif response.status == 429:
                        retry_after = float(response.headers.get("Retry-After", delay))
                        if attempt < MAX_RETRIES - 1:
                            log.warning(
                                f"Rate limited, waiting {retry_after}s (attempt {attempt + 1}/{MAX_RETRIES})"
                            )
                            await asyncio.sleep(retry_after)
                            delay = min(delay * 2, MAX_DELAY)
                            continue
                        raise RateLimitError(retry_after)

                    elif response.status == 401:
                        raise AuthError("Invalid OpenRouter API key")

                    elif response.status >= 500:
                        if attempt < MAX_RETRIES - 1:
                            log.warning(
                                f"Server error {response.status}, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                            )
                            await asyncio.sleep(delay)
                            delay = min(delay * 2, MAX_DELAY)
                            continue
                        raise ModelError(f"OpenRouter server error: {response.status}")

                    else:
                        error_text = await response.text()
                        raise ModelError(f"API error {response.status}: {error_text}")

            except aiohttp.ClientError as e:
                last_exception = e
                if attempt < MAX_RETRIES - 1:
                    log.warning(
                        f"Network error: {e}, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, MAX_DELAY)
                    continue
                raise NetworkError(f"Network error after {MAX_RETRIES} retries: {e}")

            except asyncio.TimeoutError:
                last_exception = "Request timeout"
                if attempt < MAX_RETRIES - 1:
                    log.warning(
                        f"Timeout, retrying in {delay}s (attempt {attempt + 1}/{MAX_RETRIES})"
                    )
                    await asyncio.sleep(delay)
                    delay = min(delay * 2, MAX_DELAY)
                    continue
                raise NetworkError("Request timeout after retries")

        raise NetworkError(f"Failed after {MAX_RETRIES} attempts: {last_exception}")