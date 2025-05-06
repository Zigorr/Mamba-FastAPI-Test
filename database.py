from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import redis.asyncio as redis # Valkey uses Redis protocol, so redis-py/aioredis works
from redis.asyncio.connection import ConnectionPool
from typing import Optional
import logging # Import logging

load_dotenv()

# Create a logger for this module
logger = logging.getLogger(__name__)

# Get database credentials from environment variables
POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
POSTGRES_DB = os.getenv("POSTGRES_DB", "mamba_db")

# Construct PostgreSQL URL
DATABASE_URL = os.getenv("DATABASE_URL")

# Create SQLAlchemy engine with PostgreSQL-specific settings
engine = create_engine(
    DATABASE_URL,
    pool_size=20,  # Number of connections to keep open
    max_overflow=10,  # Number of connections to allow beyond pool_size
    pool_timeout=30,  # Seconds to wait before giving up on getting a connection
    pool_recycle=1800,  # Recycle connections after 30 minutes
    echo=True  # Set to True to see SQL queries in logs
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
    finally:
        db.close() 

# --- Valkey (Redis Compatible) Configuration ---
# NOTE: Using Valkey (DigitalOcean Managed Redis Fork)
VALKEY_URL = os.getenv("VALKEY_URL") # Changed from REDIS_URL
valkey_pool = None

async def create_valkey_pool():
    """Creates a global Valkey connection pool on startup."""
    global valkey_pool
    if not VALKEY_URL:
        logger.error("VALKEY_URL environment variable not set. Valkey connection pool cannot be created.")
        return
        
    try:
        valkey_pool = ConnectionPool.from_url(VALKEY_URL, decode_responses=True, max_connections=20)
        # Test connection
        r = redis.Redis(connection_pool=valkey_pool)
        await r.ping()
        logger.info(f"Successfully connected to Valkey at {VALKEY_URL} and created pool.")
        await r.close()
    except Exception as e:
        logger.error(f"Failed to connect to Valkey or create pool: {e}")
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