import uvicorn # type: ignore
import os # Ensure os is imported early
# from dotenv import load_dotenv # type: ignore # No longer needed here
from core.config import settings # Import settings early to load .env
from contextlib import asynccontextmanager # Import for lifespan manager

# --- Load Environment Variables --- 
# load_dotenv(override=True) # Moved to the top and handled by core.config
# --------------------------------

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Response # type: ignore
from fastapi.responses import HTMLResponse # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import logging
from typing import Dict, Any # Ensure Any is imported
import certifi # Ensure certifi is imported before use
from sqlalchemy.orm import Session # type: ignore
from passlib.context import CryptContext # type: ignore
from datetime import datetime, timedelta, timezone
from reset_database import reset_database
from reset_pins import reset_all_pins

# State and Auth
import auth
from auth import get_current_user, create_access_token, get_token_header, verify_google_id_token
from services.user_services import register_user, login_user, rename_conversation, delete_conversation, get_conversation_details, get_user_conversations, toggle_conversation_pin, get_or_create_google_user
from dto import (
    CreateUserDto, UserDto, LoginDto, 
    ConversationDto, CreateConversationDto,
    MessageDto, SendMessageDto, ConversationStateDto,
    UpdateConversationStateDto, RenameConversationDto
)
from pydantic import BaseModel # Add this import

# Database and Models
from database import (
    get_db, engine, SessionLocal, 
    # Rename imports for clarity
    create_valkey_pool, # Make sure this is imported
    close_valkey_pool,  # Make sure this is imported
    get_valkey_connection 
)
from models import Base, User
from repositories import ConversationRepository, MessageRepository, UserRepository
from services.agency_services import AgencyService
# from utils.valkey_utils import publish_message_to_valkey
import json

# os.environ["SSL_CERT_FILE"] = certifi.where() # Set via settings if needed or ensure certifi is available
if settings.SSL_CERT_FILE:
    os.environ["SSL_CERT_FILE"] = settings.SSL_CERT_FILE
elif certifi.where(): # Default to certifi.where() if not in settings
    os.environ["SSL_CERT_FILE"] = certifi.where()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Cache TTLs
MESSAGES_CACHE_TTL_SECONDS = 60  # 1 minute
# CONVERSATION_DETAILS_CACHE_TTL_SECONDS = 300 # Defined in user_services.py
# USER_CONVERSATIONS_CACHE_TTL_SECONDS = 120 # Defined in user_services.py

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# Lifespan manager for startup and shutdown events
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup logic
    logger.info("Application startup (lifespan)... Genta was here")
    logger.info("Creating Valkey/Redis connection pool (lifespan)... Genta was here")
    await create_valkey_pool()
    # Add other startup tasks if needed
    yield
    # Shutdown logic
    logger.info("Application shutdown (lifespan)... Genta was here")
    logger.info("Closing Valkey/Redis connection pool (lifespan)... Genta was here")
    await close_valkey_pool()
    # Add other shutdown tasks if needed

