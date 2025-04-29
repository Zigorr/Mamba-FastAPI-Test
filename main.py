import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query, Header
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv
import asyncio
import logging
import pickle
from typing import Dict
import certifi
from sqlalchemy.orm import Session
from passlib.context import CryptContext

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
from database import get_db, engine, SessionLocal
from models import Base, User
from repositories import ConversationRepository, MessageRepository, UserRepository

# Agency
from ClientManagementAgency.agency import initialize_agency

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
    allow_origins=["*"],  # Allows all origins
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Create database tables
Base.metadata.create_all(bind=engine)



@app.get("/")
async def read_root():
     return {"message": "Welcome to the Mamba FastAPI"}

@app.post("/register", response_model=UserDto, tags=["Authentication"])
async def register_user_endpoint(user_data: CreateUserDto, db=Depends(get_db)):
    """Register a new user."""
    return register_user(user_data, db)

@app.post("/login", tags=["Authentication"])
async def login_for_access_token(login_data: LoginDto, db=Depends(get_db)):
    """Login a user and return an access token."""
    return await login_user(login_data, db)

@app.post("/chat", tags=["Chat"])
async def create_chat(
    request: dict,
    token: str = Depends(get_token_header),
    db: Session = Depends(get_db)
):
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.username} authenticated for new conversation")
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
    conversation = conversation_repo.create_from_dto(
        CreateConversationDto(name=f"Chat with {current_user.username}"),
        creator_username=current_user.username
    )

    logger.info(f"Created new conversation {conversation.id} for user {current_user.username}")

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
        logger.info(f"User {current_user.username} authenticated")
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

    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)  # Create message repository

    # Validate that the conversation belongs to the current user
    conversation = conversation_repo.get_by_id(conversation_id)
    if not conversation:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Conversation not found"
        )
    
    if conversation.user_username != current_user.username:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have access to this conversation"
        )

    logger.info(f"Received message from client {current_user.username} for conversation {conversation_id}: {message}")

    # Save user message to database
    user_message_dto = SendMessageDto(
        conversation_id=conversation_id,
        content=message
    )
    message_repo.create_from_dto(user_message_dto, current_user.username, is_from_agency=False)

    # Initialize or load agency
    agency = initialize_agency(conversation_id, conversation_repo)

    try:
        # Get completion from agency
        response = agency.get_completion(message=message)
        
        # Save updated state
        conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)
        
        # Save AI response to database
        ai_message_dto = SendMessageDto(
            conversation_id=conversation_id,
            content=response
        )
        message_repo.create_from_dto(ai_message_dto, None, is_from_agency=True)
        
        return {"response": response, "is_from_agency": True}
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
    - Use order='asc' to get messages in chronological order (oldest first)
    - Use order='desc' to get messages in reverse chronological order (newest first)
    - Set limit=0 to get all messages (no limit)
    - Use offset to skip messages for pagination
    """
    # Verify token and get current user
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.username} accessing messages for conversation {conversation_id}")
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
    
    if conversation.user_username != current_user.username:
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
    
    return {
        "messages": message_dtos, 
        "conversation_id": conversation_id,
        "total_count": message_repo.count_for_conversation(conversation_id),
        "order": order,
        "limit": limit,
        "offset": offset
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
        logger.info(f"User {current_user.username} retrieving conversations")
    except HTTPException as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Authentication failed: {e.detail}"
        )
    
    # Get conversations for user
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)
    
    conversations = conversation_repo.get_for_user(current_user.username, limit, offset)
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

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print(f"Default user: testuser (no password needed)")
    print("Access the chat interface at http://localhost:8000")
    
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
