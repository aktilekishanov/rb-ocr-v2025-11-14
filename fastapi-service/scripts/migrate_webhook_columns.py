import asyncio
import logging
import sys
from pathlib import Path

# Add parent directory to path to import core modules
sys.path.insert(0, str(Path(__file__).parent.parent))
from pipeline.database.manager import create_database_manager_from_env

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    logger.info("Starting schema migration...")
    db_manager = create_database_manager_from_env()
    await db_manager.connect()
    pool = await db_manager.get_pool()

    queries = [
        "ALTER TABLE verification_runs ADD COLUMN IF NOT EXISTS webhook_status VARCHAR(50) DEFAULT 'PENDING';",
        "ALTER TABLE verification_runs ADD COLUMN IF NOT EXISTS webhook_attempted_at TIMESTAMP WITH TIME ZONE;",
        "ALTER TABLE verification_runs ADD COLUMN IF NOT EXISTS webhook_http_code INTEGER;",
    ]

    async with pool.acquire() as conn:
        for query in queries:
            logger.info(f"Executing: {query}")
            await conn.execute(query)

    logger.info("Migration completed successfully.")
    await db_manager.disconnect()


if __name__ == "__main__":
    try:
        asyncio.run(migrate())
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
