import logging
import requests

from src.core.config import app_settings

logger = logging.getLogger(__name__)


def get_compliance_data(file_id: str, data: dict):
    url = app_settings.COMPLIANCE_CONTROL_URL
    try:
        payload = {
            "data": data
        }
        logger.info(payload)
        resp = requests.post(url, json=payload, timeout=90, verify=False)
        resp.raise_for_status()
        logger.info(f"Successfully sent Compliance Control to {url} for Document ID = {file_id}")
        return resp.json()
    except Exception as e:
        logger.error(f"Compliance Control error for Document ID = {file_id}: {e}")
        return False
