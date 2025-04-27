import os
import asyncio
import logging
import datetime
from typing import Dict, Optional, Tuple, Any, List, Set
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_

from database import get_db
from models import User, Conversation, Message, UserSession
from dto import MessageDto, SendMessageDto
import state
from state_manager import load_threads, save_threads, load_settings, save_settings, load_shared_state, save_shared_state, conversation_lock, agency_lock
from repositories import ConversationRepository, UserRepository, MessageRepository

# Agency
from agency_swarm import Agency
from ClientManagementAgency.CEO import CEO
from ClientManagementAgency.Worker import Worker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# A cache of agency instances by conversation_id
agency_instances: Dict[str, Any] = {}

async def get_or_create_agency(conversation_id: str, db: Session):
    """Get or create an agency instance for a conversation."""
    # Import inside function to avoid circular imports
    from agency import Agency
    
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    
    # Use a lock to prevent multiple agency initializations
    with agency_lock(conversation_id):
        if conversation_id not in agency_instances:
            # Get environment variables
            anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
            if not anthropic_api_key:
                raise ValueError("ANTHROPIC_API_KEY environment variable not set")
            
            # Create new agency instance
            logger.info(f"Creating new agency instance for conversation {conversation_id}")
            agency_instances[conversation_id] = Agency(anthropic_api_key)
            
            # Get conversation
            conversation = conversation_repo.get_by_id(conversation_id)
            
            if conversation:
                # Get owner
                owner = conversation.user_username
                logger.info(f"Conversation {conversation_id} is owned by: {owner}")
        
        return agency_instances[conversation_id]

async def process_message_with_agency(
    message_data: SendMessageDto,
    username: str,
    db: Session
) -> Tuple[MessageDto, MessageDto]:
    """Process a user message with the agency and return both user and agency messages."""
    # Initialize repositories
    message_repo = MessageRepository(db)
    conversation_repo = ConversationRepository(db)
    
    # Get conversation
    conversation = conversation_repo.get_by_id(message_data.conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {message_data.conversation_id} not found"
        )
    
    # Check if the user is the owner
    if conversation.user_username != username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this conversation"
        )
    
    # Get or create agency instance
    agency = await get_or_create_agency(message_data.conversation_id, db)
    
    # Create user message
    user_message = message_repo.create_from_dto(message_data, username)
    
    # Prefix the content with the username for the agency
    prefixed_content = f"FROM {username}: {message_data.content}"
    
    # Process the message with the agency
    with agency_lock(message_data.conversation_id):
        response_content = await agency.process_message(prefixed_content)
    
    # Create agency message
    agency_message_dto = SendMessageDto(
        conversation_id=message_data.conversation_id,
        content=response_content
    )
    agency_message = message_repo.create_system_message(
        message_data.conversation_id,
        response_content,
        is_agency_message=True
    )
    
    # Convert to DTOs
    user_message_dto = message_repo.to_dto(user_message)
    agency_message_dto = message_repo.to_dto(agency_message)
    
    return user_message_dto, agency_message_dto

async def cleanup_agency_resources(conversation_id: str):
    """Clean up any resources used by the agency for a specific conversation."""
    with agency_lock(conversation_id):
        if conversation_id in agency_instances:
            # If the agency has a cleanup method, call it
            if hasattr(agency_instances[conversation_id], 'cleanup'):
                await agency_instances[conversation_id].cleanup()
            
            # Remove from cache
            logger.info(f"Removing agency instance for conversation {conversation_id}")
            del agency_instances[conversation_id]

def get_active_agency_conversations() -> List[str]:
    """Get a list of conversation IDs with active agency instances."""
    return list(agency_instances.keys()) 