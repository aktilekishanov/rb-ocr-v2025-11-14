"""Database client for storing verification run results.

Handles automatic insertion of final.json data into PostgreSQL with:
- 5 retries with exponential backoff
- Verbose logging
- Non-blocking (won't fail pipeline on DB errors)
"""

import asyncio
import logging
import json
from typing import Any
from datetime import datetime

from pipeline.core.db_config import get_db_pool

logger = logging.getLogger(__name__)

# Retry configuration
MAX_RETRIES = 5
INITIAL_BACKOFF = 0.5  # seconds


async def insert_verification_run(final_json: dict[str, Any]) -> bool:
    """Insert a verification run record into PostgreSQL.
    
    Retries up to 5 times with exponential backoff on failure.
    Logs all attempts (success and failure) verbosely.
    
    Args:
        final_json: The complete final.json dict to insert.
        
    Returns:
        bool: True if insert succeeded, False if all retries failed.
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            success = await _insert_once(final_json)
            if success:
                logger.info(
                    f"✅ DB INSERT SUCCESS on attempt {attempt}/{MAX_RETRIES} | "
                    f"run_id={final_json.get('run_id')} | "
                    f"status={final_json.get('status')} | "
                    f"verdict={final_json.get('rule_verdict')}"
                )
                return True
        except Exception as e:
            backoff = INITIAL_BACKOFF * (2 ** (attempt - 1))
            logger.warning(
                f"❌ DB INSERT FAILED attempt {attempt}/{MAX_RETRIES} | "
                f"run_id={final_json.get('run_id')} | "
                f"error={str(e)} | "
                f"retrying in {backoff}s...",
                exc_info=True
            )
            
            if attempt < MAX_RETRIES:
                await asyncio.sleep(backoff)
            else:
                logger.error(
                    f"🚨 DB INSERT EXHAUSTED all {MAX_RETRIES} retries | "
                    f"run_id={final_json.get('run_id')} | "
                    f"final_error={str(e)}",
                    exc_info=True
                )
                return False
    
    return False


async def _insert_once(final_json: dict[str, Any]) -> bool:
    """Single insert attempt without retry logic.
    
    Args:
        final_json: The final.json dict.
        
    Returns:
        bool: True if insert succeeded.
        
    Raises:
        Exception: On any database error.
    """
    pool = await get_db_pool()
    
    # Helper to parse ISO timestamp strings to datetime objects
    def parse_timestamp(ts_str: str | None) -> datetime | None:
        if not ts_str:
            return None
        try:
            return datetime.fromisoformat(ts_str)
        except (ValueError, AttributeError):
            return None
    
    # Extract fields from final_json
    run_id = final_json.get("run_id")
    trace_id = final_json.get("trace_id")
    created_at = parse_timestamp(final_json.get("created_at"))
    completed_at = parse_timestamp(final_json.get("completed_at"))
    processing_time = final_json.get("processing_time_seconds")
    
    # External metadata
    ext_request_id = final_json.get("external_request_id")
    ext_s3_path = final_json.get("external_s3_path")
    ext_iin = final_json.get("external_iin")
    ext_first_name = final_json.get("external_first_name")
    ext_last_name = final_json.get("external_last_name")
    ext_second_name = final_json.get("external_second_name")
    
    # Status
    status = final_json.get("status")
    
    # HTTP error fields
    http_error_code = final_json.get("http_error_code")
    http_error_message = final_json.get("http_error_message")
    http_error_category = final_json.get("http_error_category")
    http_error_retryable = final_json.get("http_error_retryable")
    
    # Extracted data
    extracted_fio = final_json.get("extracted_fio")
    extracted_doc_date = final_json.get("extracted_doc_date")
    extracted_single_doc_type = final_json.get("extracted_single_doc_type")
    extracted_doc_type_known = final_json.get("extracted_doc_type_known")
    extracted_doc_type = final_json.get("extracted_doc_type")
    
    # Rule checks
    rule_fio_match = final_json.get("rule_fio_match")
    rule_doc_date_valid = final_json.get("rule_doc_date_valid")
    rule_doc_type_known = final_json.get("rule_doc_type_known")
    rule_single_doc_type = final_json.get("rule_single_doc_type")
    rule_verdict = final_json.get("rule_verdict")
    rule_errors = json.dumps(final_json.get("rule_errors", []))  # Convert list to JSON string
    
    # SQL INSERT statement (asyncpg handles Python list → JSONB automatically)
    query = """
        INSERT INTO verification_runs (
            run_id, trace_id, created_at, completed_at, processing_time_seconds,
            external_request_id, external_s3_path, external_iin,
            external_first_name, external_last_name, external_second_name,
            status,
            http_error_code, http_error_message, http_error_category, http_error_retryable,
            extracted_fio, extracted_doc_date, extracted_single_doc_type,
            extracted_doc_type_known, extracted_doc_type,
            rule_fio_match, rule_doc_date_valid, rule_doc_type_known,
            rule_single_doc_type, rule_verdict, rule_errors
        ) VALUES (
            $1, $2, $3, $4, $5,
            $6, $7, $8, $9, $10, $11,
            $12,
            $13, $14, $15, $16,
            $17, $18, $19, $20, $21,
            $22, $23, $24, $25, $26, $27
        )
    """
    
    async with pool.acquire() as conn:
        await conn.execute(
            query,
            run_id, trace_id, created_at, completed_at, processing_time,
            ext_request_id, ext_s3_path, ext_iin,
            ext_first_name, ext_last_name, ext_second_name,
            status,
            http_error_code, http_error_message, http_error_category, http_error_retryable,
            extracted_fio, extracted_doc_date, extracted_single_doc_type,
            extracted_doc_type_known, extracted_doc_type,
            rule_fio_match, rule_doc_date_valid, rule_doc_type_known,
            rule_single_doc_type, rule_verdict, rule_errors
        )
    
    return True
