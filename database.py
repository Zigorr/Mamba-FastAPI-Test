from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

load_dotenv()

# FORCE LOCAL DEVELOPMENT MODE - Always use SQLite
# This fixes connection issues with remote PostgreSQL instances
LOCAL_DEV_MODE = True  # Set to False to use PostgreSQL in production

if LOCAL_DEV_MODE:
    print("Running in LOCAL_DEV_MODE - Using SQLite database")
    DATABASE_URL = "sqlite:///./mamba_local.db"
    engine = create_engine(
        DATABASE_URL, 
        connect_args={"check_same_thread": False},  # Needed for SQLite
        echo=True  # Set to True to see SQL queries in logs
    )
else:
    # Get database configuration from environment variables
    POSTGRES_USER = os.getenv("POSTGRES_USER", "postgres")
    POSTGRES_PASSWORD = os.getenv("POSTGRES_PASSWORD", "postgres")
    POSTGRES_HOST = os.getenv("POSTGRES_HOST", "localhost")
    POSTGRES_PORT = os.getenv("POSTGRES_PORT", "5432")
    POSTGRES_DB = os.getenv("POSTGRES_DB", "mamba_db")

    # Get the DATABASE_URL from environment or construct one
    DATABASE_URL = os.getenv("DATABASE_URL")

    if not DATABASE_URL:
        print("No DATABASE_URL found. Constructing one from environment variables.")
        DATABASE_URL = f"postgresql://{POSTGRES_USER}:{POSTGRES_PASSWORD}@{POSTGRES_HOST}:{POSTGRES_PORT}/{POSTGRES_DB}"
    
    print(f"Using PostgreSQL database: {DATABASE_URL}")
    
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