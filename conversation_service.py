import logging
import datetime
from typing import List, Optional, Set
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import get_db
from models import User, Conversation, Message, UserSession
from dto import ConversationDto, CreateConversationDto, MessageDto, SendMessageDto, ConversationStateDto
import state
from state_manager import conversation_lock
from repositories import ConversationRepository, UserRepository, MessageRepository, UserSessionRepository

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

async def get_user_conversations(
    username: str,
    db: Session = Depends(get_db)
) -> List[ConversationDto]:
    """Get all conversations for a user."""
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
    
    # Get conversations
    conversations = conversation_repo.get_for_user(username)
    
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
    
    # Convert to DTO for response
    return message_repo.to_dto(message)

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