"""Database client for storing verification run results.

Handles automatic insertion of final.json data into PostgreSQL with:
- Retry decorator with exponential backoff
- Verbose logging
- Non-blocking (won't fail pipeline on DB errors)
"""

import json
import logging
from typing import Any

from pipeline.database.manager import DatabaseManager
from pipeline.utils.dates import parse_iso_timestamp
from pipeline.utils.retry import retry_on_db_error

logger = logging.getLogger(__name__)


@retry_on_db_error(max_retries=3)
async def insert_verification_run(
    final_json: dict[str, Any], db_manager: DatabaseManager
) -> bool:
    """Insert verification run record into database.

    Args:
        final_json: Complete final.json dict
        db_manager: Database manager instance

    Returns:
        True if insert succeeded

    Raises:
        Exception: If all retries exhausted
    """
    pool = await db_manager.get_pool()

    # Extract fields from final_json using centralized timestamp parser
    run_id = final_json.get("run_id")
    trace_id = final_json.get("trace_id")
    created_at = parse_iso_timestamp(final_json.get("created_at"))
    completed_at = parse_iso_timestamp(final_json.get("completed_at"))
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

    # Pipeline error fields
    pipeline_error_code = final_json.get("pipeline_error_code")
    pipeline_error_message = final_json.get("pipeline_error_message")
    pipeline_error_category = final_json.get("pipeline_error_category")
    pipeline_error_retryable = final_json.get("pipeline_error_retryable")

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
    rule_errors = json.dumps(
        final_json.get("rule_errors", [])
    )  # Convert list to JSON string

    query = """
        INSERT INTO verification_runs (
            run_id, trace_id, created_at, completed_at, processing_time_seconds,
            external_request_id, external_s3_path, external_iin,
            external_first_name, external_last_name, external_second_name,
            status,
            pipeline_error_code, pipeline_error_message, pipeline_error_category, pipeline_error_retryable,
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
            run_id,
            trace_id,
            created_at,
            completed_at,
            processing_time,
            ext_request_id,
            ext_s3_path,
            ext_iin,
            ext_first_name,
            ext_last_name,
            ext_second_name,
            status,
            pipeline_error_code,
            pipeline_error_message,
            pipeline_error_category,
            pipeline_error_retryable,
            extracted_fio,
            extracted_doc_date,
            extracted_single_doc_type,
            extracted_doc_type_known,
            extracted_doc_type,
            rule_fio_match,
            rule_doc_date_valid,
            rule_doc_type_known,
            rule_single_doc_type,
            rule_verdict,
            rule_errors,
        )

    logger.info(
        f"✅ DB INSERT SUCCESS | "
        f"run_id={run_id} | "
        f"status={status} | "
        f"verdict={rule_verdict}"
    )
    return True


@retry_on_db_error(max_retries=3)
async def update_webhook_status(
    run_id: str,
    status: str,
    http_code: int | None = None,
    db_manager: DatabaseManager | None = None,
) -> bool:
    """Update webhook delivery status for verification run.

    Args:
        run_id: Run ID to update
        status: Webhook status ('PENDING', 'SUCCESS', 'FAILED', 'ERROR')
        http_code: HTTP status code from webhook response
        db_manager: Database manager instance

    Returns:
        True if updated, False if row not found

    Raises:
        Exception: If all retries exhausted
    """
    if db_manager is None:
        logger.warning(f"No database manager provided for {run_id}, skipping update")
        return False

    pool = await db_manager.get_pool()

    query = """
        UPDATE verification_runs
        SET webhook_status = $1,
            webhook_attempted_at = NOW(),
            webhook_http_code = $2
        WHERE run_id = $3
        RETURNING run_id
    """

    try:
        async with pool.acquire() as conn:
            result = await conn.fetchval(query, status, http_code, run_id)

            if result is None:
                logger.warning(
                    f"No row found for run_id={run_id}, webhook status update skipped"
                )
                return False

            logger.debug(f"Updated webhook status for run_id={run_id}: {status}")
            return True

    except Exception as e:
        logger.error(
            f"Failed to update webhook status for {run_id}: {e}", exc_info=True
        )
        return False
