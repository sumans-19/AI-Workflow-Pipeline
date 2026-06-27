"""OpenAI LLM client implementation."""

import random
import re
import time
from typing import Optional

from openai import APIConnectionError, APIError, APITimeoutError, OpenAI, RateLimitError, InternalServerError

from .base import BaseLLMClient
from ..config import settings
from ..exceptions import LLMError
from ..logging_config import logger


class OpenAIClient(BaseLLMClient):
    def __init__(self):
        super().__init__()
        settings.validate_llm()
        self.client = OpenAI(
            api_key=settings.LLM_API_KEY,
            base_url=settings.LLM_BASE_URL,
        )
        self.model = settings.LLM_MODEL
        self._provider_name = "llm_provider"

    @staticmethod
    def _sanitize(text: str) -> str:
        text = re.sub(r"<ctrl\d+>", "", text)
        text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)
        return text

    @staticmethod
    def _try_repair_json(text: str) -> str:
        """Attempt to repair truncated JSON responses using a state machine."""
        text = text.rstrip()
        
        # 1. Properly close any open string
        in_string = False
        escape_next = False
        for char in text:
            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif char == '"':
                in_string = not in_string
                
        if in_string:
            if text.endswith('\\'):
                text = text[:-1]
            text += '"'
            
        # 2. Track open braces/brackets outside of strings to close them
        stack = []
        in_string = False
        escape_next = False
        
        for char in text:
            if escape_next:
                escape_next = False
            elif char == '\\':
                escape_next = True
            elif char == '"':
                in_string = not in_string
            elif not in_string:
                if char == '{':
                    stack.append('}')
                elif char == '[':
                    stack.append(']')
                elif char == '}' and stack and stack[-1] == '}':
                    stack.pop()
                elif char == ']' and stack and stack[-1] == ']':
                    stack.pop()
                    
        # Remove any trailing commas or colons if we aren't in a string
        if not in_string:
            text = re.sub(r'[,:\s]+$', '', text)
            
        # Close all open structures
        while stack:
            text += stack.pop()
            
        return text

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        max_retries: int = 3,
        response_schema: Optional[dict] = None,
    ) -> str:
        retries = 0
        while retries < max_retries:
            try:
                request_kwargs = {
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": 0.3,
                }
                if response_schema is not None:
                    request_kwargs["response_format"] = {"type": "json_object"}
                    request_kwargs["max_tokens"] = 32768

                response = self.client.chat.completions.create(**request_kwargs)

                prompt_tokens = getattr(response.usage, "prompt_tokens", 0) or 0
                completion_tokens = getattr(response.usage, "completion_tokens", 0) or 0
                self._report_usage(self.model, prompt_tokens, completion_tokens)

                finish_reason = getattr(response.choices[0], "finish_reason", "stop")
                content = response.choices[0].message.content or ""
                content = self._sanitize(content)

                if finish_reason == "length" and response_schema is not None:
                    logger.warning(
                        "Response truncated (finish_reason=length, %d tokens). "
                        "Attempting JSON repair...",
                        completion_tokens,
                    )
                    content = self._try_repair_json(content)

                return content

            except RateLimitError:
                retries += 1
                wait_time = min(30, 2**retries) + random.uniform(0, 1)
                logger.warning(
                    "Rate limit hit. Retrying in %.1fs... (%d/%d)",
                    wait_time,
                    retries,
                    max_retries,
                )
                time.sleep(wait_time)

            except (APITimeoutError, APIConnectionError, InternalServerError):
                retries += 1
                wait_time = min(30, 2**retries) + random.uniform(0, 1)
                logger.warning(
                    "Transient error (503/timeout). Retrying in %.1fs... (%d/%d)",
                    wait_time,
                    retries,
                    max_retries,
                )
                time.sleep(wait_time)

            except APIError as e:
                raise LLMError(f"API Error: {e}") from e
            except Exception as e:
                raise LLMError(f"Unexpected LLM error: {e}") from e

        raise LLMError("Max retries reached. Please check your API quota.")
