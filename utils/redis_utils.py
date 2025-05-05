import logging
import json
from typing import Optional
from database import get_redis_connection # Import the connection getter
from dto import MessageDto # Import your Message DTO

logger = logging.getLogger(__name__)

def get_conversation_channel(conversation_id: str) -> str:
    """Generates the Redis channel name for a conversation."""
    return f"conversation:{conversation_id}"

async def publish_message_to_redis(conversation_id: str, message: MessageDto):
    """Publishes a message DTO to the conversation's Redis channel."""
    redis = await get_redis_connection()
    if not redis:
        logger.error(f"Cannot publish message to Redis: No connection available.")
        return

    try:
        channel = get_conversation_channel(conversation_id)
        # Convert the DTO to JSON string for publishing
        message_json = message.model_dump_json()
        await redis.publish(channel, message_json)
        logger.info(f"Published message {message.id} to Redis channel {channel}")
    except Exception as e:
        logger.error(f"Failed to publish message {message.id} to Redis for conv {conversation_id}: {e}")
    finally:
        # Connections from pool don't need explicit closing usually,
        # but ensure it if not using pool correctly elsewhere.
        pass # await redis.close() # Typically not needed with pool 