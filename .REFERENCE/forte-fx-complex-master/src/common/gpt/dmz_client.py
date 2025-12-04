import json
import logging
from typing import Optional, Type

import requests
from pydantic import BaseModel
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
    after_log,
)

from src.common.logger.logger_config import get_logger
from src.common.pydantic_models.model_combined_json import ParsingResults
from src.core.config import app_settings

logger = get_logger("gpt")


def pydantic_schema_dict(model_cls: type[BaseModel]) -> dict:
    """
    Returns JSON Schema from Pydantic model.
    Compatible with Pydantic v2.
    Adds "additionalProperties": false and ensures all properties are in "required" for strict mode.
    """
    if hasattr(model_cls, "model_json_schema"):  # Pydantic v2
        schema = model_cls.model_json_schema()
    else:
        raise RuntimeError("Unsupported Pydantic version")

    # Recursively process schema for OpenAI strict mode
    def process_schema(obj):
        if isinstance(obj, dict):
            # If it's an object type, ensure required includes all properties
            if obj.get("type") == "object" and "properties" in obj:
                obj["additionalProperties"] = False
                # Make all properties required for strict mode
                if "properties" in obj:
                    obj["required"] = list(obj["properties"].keys())

            # Recurse into nested structures
            for value in obj.values():
                process_schema(value)

        elif isinstance(obj, list):
            for item in obj:
                process_schema(item)

    process_schema(schema)
    return schema


class DMZClient:
    def __init__(
            self,
            model: str = "gpt-4.1",
            temperature: float = 0.1,
    ):
        pass

    @retry(
        stop=stop_after_attempt(4),
        wait=wait_exponential(multiplier=1.0, max=12.0),
        retry=retry_if_exception_type((requests.RequestException, TimeoutError, ConnectionError)),
        before_sleep=before_sleep_log(logging.getLogger("pipeline"), logging.WARNING),
        after=after_log(logger, log_level=1),
        reraise=True,
    )
    def send(
            self,
            system_prompt: str,
            user_prompt: str,
            response_model: Type[BaseModel],
            model: Optional[str] = "gpt-4.1",
            temperature: Optional[float] = 0.1,
            timeout: Optional[float] = 600,
    ):
        """
        Send a request to the DMZ API with optional structured output.

        Args:
            system_prompt: System instructions for the model
            user_prompt: User's input prompt
            response_model: Optional Pydantic model for structured output validation
            model: Override default model for this request
            temperature: Override default temperature for this request
            timeout: Request timeout in seconds

        Returns:
            If response_model is provided: validated Pydantic model instance
            Otherwise: raw string response

        Raises:
            requests.RequestException: On network/HTTP errors
            ValidationError: If response doesn't match the provided Pydantic model
            ValueError: If the API returns invalid JSON
        """

        # Build messages array (OpenAI format)
        messages = [
            {"role": "system", "content": system_prompt.strip()},
            {"role": "user", "content": user_prompt.strip()},
        ]

        schema_dict = pydantic_schema_dict(response_model)
        response_format = {
            "type": "json_schema",
            "json_schema": {
                "name": response_model.__name__,
                "strict": True,
                "schema": schema_dict,
            },
        }
        # Build payload
        payload = {
            "Model": model,
            "Content": json.dumps(messages, ensure_ascii=False),
            "MaxTokens": 32767,
            "Temperature": temperature,
            "response_format": response_format,
        }

        # Make the request
        # try:
        headers = {
            "Content-Type": "application/json"
        }
        resp = requests.post(
            url=app_settings.DMZ_URL,
            json=payload,
            headers=headers,
            verify=app_settings.VERIFY_SSL,
            timeout=timeout,
        )
        resp.raise_for_status()

        # Parse response (DMZ returns echoed request + OpenAI response)
        response_text = resp.text

        # Extract the OpenAI response (after the echoed request)
        json_start = response_text.find('{"choices"')
        if json_start == -1:
            logger.error(f"Unexpected response format: {response_text[:200]}")
            raise ValueError("DMZ API response doesn't contain expected OpenAI format")

        openai_response = response_text[json_start:]
        response_data = json.loads(openai_response)

        logger.info(f"Token Usage: {response_data.get('usage')}")

        # Extract content from choices
        if not response_data.get("choices") or len(response_data["choices"]) == 0:
            raise ValueError("DMZ API response contains no choices")

        content_str = response_data["choices"][0]["message"]["content"]

        # Handle structured output
        if response_model is not None:
            # try:
            # Content should already be valid JSON matching the schema
            content_obj = json.loads(content_str)
            validated_instance = response_model.model_validate(content_obj)
            logger.debug(f"Successfully validated response against {response_model.__name__}")
            return validated_instance
        # except json.JSONDecodeError as e:
        #     logger.error(f"Failed to parse JSON from structured output: {e}")
        #     logger.error(f"Content preview: {content_str[:200]}")
        #     raise ValueError(f"Structured output is not valid JSON: {e}")
        # except ValidationError as e:
        #     logger.error(f"Validation failed for {response_model.__name__}: {e}")
        #     logger.error(f"Content preview: {content_str[:200]}")
        #     raise

        # Fallback: return raw string (with cleanup for backward compatibility)
        content_str = content_str.strip().removeprefix("```json").removesuffix("```").strip()
        logger.debug(f"Returning raw string response (length: {len(content_str)})")
        return content_str

        # except requests.RequestException as e:
        #     logger.error(f"Request failed: {e}")
        #     raise
        # except json.JSONDecodeError as e:
        #     logger.error(f"Failed to parse DMZ response as JSON: {e}")
        #     logger.error(f"Response preview: {resp.text[:200] if 'resp' in locals() else 'N/A'}")
        #     raise ValueError(f"Invalid JSON response from DMZ API: {e}")
        # except Exception as e:
        #     logger.error(f"Unexpected error in DMZ client: {e}", exc_info=True)
        #     raise

