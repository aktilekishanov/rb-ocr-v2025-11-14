from typing import Optional, Dict, Any, Type, Union

from pydantic import BaseModel


class LLMAdapter:
    """
    Unified wrapper around LLM clients that exposes a consistent `send` method.

    Supports both raw string responses and structured Pydantic output.

    Args:
        client: An instance implementing `send(system_prompt, user_prompt, **kwargs)`
        default_kwargs: Optional defaults (e.g., model, temperature) merged into each call

    Example:
        >>> from src.common.gpt.dmz_client import DMZClient
        >>> client = DMZClient()
        >>> adapter = LLMAdapter(client, default_kwargs={"timeout": 30})
        >>>
        >>> # Raw string response
        >>> result = adapter.send(
        ...     system_prompt="You are a helpful assistant",
        ...     user_prompt="What is 2+2?"
        ... )
        >>>
        >>> # Structured response with Pydantic
        >>> class Answer(BaseModel):
        ...     result: int
        ...     explanation: str
        >>>
        >>> answer = adapter.send(
        ...     system_prompt="You are a math tutor",
        ...     user_prompt="What is 2+2?",
        ...     response_model=Answer
        ... )
        >>> print(answer.result)  # 4
    """

    def __init__(self, client, default_kwargs: Optional[Dict[str, Any]] = None):
        """
        Initialize the adapter with a client and optional default parameters.

        Args:
            client: Client instance with a `send` method
            default_kwargs: Default parameters for all requests (e.g., model, temperature, timeout)
        """
        self.client = client
        self.default_kwargs: Dict[str, Any] = dict(default_kwargs or {})

    def send(
            self,
            system_prompt: str,
            user_prompt: str,
            response_model: Type[BaseModel],
            **kwargs: Any
    ) -> BaseModel:
        """
        Send a prompt through the underlying client with optional structured output.

        Args:
            user_prompt: The user's input/question
            system_prompt: System instructions for the model (default: empty string)
            response_model: Optional Pydantic model for structured output
            **kwargs: Additional parameters (model, temperature, timeout, etc.)
                     These override adapter-level default_kwargs

        Returns:
            If response_model is provided: Validated Pydantic model instance
            Otherwise: Raw string response from the LLM

        Raises:
            Any exceptions raised by the underlying client (network errors, validation errors, etc.)

        Note:
            Per-call kwargs override adapter-level `default_kwargs`.
            None values are filtered out to avoid overriding defaults.
        """
        # Merge default kwargs with per-call kwargs
        params = {**self.default_kwargs, **kwargs}

        # Call the underlying client
        return self.client.send(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_model=response_model,
            **params
        )
