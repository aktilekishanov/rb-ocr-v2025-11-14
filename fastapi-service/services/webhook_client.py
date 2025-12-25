import logging
import os
from typing import List

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WebhookPayload(BaseModel):
    err_codes: List[int] = Field(
        default_factory=list, description="List of integer error codes"
    )
    request_id: int = Field(..., description="Original request ID")
    status: str = Field(..., description="'success' or 'fail'")


class WebhookClient:
    """Webhook client with environment-based configuration.

    Environment variables (REQUIRED):
        WEBHOOK_URL: Target webhook endpoint URL
        WEBHOOK_USERNAME: Basic auth username
        WEBHOOK_PASSWORD: Basic auth password
        WEBHOOK_TIMEOUT: Request timeout in seconds (default: 10.0)
    """

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ):
        # Load from env vars (no defaults - must be configured)
        self.url = url or os.getenv("WEBHOOK_URL")
        self.username = username or os.getenv("WEBHOOK_USERNAME")
        self.password = password or os.getenv("WEBHOOK_PASSWORD")
        timeout_env = os.getenv("WEBHOOK_TIMEOUT")
        self.timeout = timeout or (float(timeout_env) if timeout_env else 10.0)

        logger.info(
            f"WebhookClient initialized with URL: {self.url}, timeout: {self.timeout}s"
        )

    async def send_result(
        self, request_id: int, success: bool, errors: List[int] | None = None
    ) -> int:
        """Send the processing result to the webhook endpoint.

        Args:
            request_id: The ID of the request being processed.
            success: Whether the processing was successful.
            errors: List of integer error codes (if any).

        Returns:
            int: HTTP status code (200, 404, etc.) or 0 if connection failed.
        """
        payload = WebhookPayload(
            request_id=request_id,
            status="success" if success else "fail",
            err_codes=errors or [],
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(
                    f"Sending webhook to {self.url}: {payload.model_dump_json()}"
                )
                response = await client.post(
                    self.url,
                    json=payload.model_dump(),
                    headers={
                        "Content-Type": "application/json",
                        "Accept": "application/json",
                    },
                    auth=(self.username, self.password),
                )
                response.raise_for_status()
                logger.info(
                    f"Webhook delivered successfully. Status: {response.status_code}"
                )
                return response.status_code
        except httpx.HTTPStatusError as e:
            logger.error(
                f"Webhook HTTP error: {e.response.status_code} - {e.response.text}"
            )
            return e.response.status_code
        except Exception as e:
            logger.error(f"Webhook connection failed: {str(e)}")
            return 0


def create_webhook_client_from_env() -> WebhookClient:
    """Factory function to create WebhookClient from environment variables.

    This allows the client to be created on-demand rather than at import time,
    making it easier to test and configure.

    Returns:
        WebhookClient: Configured webhook client instance
    """
    return WebhookClient(
        url=os.getenv("WEBHOOK_URL"),
        username=os.getenv("WEBHOOK_USERNAME"),
        password=os.getenv("WEBHOOK_PASSWORD"),
        timeout=float(os.getenv("WEBHOOK_TIMEOUT", "10.0")),
    )
