import logging
from fastapi import BackgroundTasks
from pipeline.utils.db_client import insert_verification_run
from pipeline.utils.io_utils import read_json as util_read_json

from services.webhook_client import webhook_client

logger = logging.getLogger(__name__)


async def send_webhook_and_persist(
    request_id: int, success: bool, errors: list[int], run_id: str
) -> None:
    """
    Send webhook and persist the result (success/fail + http code) to the database.
    This wrapper ensures the DB is updated with the outcome of the webhook attempt.
    """
    from pipeline.utils.db_client import update_webhook_status

    try:
        # 1. Send Webhook
        http_code = await webhook_client.send_result(request_id, success, errors)

        # 2. Determine status based on HTTP code (2xx = SUCCESS)
        status = "SUCCESS" if 200 <= http_code < 300 else "FAILED"

        # 3. Persist to DB
        await update_webhook_status(run_id, status, http_code)

    except Exception as e:
        logger.error(f"Error in webhook wrapper task: {e}", exc_info=True)
        # Try to mark as ERROR in DB if possible
        try:
            from pipeline.utils.db_client import update_webhook_status

            await update_webhook_status(run_id, "ERROR", 0)
        except Exception:
            pass


def enqueue_verification_run(
    background_tasks: BackgroundTasks, result: dict, request_id: int | None = None
) -> None:
    """
    Queue the database insertion of a verification run and optional webhook.
    Parses the result to find the final JSON path and schedules the insert task.
    """
    try:
        final_json_path = result.get("final_result_path")
        if final_json_path:
            # We read the JSON here to ensure we persist the actual result data,
            # not just the path. This might seem like I/O, but it's preparing the task payload.
            final_json = util_read_json(final_json_path)
            background_tasks.add_task(insert_verification_run, final_json)

        # Trigger webhook if request_id is present
        if request_id is not None:
            # Extract integer codes from error objects
            # Orchestrator returns errors as list of dicts: [{"code": 4, ...}, ...]
            raw_errors = result.get("errors", [])
            error_codes = [e["code"] for e in raw_errors]
            success = result.get("verdict", False)
            run_id = result.get("run_id")

            # Use the wrapper that handles persistence
            background_tasks.add_task(
                send_webhook_and_persist,
                request_id=request_id,
                success=success,
                errors=error_codes,
                run_id=run_id,
            )

    except Exception as e:
        logger.error(f"Failed to queue background tasks: {e}", exc_info=True)
