import asyncio
import logging
import os
import sys

# Add current directory to path so we can import internal modules
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

try:
    from pipeline.core.db_config import get_db_pool
except ImportError:
    # Fallback if running from root
    sys.path.append(os.getcwd())
    from pipeline.core.db_config import get_db_pool

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def migrate():
    logger.info("Starting schema migration...")
    pool = await get_db_pool()

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
    await pool.close()


if __name__ == "__main__":
    try:
        asyncio.run(migrate())
    except Exception as e:
        logger.error(f"Migration failed: {e}")
        sys.exit(1)
