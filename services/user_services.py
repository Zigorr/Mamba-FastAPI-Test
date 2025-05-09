import logging
from datetime import datetime, timedelta
from typing import Optional, List
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
import json

from database import get_db, get_valkey_connection
from models import User
from dto import UserDto, CreateUserDto, TokenData, LoginDto, ConversationDto
from repositories import UserRepository, ConversationRepository, MessageRepository
from auth import create_access_token
from core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache TTL for conversation details (e.g., 5 minutes)
CONVERSATION_CACHE_TTL_SECONDS = 300
# Cache TTL for user's list of conversations (e.g., 2 minutes)
USER_CONVERSATIONS_CACHE_TTL_SECONDS = 120

# Security configuration
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="login")

def register_user(user_data: CreateUserDto, db: Session) -> UserDto:
    """Register a new user."""
    user_repo = UserRepository(db)
    hashed_password = pwd_context.hash(user_data.password)
    
    try:
        user = user_repo.create_from_dto(user_data, hashed_password)
        db.add(user)
        db.commit()
        db.refresh(user)

        return UserDto(
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name
        )
        
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Error during user registration for {user_data.email}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An error occurred during registration."
        )

def authenticate_user(email: str, password: str, db: Session) -> Optional[User]:
    """Authenticate a user by email and password."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(email)
    
    # Verify password if user exists
    if not user or not pwd_context.verify(password, user.password):
        return None
    
    return user

def get_user_by_email(email: str, db: Session) -> Optional[UserDto]:
    """Get a user by email."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(email)
    
    if not user:
        return None
    
    # Return user DTO
    return UserDto(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name
    )

def get_users(db: Session, skip: int = 0, limit: int = 50) -> List[UserDto]:
    """Get a list of users."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get users
    users = user_repo.get_all()
    
    # Convert to DTOs
    return [
        UserDto(
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name
        )
        for user in users
    ]

def update_user(email: str, user_data: dict, db: Session) -> Optional[UserDto]:
    """Update a user's information."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(email)
    
    if not user:
        return None
    
    # Update user
    updated_user = user_repo.update(user, user_data)
    
    # Return user DTO
    return UserDto(
        email=updated_user.email,
        first_name=updated_user.first_name,
        last_name=updated_user.last_name
    )

