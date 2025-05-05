from sqlalchemy import text
from database import engine
import logging

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_all_pins():
    """
    Reset all is_pinned values to False for all conversations in the database.
    This script can be run anytime you want to unpin all conversations.
    """
    try:
        with engine.connect() as connection:
            # Check if column exists first
            result = connection.execute(text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name='conversations' AND column_name='is_pinned'"
            ))
            
            if result.rowcount == 0:
                logger.error("is_pinned column does not exist in conversations table")
                return
            
            # Update all conversations to set is_pinned to False
            result = connection.execute(text(
                "UPDATE conversations SET is_pinned = FALSE"
            ))
            connection.commit()
            
            # Get count of updated rows
            row_count = result.rowcount
            logger.info(f"Reset pinned status for {row_count} conversations")
            print(f"Successfully reset pinned status for {row_count} conversations")
            
    except Exception as e:
        logger.error(f"Error resetting pins: {e}")
        print(f"Error occurred: {e}")

if __name__ == "__main__":
    print("Resetting all pinned conversations to unpinned...")
    reset_all_pins()
    print("Operation completed.") 