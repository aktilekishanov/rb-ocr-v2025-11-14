import logging
from fastapi import BackgroundTasks
from pipeline.utils.db_client import insert_verification_run
from pipeline.utils.io_utils import read_json as util_read_json

logger = logging.getLogger(__name__)


def enqueue_verification_run(background_tasks: BackgroundTasks, result: dict) -> None:
    """
    Queue the database insertion of a verification run.
    Parses the result to find the final JSON path and schedules the insert task.
    """
    try:
        final_json_path = result.get("final_result_path")
        if final_json_path:
            # We read the JSON here to ensure we persist the actual result data,
            # not just the path. This might seem like I/O, but it's preparing the task payload.
            final_json = util_read_json(final_json_path)
            background_tasks.add_task(insert_verification_run, final_json)
    except Exception as e:
        logger.error(f"Failed to queue DB insert task: {e}", exc_info=True)
