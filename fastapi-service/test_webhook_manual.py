
import asyncio
import logging
import sys
import os

# Ensure we can import from the app directory
sys.path.append(os.getcwd())

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_webhook():
    try:
        from services.webhook_client import webhook_client
        logger.info("Starting manual webhook test...")
        
        # Test data
        request_id = 999999
        success = False
        errors = [4, 6] # FIO_MISMATCH, DOC_TYPE_UNKNOWN
        
        logger.info(f"Sending payload: request_id={request_id}, success={success}, errors={errors}")
        
        result = await webhook_client.send_result(request_id, success, errors)
        
        if result:
            logger.info("✅ Webhook sent successfully!")
        else:
            logger.error("❌ Webhook failed to send.")
            
    except ImportError as e:
        logger.error(f"Import failed: {e}")
    except Exception as e:
        logger.error(f"An error occurred: {e}")

if __name__ == "__main__":
    asyncio.run(test_webhook())