def delete_user(email: str, db: Session) -> bool:
    """Delete a user."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Delete user
    return user_repo.delete(email)

async def login_user(login_data: LoginDto, db: Session) -> dict:
    """Authenticate user and return JWT token."""
    # Initialize repository
    user_repo = UserRepository(db)
    
    # Get user
    user = user_repo.get_by_email(login_data.email)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Verify password
    if not pwd_context.verify(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    userDto = UserDto(
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name
    )
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )
    
    # Get user's conversations
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    conversations = conversation_repo.get_for_user(user.email, limit=50)
    conversation_summaries = []
    
    for conversation in conversations:
        # Include ID, name and updated_at for sorting
        conversation_summaries.append({
            "id": conversation.id,
            "name": conversation.name,
            "updated_at": conversation.updated_at
        })
        # Sort conversations by updated_at after loop
        conversation_summaries = sorted(conversation_summaries, 
            key=lambda x: x["updated_at"], 
            reverse=True)
    
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": userDto,
        "conversations": conversation_summaries
    }

async def rename_conversation(conversation_id: str, new_name: str, current_user_email: str, db: Session):
    """
    Rename a conversation for the authenticated user.
    
    Args:
        conversation_id: ID of the conversation to rename
        new_name: New name for the conversation
        current_user_email: Email of the authenticated user
        db: Database session
        
    Returns:
        Updated conversation DTO
        
    Raises:
        HTTPException: If conversation not found or user lacks permission
    """
    logger = logging.getLogger(__name__)
    conversation_repo = ConversationRepository(db)
    
    # Find the conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        logger.warning(f"Conversation {conversation_id} not found for rename operation")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Authorization Check: Ensure the current user owns the conversation
    if conversation.user_email != current_user_email:
        logger.warning(f"User {current_user_email} forbidden to rename conversation {conversation_id} owned by {conversation.user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to rename this conversation"
        )
    
    # Perform the rename
    try:
        updated_conversation = conversation_repo.update(conversation_id, {"name": new_name})
        if updated_conversation:
            logger.info(f"Conversation {conversation_id} renamed to '{new_name}' by user {current_user_email}")
            return conversation_repo.to_dto(updated_conversation)
        else:
            # This case should ideally not be reached if the conversation was found above
            logger.error(f"Conversation {conversation_id} found but rename failed.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Failed to rename conversation"
            )
    except Exception as e:
        logger.error(f"Error renaming conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Could not rename conversation: {e}"
        )

async def delete_conversation(conversation_id: str, current_user_email: str, db: Session):
    """
    Delete a conversation for the authenticated user.
    
    Args:
        conversation_id: ID of the conversation to delete
        current_user_email: Email of the authenticated user
        db: Database session
        
    Returns:
        None on success
        
    Raises:
        HTTPException: If conversation not found, user lacks permission, or deletion fails
    """
    logger = logging.getLogger(__name__)
    conversation_repo = ConversationRepository(db)
    
    # Find the conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Authorization Check: Ensure the current user owns the conversation
    if conversation.user_email != current_user_email:
        logger.warning(f"User {current_user_email} forbidden to delete conversation {conversation_id} owned by {conversation.user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this conversation"
        )

    # Perform Deletion
    try:
        deleted = conversation_repo.delete_conversation(conversation_id)
        if deleted:
            logger.info(f"Conversation {conversation_id} deleted successfully by user {current_user_email}")
            return None 
        else:
            # This case should ideally not be reached if the conversation was found above
            logger.error(f"Conversation {conversation_id} found but deletion failed.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Failed to delete conversation"
            )
            
    except Exception as e:
        # Catch potential DB errors during delete
        logger.error(f"Error deleting conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Could not delete conversation: {e}"
        )

async def get_conversation_details(conversation_id: str, current_user_email: str, db: Session) -> ConversationDto:
    """
    Get detailed information about a specific conversation for the authenticated user.
    Implements cache-aside (lazy loading) pattern with Redis.
    """
    logger = logging.getLogger(__name__)
    
    redis_conn = await get_valkey_connection()
    cache_key = f"conversation_details:{conversation_id}:{current_user_email}"

    if redis_conn:
        try:
            cached_data_json = await redis_conn.get(cache_key)
            if cached_data_json:
                logger.info(f"Cache HIT for conversation details: {cache_key}")
                # Directly parse into ConversationDto if it's stored as such
                conversation_dto = ConversationDto.model_validate_json(cached_data_json)
                return conversation_dto
            else:
                logger.info(f"Cache MISS for conversation details: {cache_key}")
        except Exception as e:
            logger.error(f"Redis GET error for {cache_key}: {e}", exc_info=True)
            # Proceed to fetch from DB if Redis fails, don't let cache error break the app

    # Cache miss or Redis error, fetch from DB
    conversation_repo = ConversationRepository(db)
    conversation = conversation_repo.get_by_id(conversation_id)

    if not conversation:
        logger.warning(f"Conversation {conversation_id} not found in DB.")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )

    # Authorization Check
    if conversation.user_email != current_user_email:
        logger.warning(f"User {current_user_email} forbidden to access conversation {conversation_id} owned by {conversation.user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this conversation"
        )

    # Convert DB model to DTO
    # Assuming conversation_repo.to_dto exists and works correctly
    conversation_dto = conversation_repo.to_dto(conversation) 
    
    # Add latest message if your DTO and to_dto method handle it
    # This might require fetching the latest message separately if not already part of 'conversation'
    message_repo = MessageRepository(db)
    latest_messages = message_repo.get_for_conversation(conversation_id, limit=1, offset=0)
    if latest_messages:
        conversation_dto.latest_message = message_repo.to_dto(latest_messages[0])


    if redis_conn:
        try:
            # Serialize DTO to JSON for storing in Redis
            conversation_dto_json = conversation_dto.model_dump_json()
            await redis_conn.set(cache_key, conversation_dto_json, ex=CONVERSATION_CACHE_TTL_SECONDS)
            logger.info(f"Stored conversation details in cache: {cache_key} with TTL {CONVERSATION_CACHE_TTL_SECONDS}s")
        except Exception as e:
            logger.error(f"Redis SET error for {cache_key}: {e}", exc_info=True)
            # Log error but proceed, data is already fetched from DB

    return conversation_dto

async def get_user_conversations(current_user_email: str, db: Session = None):
    """
    Get all conversations belonging to a user with essential details.
    Implements cache-aside (lazy loading) pattern with Redis.
    """
    logger = logging.getLogger(__name__)
    redis_conn = await get_valkey_connection()
    cache_key = f"user_conversations_summary:{current_user_email}"

    if redis_conn:
        try:
            cached_data_json = await redis_conn.get(cache_key)
            if cached_data_json:
                logger.info(f"Cache HIT for user conversations summary: {cache_key}")
                return json.loads(cached_data_json) # Deserialize from JSON string
            else:
                logger.info(f"Cache MISS for user conversations summary: {cache_key}")
        except Exception as e:
            logger.error(f"Redis GET error for {cache_key}: {e}", exc_info=True)
            # Proceed to fetch from DB if Redis fails

    # Cache miss or Redis error, fetch from DB
    conversation_repo = ConversationRepository(db)
    
    # Get all conversations for user (no limit), ordered by updated_at descending (newest first)
    conversations = conversation_repo.get_for_user(
        current_user_email, 
        limit=0, 
        ascending=False  # Get newest first
    )
    
    # Extract only the essential details
    conversation_list = []
    for conversation in conversations:
        conversation_list.append({
            "id": conversation.id,
            "name": conversation.name,
            "updated_at": conversation.updated_at,
            "is_pinned": conversation.is_pinned
        })
    
    logger.info(f"Retrieved {len(conversation_list)} conversations for user {current_user_email} from DB")
    
    result_data = {
        "conversations": conversation_list,
        "total": len(conversation_list)
    }

    if redis_conn:
        try:
            result_data_json = json.dumps(result_data) # Serialize to JSON string
            await redis_conn.set(cache_key, result_data_json, ex=USER_CONVERSATIONS_CACHE_TTL_SECONDS)
            logger.info(f"Stored user conversations summary in cache: {cache_key} with TTL {USER_CONVERSATIONS_CACHE_TTL_SECONDS}s")
        except Exception as e:
            logger.error(f"Redis SET error for {cache_key}: {e}", exc_info=True)
            # Log error but proceed, data is already fetched from DB

    return result_data

async def toggle_conversation_pin(conversation_id: str, current_user_email: str, db: Session):
    """
    Toggle the 'pinned' status of a conversation.
    
    Args:
        conversation_id: ID of the conversation to toggle
        current_user_email: Email of the authenticated user
        db: Database session
        
    Returns:
        Updated conversation DTO
        
    Raises:
        HTTPException: If conversation not found or user lacks permission
    """
    logger = logging.getLogger(__name__)
    conversation_repo = ConversationRepository(db)
    
    # Find the conversation
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        logger.warning(f"Conversation {conversation_id} not found for toggle pin operation")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    # Authorization Check: Ensure the current user owns the conversation
    if conversation.user_email != current_user_email:
        logger.warning(f"User {current_user_email} forbidden to toggle pin for conversation {conversation_id} owned by {conversation.user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to pin/unpin this conversation"
        )
    
    # Toggle the pin status
    try:
        updated_conversation = conversation_repo.toggle_pin(conversation_id)
        if updated_conversation:
            new_status = "pinned" if updated_conversation.is_pinned else "unpinned"
            logger.info(f"Conversation {conversation_id} {new_status} by user {current_user_email}")
            return conversation_repo.to_dto(updated_conversation)
        else:
            # This should not happen since we already checked if conversation exists
            logger.error(f"Conversation {conversation_id} found but toggle pin failed.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
                detail="Failed to update conversation pin status"
            )
    except Exception as e:
        logger.error(f"Error toggling pin for conversation {conversation_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail=f"Could not update conversation pin status: {e}"
        )
