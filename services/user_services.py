import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, List
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from passlib.context import CryptContext
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from pydantic import BaseModel
import json
import random
import string
from zerobouncesdk import ZeroBounce, ZBException, ZBValidateStatus

from database import get_db, get_valkey_connection
from models import User
from dto import UserDto, CreateUserDto, TokenData, LoginDto, ConversationDto
from repositories import UserRepository, ConversationRepository, MessageRepository, ProjectRepository
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
    
    # ZeroBounce Email Validation
    if settings.ZEROBOUNCE_API_KEY:
        try:
            zero_bounce = ZeroBounce(settings.ZEROBOUNCE_API_KEY)
            validation_response = zero_bounce.validate(user_data.email)
            if validation_response.status != ZBValidateStatus.valid:
                logger.warning(f"ZeroBounce validation failed for {user_data.email}: Status - {validation_response.status}, SubStatus - {validation_response.sub_status}")
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Email address is not valid. Status: {validation_response.status}"
                )
                
            logger.info(f"ZeroBounce validation successful for {user_data.email}, Status: {validation_response.status}, SubStatus: {validation_response.sub_status}")
        except HTTPException: # Re-raise the HTTPException from the validation status check
            raise
        except ZBException as e:
            logger.error(f"ZeroBounce API error for {user_data.email}: {e}")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Email validation service is temporarily unavailable. Please try again later."
            )
        except Exception as e:
            logger.error(f"Unexpected error during ZeroBounce validation for {user_data.email}: {e}")
            # Fallback or raise error
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during email validation."
            )
    else:
        logger.warning("ZEROBOUNCE_API_KEY not configured. Skipping email validation.")

    token_limit = None
    if not user_data.email.endswith("@mamba.agency"):
        token_limit = 800

    is_mamba_user = user_data.email.endswith("@mamba.agency")

    try:
        # Create an instance of the User model directly
        user = User(
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password=hashed_password,
            role="user", # Default role
            token_limit=None if is_mamba_user else settings.DEFAULT_FREE_USER_TOKEN_LIMIT,
            is_subscribed=False, # Default to not subscribed
            email_verified=True, # Set to True by default as we are removing verification
            tokens_last_reset_at=datetime.now(timezone.utc) if not is_mamba_user else None
        )
        
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

async def _generate_auth_response(user: User, db: Session) -> dict:
    """Helper function to generate the authentication response for a user."""
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.email}, expires_delta=access_token_expires
    )

    project_repo = ProjectRepository(db)

    # Get projects
    projects = project_repo.get_for_user(user.email)
    project_summaries = []
    for project in projects:
        project_summaries.append({
            "id": project.id,
            "name": project.name,
            "website_url": project.website_url,
            "project_data": project.project_data
        })

    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": {
            "email": user.email,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "token_limit": user.token_limit,
            "is_subscribed": user.is_subscribed,
            "email_verified": user.email_verified
        },
        "projects": project_summaries
    }

async def login_user(login_data: LoginDto, db: Session) -> dict:
    """Authenticate user and return JWT token."""
    user_repo = UserRepository(db)
    user = user_repo.get_by_email(login_data.email)

    if not user or not pwd_context.verify(login_data.password, user.password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return await _generate_auth_response(user, db)

async def get_or_create_google_user(email: str, first_name: str, last_name: str, db: Session) -> dict:
    """Get an existing user or create a new one for Google Sign-In, then return auth response."""
    user_repo = UserRepository(db)
    user = user_repo.get_by_email(email)

    if not user:
        # Create new user for Google Sign-In
        token_limit = None
        is_mamba_user_via_google = email.endswith("@mamba.agency")
        if not is_mamba_user_via_google:
            token_limit = settings.DEFAULT_FREE_USER_TOKEN_LIMIT
        
        new_user_data = User(
            email=email,
            first_name=first_name,
            last_name=last_name,
            password=pwd_context.hash(settings.GOOGLE_USER_DEFAULT_PASSWORD), 
            role="user",
            token_limit=token_limit,
            is_subscribed=False,
            email_verified=True, 
            tokens_last_reset_at=datetime.now(timezone.utc) if not is_mamba_user_via_google else None
        )
        try:
            db.add(new_user_data)
            db.commit()
            db.refresh(new_user_data)
            user = new_user_data
        except IntegrityError: 
            db.rollback()
            logger.error(f"Integrity error creating Google user {email}, user might have been created concurrently.")
            user = user_repo.get_by_email(email)
            if not user:
                 raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Could not create or find user after Google sign-in.")
        except Exception as e:
            db.rollback()
            logger.error(f"Error creating Google user {email}: {e}")
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Error creating user account after Google sign-in.")

    return await _generate_auth_response(user, db)

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
