from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
# import os # os might still be needed for other things, or can be removed if not
# from dotenv import load_dotenv # No longer needed here, config handles it
import redis.asyncio as redis # Valkey uses Redis protocol, so redis-py/aioredis works
from redis.asyncio.connection import ConnectionPool
from typing import Optional
import logging # Import logging
from core.config import settings # Import the centralized settings

# load_dotenv() # Handled by core.config

# Create a logger for this module
logger = logging.getLogger(__name__)

# Get database credentials from environment variables NO LONGER NEEDED DIRECTLY
# POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
# POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
# POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
# POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
# POSTGRES_DB = os.getenv("POSTGRES_DB", "mamba_db")

# Construct PostgreSQL URL NO LONGER NEEDED DIRECTLY
# DATABASE_URL = os.getenv("DATABASE_URL")
logger.info(f"DATABASE_URL from settings: {settings.DATABASE_URL}") # Use settings

# Create SQLAlchemy engine with PostgreSQL-specific settings
engine = create_engine(
    settings.DATABASE_URL, # Use settings
    pool_size=20,  # Number of connections to keep open
    max_overflow=10,  # Number of connections to allow beyond pool_size
    pool_timeout=30,  # Seconds to wait before giving up on getting a connection
    pool_recycle=1800,  # Recycle connections after 30 minutes
    echo=False  # Set to True to see SQL queries in logs, False for production
)

# Create SessionLocal class
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Create Base class
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()

# --- Valkey (Redis Compatible) Configuration ---
# NOTE: Using Valkey (DigitalOcean Managed Redis Fork)
# VALKEY_URL = os.getenv("VALKEY_URL") # Use settings.VALKEY_URL
valkey_pool = None

async def create_valkey_pool():
    """Creates a global Valkey connection pool on startup."""
    global valkey_pool
    if not settings.VALKEY_URL: # Use settings
        logger.error("VALKEY_URL environment variable not set in settings. Valkey connection pool cannot be created.")
        return
        
    try:
        logger.info(f"Attempting to create Valkey/Redis pool with URL: {settings.VALKEY_URL}") # Log before creation
        valkey_pool = ConnectionPool.from_url(settings.VALKEY_URL, decode_responses=True, max_connections=20) # Use settings
        # Test connection
        r = redis.Redis(connection_pool=valkey_pool)
        await r.ping()
        logger.info(f"Successfully connected to Valkey at parsed host and created pool.") # Adjusted log
        await r.close()
    except Exception as e:
        logger.error(f"Failed to connect to Valkey or create pool. URL: {settings.VALKEY_URL}. Error: {e}", exc_info=True) # Use settings and log error details
        valkey_pool = None

async def get_valkey_connection() -> Optional[redis.Redis]:
    """Provides a Valkey connection from the global pool."""
    # Rename function for clarity
    if valkey_pool is None:
        logger.warning("Valkey pool is not available.")
        return None
    return redis.Redis(connection_pool=valkey_pool)

async def close_valkey_pool():
    """Closes the Valkey connection pool on shutdown."""
    global valkey_pool
    if valkey_pool:
        await valkey_pool.disconnect()
        logger.info("Valkey connection pool closed.")

# --- Remove old Redis functions if they still exist ---
# async def create_redis_pool(): ...
# async def get_redis_connection(): ...
# async def close_redis_pool(): ... 