app = FastAPI(
    title="Mamba FastAPI Chat",
    description="A FastAPI application with WebSocket chat and user authentication",
    version="1.0.0",
    openapi_tags=[
        {
            "name": "Authentication",
            "description": "Operations related to user authentication"
        },
        {
            "name": "Chat",
            "description": "Chat operations, conversations and messages"
        },
        {
            "name": "Admin",
            "description": "Administrative operations"
        }
    ],
    lifespan=lifespan # Add the lifespan manager here
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173","http://localhost:8000", "http://178.128.90.137", "https://front-genta.xyz", "http://front-genta.xyz"],  # Or restrict to your frontend URL like ["https://yourfrontend.com"]
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create database tables
Base.metadata.create_all(bind=engine)

# @app.options("/{path:path}")
# async def preflight(full_path: str, request: Request) -> Response:
#     return Response(status_code=204)


@app.get("/")
async def read_root():
     return {"message": "Welcome to Mamba FastAPI Server"}

class GoogleLoginRequest(BaseModel):
    token: str # This will be the Google ID token from the frontend

@app.post("/register", response_model=UserDto, tags=["Authentication"])
async def register_user_endpoint(user_data: CreateUserDto, db: Session = Depends(get_db)):
    """Register a new user."""
    return register_user(user_data, db)

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(login_data: LoginDto, db=Depends(get_db)):
    """Login a user and return an access token."""
    return await login_user(login_data, db)

@app.post("/subscribe", tags=["User"])
async def subscribe_user_endpoint(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """Allows an authenticated user to 'subscribe'."""

    if current_user.email.endswith("@mamba.agency"):
        # Mamba agency users already have unlimited access
        return {"message": "Mamba agency users have unlimited access by default."}

    if current_user.is_subscribed:
        return {"message": "You are already subscribed and have unlimited tokens."}

    current_user.is_subscribed = True
    current_user.token_limit = None  # Unlimited tokens upon subscription
    db.add(current_user)
    db.commit()
    db.refresh(current_user)

    # Placeholder for actual subscription benefits/UI update
    return {"message": "Thanks for the support! Follow development to see the updates! You now have unlimited tokens."}

@app.post("/chat", tags=["Chat"])
async def create_chat(
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated for new conversation")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    # Get message from request
    message = request.get("message")
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required"
        )

    # Create new conversation
    conversation_repo = ConversationRepository(db)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    conversation = conversation_repo.create_from_dto(
        CreateConversationDto(name=f"Chat @{timestamp}"),
        creator_email=current_user.email
    )

    logger.info(f"Created new conversation {conversation.id} for user {current_user.email}")

    # Forward the message to the chat endpoint
    response = await chat_endpoint(
        conversation_id=conversation.id,
        request=request,
        token=token,
        db=db
    )
    response["conversation_id"] = conversation.id
    response["conversation_name"] = conversation.name
    return response

@app.post("/chat/{conversation_id}", tags=["Chat"])
async def chat_endpoint(
    conversation_id: str,
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated")

        # Token Management Logic
        is_mamba_user = current_user.email.endswith("@mamba.agency")
        is_subscribed_user = current_user.is_subscribed
        can_have_unlimited_tokens = is_mamba_user or is_subscribed_user

        if not can_have_unlimited_tokens:
            now = datetime.now(timezone.utc)
            needs_token_reset = False
            if current_user.tokens_last_reset_at is None:
                needs_token_reset = True
            elif now - current_user.tokens_last_reset_at > timedelta(hours=24):
                needs_token_reset = True

            if needs_token_reset:
                current_user.token_limit = settings.DEFAULT_FREE_USER_TOKEN_LIMIT
                current_user.tokens_last_reset_at = now
                db.add(current_user)
                db.commit()
                db.refresh(current_user)
            
            if current_user.token_limit is None or current_user.token_limit <= 0:
                logger.warning(f"User {current_user.email} token limit {current_user.token_limit} insufficient.")
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Token limit reached. Please subscribe for unlimited access or wait 24 hours for tokens to reset."
                )
        # End of Token Management Logic

    except HTTPException as e:
        raise e

    # Get message from request
    message = request.get("message")
    if not message:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Message is required"
        )

    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)  # Create message repository

    # Validate that the conversation belongs to the current user
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )

    logger.info(f"Received message from client {current_user.email} for conversation {conversation_id}: {message}")

    # Save user message to database
    user_message_dto = SendMessageDto(
        conversation_id=conversation_id,
        content=message
    )
    message_repo.create_from_dto(user_message_dto, current_user.email, is_from_agency=False)

    # Initialize or load agency
    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)

    try:
        # Get completion from agency
        agency_response = agency.get_completion(message=message)
        
        # Decrement token for free users if operation was successful
        if not can_have_unlimited_tokens:
            if current_user.token_limit is not None and current_user.token_limit > 0:
                current_user.token_limit -= 1 # Assuming 1 token per message
                db.add(current_user)
                db.commit()
            # else: log or handle case where token_limit became <=0 unexpectedly after check? 
            # For now, the check before agency.get_completion should prevent this.

        # Save AI response to database
        ai_message_dto = SendMessageDto(
            conversation_id=conversation_id,
            content=agency_response
        )
        message_repo.create_from_dto(ai_message_dto, None, is_from_agency=True)
        
        agency_action = agency.shared_state.get("action")
        if agency_action:
            response = {
                "response": agency_response, 
                "is_from_agency": True, 
                "action": agency_action
            }
        else:
            response = {
                "response": agency_response, "is_from_agency": True}
            
        if agency_action and agency_action.get("action-type") == "keywords_ready":
            agency.shared_state.set("action", None)
        # Save updated state
        conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)

        # --- Publish to Valkey AFTER successful commit ---
        # try:
        #     if user_message_dto:
        #         await publish_message_to_valkey(conversation_id, message_repo.to_dto(user_message_dto))
        #     if ai_message_dto:
        #         await publish_message_to_valkey(conversation_id, message_repo.to_dto(ai_message_dto))
            
        #     return response
        # except Exception as pub_e:
        #     # Log failure to publish but don't fail the request, DB is source of truth
        #     logger.error(f"Failed to publish message(s) to Valkey for conv {conversation_id}: {pub_e}")
        #     return response
        return response # Return original response directly
    except Exception as e:
        logger.error(f"Error processing message for {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )

@app.get("/messages/{conversation_id}", tags=["Chat"])
async def get_messages_flexible(
    conversation_id: str,
    limit: int = Query(0, description="Maximum number of messages to retrieve, set to 0 for all messages"),
    offset: int = Query(0, description="Number of messages to skip"),
    order: str = Query("desc", description="Order of messages: 'asc' for oldest first, 'desc' for newest first"),
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """
    Get messages for a conversation with flexible options for ordering and pagination.
    Implements cache-aside (lazy loading) pattern with Redis.
    """
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        # logger.info(f"User {current_user.email} accessing messages for conversation {conversation_id}") # Moved logging after cache check
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    redis_conn = await get_valkey_connection()
    # Create a cache key that includes all query parameters that affect the result
    cache_key = f"messages:{conversation_id}:limit_{limit}:offset_{offset}:order_{order.lower()}"

    if redis_conn:
        try:
            cached_data_json = await redis_conn.get(cache_key)
            if cached_data_json:
                logger.info(f"Cache HIT for messages: {cache_key} by user {current_user.email}")
                return json.loads(cached_data_json)
            else:
                logger.info(f"Cache MISS for messages: {cache_key} by user {current_user.email}")
        except Exception as e:
            logger.error(f"Redis GET error for messages {cache_key}: {e}", exc_info=True)
            # Proceed to fetch from DB if Redis fails

    logger.info(f"User {current_user.email} accessing messages for conversation {conversation_id} from DB (after cache miss/error)")

    # Validate conversation exists and belongs to user
    conversation_repo = ConversationRepository(db)
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )
    
    # Use custom repository method for flexible retrieval
    message_repo = MessageRepository(db)
    
    # Validate order parameter
    if order.lower() not in ["asc", "desc"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must be 'asc' or 'desc'"
        )
    
    # Get messages with the specified options
    messages = message_repo.get_messages_flexible(
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        ascending=(order.lower() == "asc")
    )
    
    # Convert to DTOs
    message_dtos = [message_repo.to_dto(message) for message in messages]

    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)

    latest_action = agency.shared_state.get("action", None)

    keyword_tables = agency.shared_state.get("keywords_output", None)
    generated_content = {}
    
    if keyword_tables:
        generated_content["keyword_tables"] = keyword_tables
    
    return {
        "messages": message_dtos, 
        "conversation_id": conversation_id,
        "total_count": message_repo.count_for_conversation(conversation_id),
        "order": order,
        "limit": limit,
        "offset": offset,
        "generated_content": generated_content,
        "action": latest_action
    }

