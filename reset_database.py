from database import engine, Base
import logging
from models import User, Conversation, Message

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def reset_database():
    """
    Drops all tables in the database and recreates them.
    WARNING: This will delete all data in the database!
    """
    try:
        # Drop all tables
        logger.info("Dropping all tables...")
        Base.metadata.drop_all(bind=engine)
        logger.info("Successfully dropped all tables in the database")
        
        # Recreate all tables
        # logger.info("Recreating tables...")
        # Base.metadata.create_all(bind=engine)
        # logger.info("Successfully recreated all tables in the database")
        
    except Exception as e:
        logger.error(f"Error resetting database: {e}")
        raise

if __name__ == "__main__":
    # Ask for confirmation before proceeding
    confirmation = input("WARNING: This will delete ALL data in the database. Are you sure? (yes/no): ")
    
    if confirmation.lower() == 'yes':
        reset_database()
    else:
        logger.info("Operation cancelled by user") 