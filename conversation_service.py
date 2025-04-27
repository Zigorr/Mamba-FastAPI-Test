import logging
import datetime
from typing import List, Optional, Set
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import get_db
from models import User, Conversation, Message, UserSession
from dto import ConversationDto, CreateConversationDto, MessageDto, SendMessageDto, ConversationStateDto, UpdateConversationStateDto
import state
from state_manager import conversation_lock
from repositories import ConversationRepository, UserRepository, MessageRepository, UserSessionRepository
from app_cache import cached, invalidate_conversation_cache

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

async def create_conversation(
    conversation_data: CreateConversationDto, 
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationDto:
    """Create a new conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    user_repo = UserRepository(db)
    message_repo = MessageRepository(db)
    
    # Verify user exists
    if not user_repo.get_by_username(current_username):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {current_username} not found"
        )
    
    # Create conversation
    db_conversation = conversation_repo.create_from_dto(conversation_data, current_username)
    
    # Add system message
    message_repo.create_system_message(
        db_conversation.id, 
        f"Conversation '{conversation_data.name}' created by {current_username}"
    )
    
    # Convert to DTO for response
    return conversation_repo.to_dto(db_conversation)

@cached(ttl_seconds=60, key_prefix="conversation")
async def get_conversation(
    conversation_id: str,
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationDto:
    """Get a conversation by ID."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    
    # Get conversation
    db_conversation = conversation_repo.get_by_id(conversation_id)
    
    if not db_conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Check if the user is the owner
    if db_conversation.user_username != current_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this conversation"
        )
    
    # Convert to DTO for response
    return conversation_repo.to_dto(db_conversation)

@cached(ttl_seconds=30, key_prefix="user_conversations")
async def get_user_conversations(
    username: str,
    limit: int = 20,
    offset: int = 0,
    db: Session = Depends(get_db)
) -> List[ConversationDto]:
    """Get all conversations for a user with pagination."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    user_repo = UserRepository(db)
    
    # Check if user exists
    user = user_repo.get_by_username(username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {username} not found"
        )
    
    # Get conversations with pagination
    conversations = conversation_repo.get_for_user(username, limit, offset)
    
    # Convert to DTOs
    return [conversation_repo.to_dto(conv) for conv in conversations]

async def send_message(
    message_data: SendMessageDto,
    current_username: str,
    db: Session = Depends(get_db)
) -> MessageDto:
    """Send a message in a conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    # Get conversation
    conversation = conversation_repo.get_by_id(message_data.conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {message_data.conversation_id} not found"
        )
    
    # Check if the user is the owner
    if conversation.user_username != current_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this conversation"
        )
    
    # Create message
    message = message_repo.create_from_dto(message_data, current_username)
    
    # Invalidate conversation cache since we modified it
    invalidate_conversation_cache(message_data.conversation_id)
    
    # Convert to DTO for response
    return message_repo.to_dto(message)

@cached(ttl_seconds=30, key_prefix="conversation_messages")
async def get_conversation_messages(
    conversation_id: str,
    current_username: str,
    limit: int = 50,
    offset: int = 0,
    db: Session = Depends(get_db)
) -> List[MessageDto]:
    """Get messages for a conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    # Get conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Check if the user is the owner
    if conversation.user_username != current_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this conversation"
        )
    
    # Get messages
    messages = message_repo.get_for_conversation(conversation_id, limit, offset)
    
    # Convert to DTOs
    return [message_repo.to_dto(msg) for msg in messages]

@cached(ttl_seconds=15, key_prefix="conversation_state")
async def get_conversation_state(
    conversation_id: str,
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationStateDto:
    """Get the current state of a conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    session_repo = UserSessionRepository(db)
    message_repo = MessageRepository(db)
    
    # Get conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Check if the user is the owner
    if conversation.user_username != current_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this conversation"
        )
    
    # Get active sessions
    active_sessions = session_repo.get_active_sessions_for_conversation(conversation_id)
    active_users = [session.user_username for session in active_sessions]
    
    # Get recent messages
    messages = message_repo.get_for_conversation(conversation_id, limit=50)
    message_dtos = [message_repo.to_dto(msg) for msg in messages]
    
    # Get last updated time
    last_updated = None
    if messages:
        last_updated = messages[0].timestamp.isoformat()
    
    return ConversationStateDto(
        conversation_id=conversation_id,
        active_users=active_users,
        messages=message_dtos,
        last_updated=last_updated
    )

@cached(ttl_seconds=60, key_prefix="conversation_data")
async def get_conversation_data(
    conversation_id: str,
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationDto:
    """Get all data for a conversation, including state."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    
    # Get conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Check if the user is the owner
    if conversation.user_username != current_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this conversation"
        )
    
    # Convert to DTO for response
    return conversation_repo.to_dto(conversation)

async def update_conversation_state(
    conversation_id: str,
    state_data: UpdateConversationStateDto,
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationDto:
    """Update state fields in a conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    
    # Get conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Check if the user is the owner
    if conversation.user_username != current_username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not the owner of this conversation"
        )
    
    # Create a dict with only the non-None fields
    update_data = {}
    if state_data.shared_state is not None:
        update_data['shared_state'] = state_data.shared_state
    if state_data.threads is not None:
        update_data['threads'] = state_data.threads
    if state_data.settings is not None:
        update_data['settings'] = state_data.settings
    
    # Update the conversation
    updated_conversation = conversation_repo.update_state(conversation_id, update_data)
    
    # Invalidate conversation cache since we modified it
    invalidate_conversation_cache(conversation_id)
    
    # Convert to DTO for response
    return conversation_repo.to_dto(updated_conversation) 