@app.get("/conversations", tags=["Chat"])
async def get_conversations_with_messages(
    limit: int = Query(20, description="Maximum number of conversations to retrieve"),
    offset: int = Query(0, description="Number of conversations to skip"),
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Get all conversations for the current user with their latest messages."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} retrieving conversations")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )
    
    # Get conversations for user
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    conversations = conversation_repo.get_for_user(current_user.email, limit, offset)
    result = []
    
    # For each conversation, get the latest message
    for conversation in conversations:
        conv_dto = conversation_repo.to_dto(conversation)
        latest_messages = message_repo.get_for_conversation(conversation.id, limit=1, offset=0)
        
        # Add latest message preview if available
        if latest_messages:
            latest_message = message_repo.to_dto(latest_messages[0])
            conv_dto.latest_message = latest_message
        
        result.append(conv_dto)
    
    return {"conversations": result}

@app.post("/submit_form/{conversation_id}", tags=["Chat"])
async def submit_form(
    conversation_id: str,
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Submit a form for a conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated")

        # Token Management Logic (for submit_form)
        is_mamba_user = current_user.email.endswith("@mamba.agency")
        is_subscribed_user = current_user.is_subscribed
        can_have_unlimited_tokens = is_mamba_user or is_subscribed_user 

        if not can_have_unlimited_tokens: 
            now = datetime.now(timezone.utc)
            needs_token_reset = False
            if current_user.tokens_last_reset_at is None or \
               (now - current_user.tokens_last_reset_at > timedelta(hours=24)):
                needs_token_reset = True

            if needs_token_reset:
                current_user.token_limit = settings.DEFAULT_FREE_USER_TOKEN_LIMIT
                current_user.tokens_last_reset_at = now
                db.add(current_user)
                db.commit()
                db.refresh(current_user)
            
            if current_user.token_limit is None or current_user.token_limit <= 0:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Token limit reached. Please subscribe or wait for tokens to reset."
                )
        # End of Token Management Logic

    except HTTPException as e:
        raise e

    # Get message from request
    form_data = request.get("form_data")
    form_action = request.get("action", None)
    if not form_data:
        if form_action == "cancel_form":
            message = "I have cancelled the form"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Form data is required"
            )

    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)  # Create message repository

    # Validate that the conversation belongs to the current user
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )

    logger.info(f"Received business form data from client {current_user.email} for conversation {conversation_id}")
    message = "I have submitted the form"
    # Save user message to database
    user_message_dto = SendMessageDto(
        conversation_id=conversation_id,
        content=message
    )
    message_repo.create_from_dto(user_message_dto, current_user.email, is_from_agency=False)

    # Initialize or load agency
    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)

    try:
        # Set the form data in the shared state
        if form_data:
            agency.shared_state.set('business_info_data', form_data)
        if form_action == "cancel_form":
            agency.shared_state.set('action', None)
        # Get completion from agency
        agency_response = agency.get_completion(message=message)
        
        # Decrement token for free users if operation was successful
        if not can_have_unlimited_tokens: 
            if current_user.token_limit is not None and current_user.token_limit > 0:
                current_user.token_limit -= 1 
                db.add(current_user)
                db.commit()

        # Save updated state
        conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)
        
        # Save AI response to database
        ai_message_dto = SendMessageDto(
            conversation_id=conversation_id,
            content=agency_response
        )
        message_repo.create_from_dto(ai_message_dto, None, is_from_agency=True)
        
        if agency.shared_state.get("action"):
            action = agency.shared_state.get("action")
            return {"response": agency_response, "is_from_agency": True, "action": action}
        else:
            return {"response": agency_response, "is_from_agency": True}
    except Exception as e:
        logger.error(f"Error processing message for {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error processing message: {str(e)}"
        )

    # --- Update any other publishing calls similarly (e.g., in /submit_form) ---

