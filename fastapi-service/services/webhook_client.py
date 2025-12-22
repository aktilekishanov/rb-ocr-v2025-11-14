import logging
import httpx
from pydantic import BaseModel, Field
from typing import List

logger = logging.getLogger(__name__)

WEBHOOK_URL = "https://dev-loan-api.fortebank.com/api/v1/delay/delay/document-scan/result"


class WebhookPayload(BaseModel):
    err_codes: List[int] = Field(default_factory=list, description="List of integer error codes")
    request_id: int = Field(..., description="Original request ID")
    status: str = Field(..., description="'success' or 'fail'")


class WebhookClient:
    def __init__(self, url: str = WEBHOOK_URL, timeout: float = 10.0):
        self.url = url
        self.timeout = timeout

    async def send_result(self, request_id: int, success: bool, errors: List[int] | None = None) -> int:
        """
        Send the processing result to the webhook endpoint.

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
            err_codes=errors or []
        )

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                logger.info(f"Sending webhook to {self.url}: {payload.model_dump_json()}")
                response = await client.post(
                    self.url,
                    json=payload.model_dump(),
                    headers={"Content-Type": "application/json", "Accept": "application/json"},
                    auth=("bank", "bank")
                )
                response.raise_for_status()
                logger.info(f"Webhook delivered successfully. Status: {response.status_code}")
                return response.status_code
        except httpx.HTTPStatusError as e:
            logger.error(f"Webhook HTTP error: {e.response.status_code} - {e.response.text}")
            return e.response.status_code
        except Exception as e:
            logger.error(f"Webhook connection failed: {str(e)}")
            return 0

# Global instance
webhook_client = WebhookClient()
