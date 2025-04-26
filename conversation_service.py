import logging
import datetime
from typing import List, Optional, Set
from fastapi import Depends, HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_

from database import get_db
from models import User, Conversation, Message, UserSession
from dto import ConversationDto, CreateConversationDto, MessageDto, JoinConversationDto, LeaveConversationDto, SendMessageDto, ConversationStateDto
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
    """Create a new conversation with the given participants."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    user_repo = UserRepository(db)
    message_repo = MessageRepository(db)
    
    # Verify all participants exist
    for username in conversation_data.participants:
        if not user_repo.get_by_username(username):
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"User {username} not found"
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
    
    # Check if the user is a participant
    participants = [user.username for user in db_conversation.participants]
    if current_username not in participants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
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

async def join_conversation(
    join_data: JoinConversationDto,
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationDto:
    """Join a conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    user_repo = UserRepository(db)
    message_repo = MessageRepository(db)
    session_repo = UserSessionRepository(db)
    
    # Verify the user has permission to add others (they must be a participant)
    if join_data.username != current_username:
        # Check if current user is in the conversation
        db_conversation = conversation_repo.get_by_id(join_data.conversation_id)
        if not db_conversation:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Conversation {join_data.conversation_id} not found"
            )
        
        participants = [user.username for user in db_conversation.participants]
        if current_username not in participants:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="You don't have permission to add users to this conversation"
            )
    
    # Verify user exists
    user = user_repo.get_by_username(join_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"User {join_data.username} not found"
        )
    
    # Get conversation
    conversation = conversation_repo.get_by_id(join_data.conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {join_data.conversation_id} not found"
        )
    
    # Add user to conversation
    added = conversation_repo.add_participant(join_data.conversation_id, join_data.username)
    
    # Create or activate user session
    session_repo.create_or_activate_session(join_data.username, join_data.conversation_id)
    
    # Add system message about user joining
    message_repo.create_system_message(
        join_data.conversation_id, 
        f"User {join_data.username} joined the conversation"
    )
    
    # Register the active session in memory too
    with conversation_lock(join_data.conversation_id):
        state.register_active_session(join_data.conversation_id, join_data.username)
    
    # Get updated conversation
    updated_conversation = conversation_repo.get_by_id(join_data.conversation_id)
    
    # Convert to DTO for response
    return conversation_repo.to_dto(updated_conversation)

async def leave_conversation(
    leave_data: LeaveConversationDto,
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationDto:
    """Leave a conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    session_repo = UserSessionRepository(db)
    
    # Verify the user has permission (can only remove themselves or if they're admin)
    if leave_data.username != current_username:
        # Additional permission check would go here
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You don't have permission to remove other users from this conversation"
        )
    
    # Get the conversation
    conversation = conversation_repo.get_by_id(leave_data.conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {leave_data.conversation_id} not found"
        )
    
    # Verify user is a participant
    participants = [user.username for user in conversation.participants]
    if leave_data.username not in participants:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"User {leave_data.username} is not a participant in this conversation"
        )
    
    # Deactivate user session
    session_repo.deactivate_session(leave_data.username, leave_data.conversation_id)
    
    # Add system message about user leaving
    message_repo.create_system_message(
        leave_data.conversation_id, 
        f"User {leave_data.username} left the conversation"
    )
    
    # Unregister the active session in memory
    with conversation_lock(leave_data.conversation_id):
        state.unregister_active_session(leave_data.conversation_id, leave_data.username)
    
    # Get updated conversation
    updated_conversation = conversation_repo.get_by_id(leave_data.conversation_id)
    
    # Convert to DTO for response
    return conversation_repo.to_dto(updated_conversation)

async def send_message(
    message_data: SendMessageDto,
    current_username: str,
    db: Session = Depends(get_db)
) -> MessageDto:
    """Send a message to a conversation."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    # Get the conversation
    conversation = conversation_repo.get_by_id(message_data.conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {message_data.conversation_id} not found"
        )
    
    # Check if user is a participant
    participants = [user.username for user in conversation.participants]
    if current_username not in participants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )
    
    # Create the message
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
    
    # Get the conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Check if user is a participant
    participants = [user.username for user in conversation.participants]
    if current_username not in participants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )
    
    # Get messages
    messages = message_repo.get_for_conversation(conversation_id, limit, offset)
    
    # Convert to DTOs
    return [message_repo.to_dto(message) for message in messages]

async def get_conversation_state(
    conversation_id: str,
    current_username: str,
    db: Session = Depends(get_db)
) -> ConversationStateDto:
    """Get the current state of a conversation, including active users and recent messages."""
    # Initialize repositories
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    session_repo = UserSessionRepository(db)
    
    # Get the conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Conversation {conversation_id} not found"
        )
    
    # Check if user is a participant
    participants = [user.username for user in conversation.participants]
    if current_username not in participants:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You are not a participant in this conversation"
        )
    
    # Get active users from both DB and memory
    active_sessions = session_repo.get_active_sessions_for_conversation(conversation_id)
    active_users_db = [session.user_username for session in active_sessions]
    
    # Merge with in-memory active users
    active_users_memory = state.get_active_users(conversation_id)
    active_users = list(set(active_users_db).union(active_users_memory))
    
    # Get recent messages
    recent_messages = message_repo.get_for_conversation(conversation_id, limit=20)
    message_dtos = [message_repo.to_dto(message) for message in recent_messages]
    
    # Build the state DTO
    return ConversationStateDto(
        conversation_id=conversation_id,
        active_users=active_users,
        messages=message_dtos,
        last_updated=conversation.updated_at.isoformat() if conversation.updated_at else None
    ) 