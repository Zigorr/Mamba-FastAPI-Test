import uvicorn # type: ignore
from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Response, Body # type: ignore
from fastapi.responses import HTMLResponse # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore
import os
from dotenv import load_dotenv # type: ignore
import logging
from typing import Dict
import certifi # type: ignore
from sqlalchemy.orm import Session # type: ignore
from passlib.context import CryptContext # type: ignore
from datetime import datetime
from reset_database import reset_database

# State and Auth
import auth
from auth import get_current_user, create_access_token, get_token_header
from services.user_services import register_user, login_user
from dto import (
    CreateUserDto, UserDto, LoginDto, 
    ConversationDto, CreateConversationDto,
    MessageDto, SendMessageDto, ConversationStateDto,
    UpdateConversationStateDto
)

# Database and Models
from database import (
    get_db, engine, SessionLocal, 
    create_redis_pool, close_redis_pool, get_redis_connection # Updated imports
)
from models import Base, User
from repositories import ConversationRepository, MessageRepository, UserRepository

# Agency
from services.agency_services import AgencyService
from utils.redis_utils import publish_message_to_redis # Import publish helper
import json # Import json

load_dotenv(override=True)
os.environ["SSL_CERT_FILE"] = certifi.where()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Password hashing
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

app = FastAPI(
    title="Mamba FastAPI Chat",
    description="A FastAPI application with WebSocket chat and user authentication",
    version="1.0.0"
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

# Add startup event to check Redis
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup...")
    logger.info("Creating Redis connection pool...")
    await create_redis_pool()
    # Add other startup tasks if needed

@app.on_event("shutdown")
async def shutdown_event():
    logger.info("Application shutdown...")
    logger.info("Closing Redis connection pool...")
    await close_redis_pool()
    # Add other shutdown tasks if needed

# @app.options("/{path:path}")
# async def preflight(full_path: str, request: Request) -> Response:
#     return Response(status_code=204)


@app.get("/")
async def read_root():
     return {"message": "Welcome to the Mamba FastAPI"}

@app.post("/register", tags=["Authentication"])
async def register_user_endpoint(user_data: CreateUserDto, request: Request, db: Session = Depends(get_db)):
    """Register a new user and trigger verification email."""
    # Note: Response model removed as we return a message dict now
    return await register_user(user_data, db, request)

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(login_data: LoginDto, db=Depends(get_db)):
    """Login a user and return an access token."""
    return await login_user(login_data, db)

@app.get("/verify-email", tags=["Authentication"], response_class=HTMLResponse)
async def verify_email_endpoint(token: str = Query(...), db: Session = Depends(get_db)):
    """Verify user's email address using the provided token."""
    user_repo = UserRepository(db)
    user = user_repo.get_by_verification_token(token)
    
    if not user:
        return HTMLResponse(content="<h1>Invalid or expired verification token.</h1>", status_code=400)
    
    if user.is_verified:
        return HTMLResponse(content="<h1>Email already verified.</h1>")

    if user_repo.verify_user(token):
        logger.info(f"Email verified successfully for user {user.email}")
        # You can redirect to a login page or show a success message
        return HTMLResponse(content="<h1>Email verified successfully! You can now log in.</h1>")
    else:
        # This case should ideally not happen if get_by_verification_token worked
        logger.error(f"Verification failed unexpectedly for token {token}")
        return HTMLResponse(content="<h1>Email verification failed. Please try again or contact support.</h1>", status_code=500)

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
        payload=request,
        token=token,
        db=db
    )
    response["conversation_id"] = conversation.id
    response["conversation_name"] = conversation.name
    return response

@app.post("/chat/{conversation_id}", tags=["Chat"])
async def chat_endpoint(
    conversation_id: str,
    payload: dict = Body(...),
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
    except HTTPException as e:
        raise e

    message_content = payload.get("message")
    if not message_content:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Message is required")

    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)

    user_message_db = None
    ai_message_db = None
    agency_response_content = None
    agency_action = None

    try:
        # Lock the conversation row
        conversation = conversation_repo.get_by_id_for_update(conversation_id)
        if not conversation:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Conversation not found")
        if conversation.user_email != current_user.email:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

        logger.info(f"Processing message from {current_user.email} for conv {conversation_id}: {message_content}")

        # 1. Save user message (no commit yet)
        user_message_dto = SendMessageDto(conversation_id=conversation_id, content=message_content)
        user_message_db = message_repo.create_from_dto(user_message_dto, current_user.email, is_from_agency=False)

        # 2. Initialize agency and get completion (reads state from locked conversation)
        agency = AgencyService.initialize_agency(conversation_id, conversation_repo, conversation_override=conversation)
        agency_response_content = agency.get_completion(message=message_content)

        # 3. Save AI response (no commit yet)
        if agency_response_content:
            ai_message_dto = SendMessageDto(conversation_id=conversation_id, content=agency_response_content)
            ai_message_db = message_repo.create_from_dto(ai_message_dto, None, is_from_agency=True)

        # 4. Extract action and Save updated state (no commit yet)
        agency_action = agency.shared_state.get("action")
        conversation.shared_state = agency.shared_state.data 
        db.add(conversation)
        
    except HTTPException as e:
        db.rollback()
        raise e
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing message for {conversation_id}: {e}", exc_info=True)
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error processing message: {str(e)}")

    # Publish to Redis AFTER successful commit
    try:
        if user_message_db:
            await publish_message_to_redis(conversation_id, message_repo.to_dto(user_message_db))
        if ai_message_db:
            await publish_message_to_redis(conversation_id, message_repo.to_dto(ai_message_db))
            
        if agency_action and agency_action.get("action-type") == "keywords_ready":
            pass

    except Exception as pub_e:
        logger.error(f"Failed to publish message(s) to Redis for conv {conversation_id}: {pub_e}")

    response_payload = {
        "response": agency_response_content,
        "is_from_agency": True
    }
    if agency_action:
        response_payload["action"] = agency_action
        
    return response_payload

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
    - Use order='asc' to get messages in chronological order (oldest first)
    - Use order='desc' to get messages in reverse chronological order (newest first)
    - Set limit=0 to get all messages (no limit)
    - Use offset to skip messages for pagination
    """
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} accessing messages for conversation {conversation_id}")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

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

    # Read state directly from DB for response context if needed
    latest_action = conversation.shared_state.get("action") if conversation and conversation.shared_state else None

    keyword_tables = conversation.shared_state.get("keywords_output", None)
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
async def get_user_conversations(
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
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

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

    # Lock the conversation row for the duration of this transaction
    conversation = conversation_repo.get_by_id_for_update(conversation_id)
    
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

@app.delete("/messages/{message_id}", status_code=status.HTTP_204_NO_CONTENT, tags=["Chat"])
async def delete_message_endpoint(
    message_id: int,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    """Deletes a specific message."""
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.email} attempting to delete message {message_id}")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )

    message_repo = MessageRepository(db)
    message = message_repo.get_by_id(message_id)

    if not message:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Message not found"
        )

    # Permission Check: Only allow sender to delete their own message
    # Add admin check here if needed (e.g., if current_user.is_admin:)
    if message.sender_email != current_user.email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to delete this message"
        )

    if message_repo.delete(message_id):
        logger.info(f"Message {message_id} deleted successfully by user {current_user.email}")
        # Return No Content on success
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    else:
        # This case indicates the message was found but deletion failed somehow
        logger.error(f"Failed to delete message {message_id} even though it was found.")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete message"
        )

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print("Access the chat interface at http://localhost:8000")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
