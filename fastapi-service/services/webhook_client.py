import logging
import os
import httpx
from pydantic import BaseModel, Field
from typing import List

logger = logging.getLogger(__name__)

# Default constants (Fix #2: Use env vars with fallback defaults)
DEFAULT_WEBHOOK_URL = (
    "https://dev-loan-api.fortebank.com/api/v1/delay/delay/document-scan/result"
)
DEFAULT_WEBHOOK_USERNAME = "bank"
DEFAULT_WEBHOOK_PASSWORD = "bank"
DEFAULT_WEBHOOK_TIMEOUT = 10.0


class WebhookPayload(BaseModel):
    err_codes: List[int] = Field(
        default_factory=list, description="List of integer error codes"
    )
    request_id: int = Field(..., description="Original request ID")
    status: str = Field(..., description="'success' or 'fail'")


class WebhookClient:
    """Webhook client with environment-based configuration.

    Fix #2: Hardcoded credentials moved to environment variables with
    sensible defaults for development.

    Environment variables:
        WEBHOOK_URL: Target webhook endpoint URL
        WEBHOOK_USERNAME: Basic auth username
        WEBHOOK_PASSWORD: Basic auth password
        WEBHOOK_TIMEOUT: Request timeout in seconds
    """

    def __init__(
        self,
        url: str | None = None,
        username: str | None = None,
        password: str | None = None,
        timeout: float | None = None,
    ):
        # Load from env vars with fallback to defaults
        self.url = url or os.getenv("WEBHOOK_URL", DEFAULT_WEBHOOK_URL)
        self.username = username or os.getenv(
            "WEBHOOK_USERNAME", DEFAULT_WEBHOOK_USERNAME
        )
        self.password = password or os.getenv(
            "WEBHOOK_PASSWORD", DEFAULT_WEBHOOK_PASSWORD
        )
        self.timeout = timeout or float(
            os.getenv("WEBHOOK_TIMEOUT", str(DEFAULT_WEBHOOK_TIMEOUT))
        )

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


# Global instance
webhook_client = WebhookClient()
