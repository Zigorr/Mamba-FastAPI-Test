import os
from typing import Any, Optional, Dict, List, Union
from functools import wraps
import redis
import datetime
from tenacity import retry, stop_after_attempt, wait_exponential
import logging
from enhanced_serialization import serialize, deserialize, SerializationFormat

# Configure logging
logger = logging.getLogger(__name__)

# Try to get Redis URL from environment, default to localhost if not found
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Choose serialization format
SERIALIZATION_FORMAT = os.getenv("CACHE_FORMAT", "orjson")
if SERIALIZATION_FORMAT not in ["json", "orjson", "ujson", "msgpack"]:
    SERIALIZATION_FORMAT = "orjson"

SERIALIZATION_FORMAT = SerializationFormat(SERIALIZATION_FORMAT)

# Create Redis connection pool
try:
    redis_pool = redis.ConnectionPool.from_url(
        REDIS_URL,
        socket_timeout=5.0,
        socket_connect_timeout=5.0,
        health_check_interval=30
    )
    logger.info(f"Redis connection pool created for {REDIS_URL}")
except Exception as e:
    logger.warning(f"Failed to create Redis connection pool: {e}")
    redis_pool = None

def get_redis_connection() -> Optional[redis.Redis]:
    """Get a Redis connection from the pool."""
    if redis_pool is None:
        return None
    try:
        return redis.Redis(connection_pool=redis_pool)
    except Exception as e:
        logger.error(f"Failed to get Redis connection: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def cache_get(key: str) -> Optional[Any]:
    """Get a value from cache with retry logic."""
    try:
        r = get_redis_connection()
        if r is None:
            return None
            
        value = r.get(key)
        if value:
            return deserialize(value, SERIALIZATION_FORMAT)
        return None
    except Exception as e:
        logger.error(f"Cache get error for key {key}: {e}")
        return None

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def cache_set(key: str, value: Any, ttl_seconds: int = 300) -> bool:
    """Set a value in cache with retry logic."""
    try:
        r = get_redis_connection()
        if r is None:
            return False
            
        serialized = serialize(value, SERIALIZATION_FORMAT)
        return r.setex(key, ttl_seconds, serialized)
    except Exception as e:
        logger.error(f"Cache set error for key {key}: {e}")
        return False

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=4, max=10))
def cache_delete(key: str) -> bool:
    """Delete a value from cache with retry logic."""
    try:
        r = get_redis_connection()
        if r is None:
            return False
            
        return r.delete(key) > 0
    except Exception as e:
        logger.error(f"Cache delete error for key {key}: {e}")
        return False

def invalidate_user_cache(username: str) -> None:
    """Invalidate all cache entries for a user."""
    try:
        r = get_redis_connection()
        if r is None:
            return
            
        user_keys = r.keys(f"user:{username}:*")
        if user_keys:
            r.delete(*user_keys)
            logger.info(f"Invalidated {len(user_keys)} cache entries for user {username}")
    except Exception as e:
        logger.error(f"Cache invalidation error for user {username}: {e}")

def invalidate_conversation_cache(conversation_id: str) -> None:
    """Invalidate all cache entries for a conversation."""
    try:
        r = get_redis_connection()
        if r is None:
            return
            
        conversation_keys = r.keys(f"conversation:{conversation_id}:*")
        if conversation_keys:
            r.delete(*conversation_keys)
            logger.info(f"Invalidated {len(conversation_keys)} cache entries for conversation {conversation_id}")
    except Exception as e:
        logger.error(f"Cache invalidation error for conversation {conversation_id}: {e}")

def cached(ttl_seconds: int = 300, key_prefix: str = ""):
    """Decorator to cache function results."""
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, **kwargs):
            # Create a cache key from function name and arguments
            # For most repository or service functions, the first arg after self/cls
            # is typically the primary key (username, conversation_id, etc.)
            cache_key = f"{key_prefix}:{func.__name__}"
            
            if len(args) > 1:  # Skip self/cls
                cache_key += f":{args[1]}"
                
            # Add important kwargs to the cache key
            important_kwargs = ['username', 'conversation_id', 'id', 'limit', 'offset']
            for k in important_kwargs:
                if k in kwargs:
                    cache_key += f":{k}={kwargs[k]}"
            
            # Try to get from cache first
            cached_value = cache_get(cache_key)
            if cached_value is not None:
                logger.debug(f"Cache hit for {cache_key}")
                return cached_value
                
            # Execute the function if cache miss
            logger.debug(f"Cache miss for {cache_key}")
            result = await func(*args, **kwargs)
            
            # Cache the result
            cache_set(cache_key, result, ttl_seconds)
            
            return result
        return wrapper
    return decorator 