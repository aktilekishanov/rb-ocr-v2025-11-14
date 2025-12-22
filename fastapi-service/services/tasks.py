import logging
from fastapi import BackgroundTasks
from pipeline.utils.db_client import insert_verification_run
from pipeline.utils.io_utils import read_json as util_read_json

from services.webhook_client import webhook_client

logger = logging.getLogger(__name__)


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
            
            background_tasks.add_task(
                webhook_client.send_result,
                request_id=request_id,
                success=success,
                errors=error_codes
            )

    except Exception as e:
        logger.error(f"Failed to queue background tasks: {e}", exc_info=True)
