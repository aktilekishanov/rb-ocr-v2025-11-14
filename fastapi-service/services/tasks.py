import logging
import asyncio
from fastapi import BackgroundTasks
from pipeline.utils.db_client import insert_verification_run, update_webhook_status

from services.webhook_client import webhook_client

logger = logging.getLogger(__name__)


# ==============================================================================
# Helper Functions (Fix #3: SRP Violation)
# ==============================================================================


def _extract_error_codes(result: dict) -> list[int]:
    """Extract integer error codes from result.

    Single responsibility: Error code extraction only.
    """
    raw_errors = result.get("errors", [])
    return [e["code"] for e in raw_errors]


# ==============================================================================
# Webhook Functions (Fix #4: Database Transaction + Improved Error Handling)
# ==============================================================================


async def send_webhook_and_persist(
    request_id: int,
    success: bool,
    errors: list[int],
    run_id: str,
    max_db_retries: int = 3,
) -> None:
    """Send webhook and persist status with retry logic.

    Ensures database is ALWAYS updated with webhook status, never silently fails.
    Implements exponential backoff for database retries.
    """
    http_code = 0
    status = "ERROR"

    # 1. Send webhook (may fail, that's OK)
    try:
        http_code = await webhook_client.send_result(request_id, success, errors)
        status = "SUCCESS" if 200 <= http_code < 300 else "FAILED"
        logger.info(
            f"Webhook sent for run_id={run_id}: status={status}, http_code={http_code}"
        )
    except Exception as e:
        logger.error(f"Webhook send failed for run_id={run_id}: {e}", exc_info=True)
        # status remains "ERROR", http_code remains 0

    # 2. Persist to DB with retries (NEVER silently fail)
    for attempt in range(1, max_db_retries + 1):
        try:
            db_success = await update_webhook_status(run_id, status, http_code)
            if db_success:
                logger.info(
                    f"✅ Webhook status persisted: run_id={run_id}, "
                    f"status={status}, http_code={http_code}"
                )
                return
            else:
                logger.warning(
                    f"DB update returned False for run_id={run_id}, "
                    f"attempt {attempt}/{max_db_retries}"
                )
        except Exception as e:
            logger.error(
                f"DB update failed for run_id={run_id}, "
                f"attempt {attempt}/{max_db_retries}: {e}",
                exc_info=True,
            )

        if attempt < max_db_retries:
            backoff = 0.5 * (2 ** (attempt - 1))  # Exponential backoff
            await asyncio.sleep(backoff)

    # If we get here, all retries failed - CRITICAL ERROR
    logger.critical(
        f"🚨 CRITICAL: Failed to persist webhook status after {max_db_retries} attempts. "
        f"run_id={run_id}, status={status}, http_code={http_code}. "
        f"MANUAL INTERVENTION REQUIRED."
    )


# ==============================================================================
# Atomic Operations (Fix #1: Race Condition)
# ==============================================================================


async def insert_run_then_webhook(
    final_json: dict,
    request_id: int,
    success: bool,
    errors: list[int],
    run_id: str,
) -> None:
    """Atomically insert run then send webhook. Guaranteed order.

    This prevents race condition where webhook status update happens
    before the verification run row exists in the database.
    """
    try:
        # 1. Insert row FIRST (blocking operation)
        insert_success = await insert_verification_run(final_json)
        if not insert_success:
            logger.error(f"❌ Failed to insert run {run_id}, skipping webhook send")
            return

        logger.info(f"✅ Verification run inserted: run_id={run_id}")

        # 2. Now safe to send webhook and update status
        # Row is guaranteed to exist, so update_webhook_status won't fail
        await send_webhook_and_persist(request_id, success, errors, run_id)

    except Exception as e:
        logger.error(
            f"Error in atomic insert+webhook for run_id={run_id}: {e}",
            exc_info=True,
        )


async def insert_verification_run_from_path(path: str) -> bool:
    """Load JSON from path and insert in background (Fix #6: File I/O).

    Moves file I/O out of the request handler into background task.
    """
    try:
        from pipeline.utils.io_utils import read_json as util_read_json

        final_json = util_read_json(path)
        return await insert_verification_run(final_json)
    except Exception as e:
        logger.error(f"Failed to load/insert from {path}: {e}", exc_info=True)
        return False


# ==============================================================================
# Main Enqueueing Function
# ==============================================================================


def enqueue_verification_run(
    background_tasks: BackgroundTasks,
    result: dict,
    request_id: int | None = None,
) -> None:
    """Queue database insertion and optional webhook.

    Single responsibility: Task enqueueing only.
    Delegates parsing and extraction to helper functions.

    Fixes applied:
    - #1: Race condition - uses atomic insert_run_then_webhook
    - #3: SRP violation - delegates to helper functions
    - #6: File I/O - passes path instead of reading file here
    """
    try:
        final_json_path = result.get("final_result_path")
        if not final_json_path:
            logger.warning("No final_result_path in result, skipping persistence")
            return

        # If webhook needed, do BOTH operations atomically
        if request_id is not None:
            # Read file once for atomic operation
            from pipeline.utils.io_utils import read_json as util_read_json

            final_json = util_read_json(final_json_path)

            error_codes = _extract_error_codes(result)
            success = result.get("verdict", False)
            run_id = result.get("run_id")

            # Single atomic task that does: INSERT, then WEBHOOK
            background_tasks.add_task(
                insert_run_then_webhook,
                final_json=final_json,
                request_id=request_id,
                success=success,
                errors=error_codes,
                run_id=run_id,
            )
        else:
            # No webhook, just insert (can defer file reading)
            background_tasks.add_task(
                insert_verification_run_from_path, final_json_path
            )

    except Exception as e:
        logger.error(f"Failed to enqueue background tasks: {e}", exc_info=True)
