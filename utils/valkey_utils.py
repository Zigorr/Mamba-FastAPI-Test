import logging
import json
from typing import Optional
from database import get_valkey_connection # Use the renamed connection getter
from dto import MessageDto

logger = logging.getLogger(__name__)

# Note: Valkey uses Redis Pub/Sub protocol

def get_conversation_channel(conversation_id: str) -> str:
    """Generates the Valkey/Redis channel name for a conversation."""
    return f"conversation:{conversation_id}"

async def publish_message_to_valkey(conversation_id: str, message: MessageDto):
    """Publishes a message DTO to the conversation's Valkey channel."""
    # Rename function for clarity
    valkey_conn = await get_valkey_connection()
    if not valkey_conn:
        logger.error(f"Cannot publish message to Valkey: No connection available.")
        return

    try:
        channel = get_conversation_channel(conversation_id)
        message_json = message.model_dump_json()
        await valkey_conn.publish(channel, message_json)
        logger.info(f"Published message {message.id} to Valkey channel {channel}")
    except Exception as e:
        logger.error(f"Failed to publish message {message.id} to Valkey for conv {conversation_id}: {e}")
    finally:
        # Connections from pool don't need explicit closing
        pass 