from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv
import redis.asyncio as redis
import logging
from redis.asyncio.connection import ConnectionPool
from typing import Optional

load_dotenv()

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

# --- Redis Configuration ---
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
redis_pool = None

async def create_redis_pool():
    """Creates a global Redis connection pool on startup."""
    global redis_pool
    try:
        # decode_responses=True means Redis commands return strings, not bytes
        redis_pool = ConnectionPool.from_url(REDIS_URL, decode_responses=True, max_connections=20)
        # Test connection
        r = redis.Redis(connection_pool=redis_pool)
        await r.ping()
        logging.info(f"Successfully connected to Redis at {REDIS_URL} and created pool.")
        await r.close() # Close the test connection
    except Exception as e:
        logging.error(f"Failed to connect to Redis or create pool: {e}")
        redis_pool = None # Ensure pool is None if connection fails

async def get_redis_connection() -> Optional[redis.Redis]:
    """Provides a Redis connection from the global pool."""
    if redis_pool is None:
        logging.warning("Redis pool is not available.")
        return None
    return redis.Redis(connection_pool=redis_pool)

async def close_redis_pool():
    """Closes the Redis connection pool on shutdown."""
    global redis_pool
    if redis_pool:
        await redis_pool.disconnect()
        logging.info("Redis connection pool closed.") 