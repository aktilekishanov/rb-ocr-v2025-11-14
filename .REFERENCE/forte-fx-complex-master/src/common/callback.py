import logging
import requests

from src.core.config import app_settings

logger = logging.getLogger(__name__)


def send_callback(file_id: str, payload: dict):
    url = app_settings.CALLBACK_URL
    try:
        headers = {
            "PRIVATE_API_KEY": app_settings.CALLBACK_PRIVATE_KEY
        }
        payload_temp = {
            "DOCUMENT_ID": file_id,
            "RESULT_LINK": f"{app_settings.FRONTEND_URL}/{file_id}"
        }
        payload = payload_temp | payload
        logger.info(payload)
        resp = requests.post(url, headers=headers, json=payload, timeout=10)  # the cert is issued by USERTrust RSA Certification Authority
        resp.raise_for_status()
        logger.info(f"Successfully sent callback to {url} for Document ID = {file_id}")
        return True
    except Exception as e:
        logger.error(f"Callback error for Document ID = {file_id}: {e}")
        return False
