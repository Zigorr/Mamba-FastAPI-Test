from sqlalchemy import create_engine, event
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, scoped_session
import os
from dotenv import load_dotenv
import time
import logging

# Configure logging for database operations
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("database")

load_dotenv()

# Get database configuration from environment variables
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("DATABASE_URL environment variable is not set. Please check your .env file.")

print(f"Using database: {DATABASE_URL}")

# Create SQLAlchemy engine with optimized PostgreSQL-specific settings
engine = create_engine(
    DATABASE_URL,
    pool_size=50,  # Increased number of connections for high traffic
    max_overflow=20,  # Increased overflow for peak loads
    pool_timeout=30,  # Seconds to wait before giving up on getting a connection
    pool_recycle=1800,  # Recycle connections after 30 minutes
    pool_pre_ping=True,  # Check connection validity before using it
    connect_args={"connect_timeout": 10},  # Set connection timeout
    echo=False,  # Set to False in production to reduce logging overhead
    json_serializer=lambda obj: obj,  # Use faster JSON serialization
    execution_options={
        "timeout": 30,  # Query timeout in seconds
        "statement_timeout": 30000  # Statement timeout in milliseconds
    }
)

# Add event listeners for query timing and connection debugging
@event.listens_for(engine, "before_cursor_execute")
def before_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    conn.info.setdefault('query_start_time', []).append(time.time())
    if os.getenv("SQL_DEBUG") == "1":
        logger.debug("SQL: %s", statement)

@event.listens_for(engine, "after_cursor_execute")
def after_cursor_execute(conn, cursor, statement, parameters, context, executemany):
    total = time.time() - conn.info['query_start_time'].pop(-1)
    if total > 0.5:  # Log slow queries (more than 500ms)
        logger.warning("SLOW QUERY (%.3fs): %s", total, statement)

# Create SessionLocal class with thread-safety
SessionLocal = scoped_session(
    sessionmaker(
        autocommit=False, 
        autoflush=False, 
        bind=engine,
        expire_on_commit=False  # Don't expire objects after commit for better performance
    )
)

# Create Base class
Base = declarative_base()

# Dependency to get DB session
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close() 