@app.post("/get_keywords/{conversation_id}", tags=["Chat"])
async def get_keywords(
    conversation_id: str,
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} authenticated")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    # Get message from request
    table_id = request.get("table_id")
    if not table_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Table ID is required"
        )

    conversation_repo = ConversationRepository(db)

    # Validate that the conversation belongs to the current user
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )

    logger.info(f"Received business form data from client {current_user.email} for conversation {conversation_id}")

    agency = AgencyService.initialize_agency(conversation_id, conversation_repo)
    keywords_output = agency.shared_state.get('keywords_output')
    table_data = keywords_output.get(table_id)
    if not table_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Table ID not found"
        )
    agency.shared_state.set('action', None)
    conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)

    return table_data

@app.delete("/conversations/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Chat"])
async def delete_conversation_endpoint(
    conversation_id: str,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Deletes an entire conversation and its messages."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to delete conversation {conversation_id}")
    except HTTPException as e:
        # Re-raise authentication errors
        raise e 

    # Call the service function
    return await delete_conversation(conversation_id, current_user.email, db)

@app.patch("/conversations/{conversation_id}/rename", response_model=ConversationDto, tags=["Chat"])
async def rename_conversation_endpoint(
    conversation_id: str,
    rename_data: RenameConversationDto,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Rename an existing conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to rename conversation {conversation_id}")
    except HTTPException as e:
        raise e

    # Call the service function
    return await rename_conversation(conversation_id, rename_data.name, current_user.email, db)

@app.get("/conversations/{conversation_id}", tags=["Chat"])
async def get_conversation_details_endpoint(
    conversation_id: str,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Get detailed information about a specific conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} requesting details for conversation {conversation_id}")
    except HTTPException as e:
        raise e

    # Call the service function
    return await get_conversation_details(conversation_id, current_user.email, db)

@app.get("/user/conversations", tags=["Chat"])
async def get_user_conversations_endpoint(
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Get all conversations belonging to the authenticated user with essential details."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} requesting their conversations")
    except HTTPException as e:
        raise e

    # Call the service function with the user's email and database session
    return await get_user_conversations(current_user.email, db)

@app.post("/conversations/{conversation_id}/toggle-pin", response_model=ConversationDto, tags=["Chat"])
async def toggle_pin_endpoint(
    conversation_id: str,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Toggle the pinned status of a conversation."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to toggle pin for conversation {conversation_id}")
    except HTTPException as e:
        raise e

    # Call the service function
    return await toggle_conversation_pin(conversation_id, current_user.email, db)

@app.post("/auth/google", tags=["Authentication"])
async def google_auth_endpoint(request: GoogleLoginRequest, db: Session = Depends(get_db)):
    """Handles Google Sign-In/Sign-Up."""
    google_token = request.token
    try:
        idinfo = await verify_google_id_token(google_token, settings.GOOGLE_CLIENT_ID)
        if not idinfo or "email" not in idinfo:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid Google token")

        email = idinfo["email"]
        first_name = idinfo.get("given_name", "")
        last_name = idinfo.get("family_name", "")

        auth_response = await get_or_create_google_user(
            email=email,
            first_name=first_name,
            last_name=last_name,
            db=db
        )
        return auth_response

    except ValueError as e: # Specific exception from google-auth library for invalid token
        logger.error(f"Google token verification failed: {e}")
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=f"Invalid Google token: {e}")
    except HTTPException as e:
        raise e # Re-raise existing HTTPExceptions
    except Exception as e:
        logger.error(f"Error during Google authentication for token {google_token[:20]}...: {e}")
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Google authentication failed.")

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print("Access the chat interface at http://localhost:8000")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
