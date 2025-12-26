import logging

import httpx
from core.settings import webhook_settings
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class WebhookPayload(BaseModel):
    err_codes: list[int] = Field(
        default_factory=list, description="List of integer error codes"
    )
    request_id: int = Field(..., description="Original request ID")
    status: str = Field(..., description="'success' or 'fail'")


class WebhookClient:
    """Webhook client with centralized Pydantic settings."""

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ):
        self.url = url or webhook_settings.WEBHOOK_URL
        self.username = username or webhook_settings.WEBHOOK_USERNAME
        self.password = password or webhook_settings.WEBHOOK_PASSWORD.get_secret_value()
        self.timeout = timeout or 10.0

        logger.info(
            f"WebhookClient initialized with URL: {self.url}, timeout: {self.timeout}s"
        )

    async def send_result(
        self, request_id: int, success: bool, errors: list[int] | None = None
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
    """Factory function to create WebhookClient from centralized settings.

    Returns:
        WebhookClient: Configured webhook client instance
    """
    return WebhookClient(
        url=webhook_settings.WEBHOOK_URL,
        username=webhook_settings.WEBHOOK_USERNAME,
        password=webhook_settings.WEBHOOK_PASSWORD.get_secret_value(),
    )
