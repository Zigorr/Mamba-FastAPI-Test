import asyncio
import logging
import re
from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session
from database import SessionLocal
from auth import get_current_user
import state
from state_manager import (
    load_threads, save_threads, 
    load_settings, save_settings, 
    load_shared_state, save_shared_state, 
    conversation_lock, agency_lock,
    get_client_name, set_client_name
)

# Agency
# Using our custom Agency wrapper instead of agency_swarm directly
from agency_wrapper import Agency
from ClientManagementAgency.CEO import CEO
from ClientManagementAgency.Worker import Worker

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Track active WebSocket connections by conversation and user
# Key: (conversation_id, username), Value: WebSocket
active_connections = {}

# Create and cache agency instances
# Key: conversation_id, Value: Agency instance
agency_cache = {}

# Store client names directly if extraction fails
# This is a fallback mechanism
if not hasattr(state, 'client_names'):
    state.client_names = {}

def extract_client_name_from_message(message_text):
    """
    Try to extract a client name from a message.
    Looks for common patterns like "my name is [name]" or "I am [name]".
    """
    # Common patterns for name introduction
    patterns = [
        r"my name is (\w+)",
        r"i am (\w+)",
        r"i'm (\w+)",
        r"call me (\w+)"
    ]
    
    for pattern in patterns:
        matches = re.search(pattern, message_text.lower())
        if matches:
            # Capitalize the first letter of the name
            return matches.group(1).capitalize()
    
    return None

async def broadcast_to_conversation(conversation_id: str, message: str, exclude_user: str = None):
    """Broadcast a message to all users in a conversation except the excluded user."""
    active_users = state.get_active_users(conversation_id)
    
    for username in active_users:
        if username != exclude_user:  # Don't send to the originating user
            connection_key = (conversation_id, username)
            if connection_key in active_connections:
                websocket = active_connections[connection_key]
                try:
                    await websocket.send_text(f"User {exclude_user}: {message}")
                except Exception as e:
                    logger.error(f"Error broadcasting to {username} in {conversation_id}: {e}")

def get_or_create_agency(conversation_id: str):
    """Get an existing agency instance or create a new one."""
    # Use agency_lock to prevent race conditions
    with agency_lock(conversation_id):
        if conversation_id in agency_cache:
            logger.info(f"Returning existing agency for conversation {conversation_id}")
            return agency_cache[conversation_id]
        
        # Create a new agency
        logger.info(f"Creating new agency for conversation {conversation_id}")
        ceo = CEO()
        worker = Worker()

        # Create an initial shared state if we have client name
        initial_shared_state = {}
        client_name = get_client_name(conversation_id)
        if client_name:
            initial_shared_state['client_name'] = client_name
            logger.info(f"Including client_name {client_name} in initial shared state")

        # Use our wrapped Agency with conversation_id to ensure isolation
        agency = Agency(
            agents=[ceo, [ceo, worker]],
            shared_instructions='./ClientManagementAgency/agency_manifesto.md',
            shared_state=initial_shared_state,
            threads_callbacks={
                'load': lambda: load_threads(conversation_id),
                'save': lambda threads: save_threads(conversation_id, threads),
            },
            settings_callbacks={
                'load': lambda: load_settings(conversation_id),
                'save': lambda settings: save_settings(conversation_id, settings),
            },
            conversation_id=conversation_id  # Pass conversation_id to ensure isolation
        )
        
        # Cache the agency instance
        agency_cache[conversation_id] = agency
        
        logger.info(f"Created new agency instance for conversation {conversation_id}")
        return agency

def get_client_name_from_agency(agency):
    """Extract client name directly from agency shared state."""
    if not hasattr(agency, 'shared_state'):
        return None
    
    # Try to get client name from shared_state.data
    try:
        if hasattr(agency.shared_state, 'data'):
            if agency.shared_state.data.get('client_name'):
                return agency.shared_state.data.get('client_name')
    except Exception:
        pass
    
    # Try using get method if available
    try:
        if hasattr(agency.shared_state, 'get'):
            client_name = agency.shared_state.get('client_name')
            if client_name:
                return client_name
    except Exception:
        pass
    
    return None

async def handle_websocket_chat(
    websocket: WebSocket, 
    conversation_id: str,
    token: str = Query(..., description="JWT token for authentication"),
):
    """Handle WebSocket connection for chat functionality."""
    # Manual token verification for WebSocket
    db = SessionLocal()
    current_user = None
    
    try:
        current_user = await get_current_user(token=token, db=db)
        logger.info(f"User {current_user.username} authenticated for conversation {conversation_id}")
    except HTTPException as e:
        await websocket.accept() # Accept before closing with code
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"Authentication failed: {e.detail}")
        logger.warning(f"WebSocket authentication failed for conv {conversation_id}: {e.detail}")
        db.close()
        return
    
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for user {current_user.username} and conversation_id: {conversation_id}")

    # Register active session
    state.register_active_session(conversation_id, current_user.username)
    
    # Store WebSocket connection
    connection_key = (conversation_id, current_user.username)
    active_connections[connection_key] = websocket
    
    # Notify other users of this user joining
    other_users = state.get_active_users(conversation_id)
    other_users_list = ", ".join([user for user in other_users if user != current_user.username])
    if other_users_list:
        await websocket.send_text(f"System: Other users in this conversation: {other_users_list}")
        await broadcast_to_conversation(
            conversation_id, 
            f"has joined the conversation.", 
            exclude_user=current_user.username
        )

    # Get or create an agency for this conversation
    agency = get_or_create_agency(conversation_id)

    # --- Agency Interaction Logic --- 
    async def on_message_callback(msg: str):
        """Callback function to send agency messages to WebSocket client."""
        logger.info(f"Sending message to client {current_user.username} for conversation {conversation_id}: {msg[:100]}...")
        await websocket.send_text(f"Agency: {msg}")
        
        # Broadcast agency's response to all other participants
        for username in state.get_active_users(conversation_id):
            if username != current_user.username:
                other_connection_key = (conversation_id, username)
                if other_connection_key in active_connections:
                    other_websocket = active_connections[other_connection_key]
                    try:
                        await other_websocket.send_text(f"Agency to {current_user.username}: {msg}")
                    except Exception as e:
                        logger.error(f"Error broadcasting agency response to {username}: {e}")

    # Start receiving messages from the client
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from client {current_user.username} for conversation {conversation_id}: {data}")

            # Broadcast message to other users in the conversation
            await broadcast_to_conversation(conversation_id, data, exclude_user=current_user.username)
            
            # Try to extract client name from message as a fallback
            extracted_name = extract_client_name_from_message(data)
            if extracted_name:
                logger.info(f"Extracted client name '{extracted_name}' from message text for conversation {conversation_id}")
                # Store using the state manager function
                set_client_name(conversation_id, extracted_name)

            # Use a separate completion task for this specific conversation
            async def get_completion_async():
                # Ensure the message explicitly includes the conversation context
                formatted_message = f"FROM USER {current_user.username} IN CONVERSATION {conversation_id}: {data}"
                return agency.get_completion(message=formatted_message)

            completion_task = asyncio.create_task(get_completion_async())
            
            # Wait for the agency processing to complete for this message
            completion_result = await completion_task
            logger.info(f"Agency processing complete for message in conversation {conversation_id}")

            # Send the completion result back to the client
            await on_message_callback(completion_result)

            # Save the updated agency state after completion
            try:
                # Create a new shared state dictionary
                updated_shared_state = {}
                
                # Get client name using the direct method from agency
                client_name = get_client_name_from_agency(agency)
                if client_name:
                    updated_shared_state['client_name'] = client_name
                    # Save in state manager too
                    set_client_name(conversation_id, client_name)
                else:
                    # Try to get client name from the state manager
                    client_name = get_client_name(conversation_id)
                    if client_name:
                        updated_shared_state['client_name'] = client_name
                
                # If we have a shared_state attribute, try to copy any data
                if hasattr(agency, 'shared_state') and hasattr(agency.shared_state, 'data'):
                    # Copy all key-value pairs from shared_state_data
                    for key, value in agency.shared_state.data.items():
                        updated_shared_state[key] = value
                
                # Save the updated state
                with agency_lock(conversation_id):
                    save_shared_state(conversation_id, updated_shared_state)
                    
                logger.info(f"Saved updated agency state for conversation {conversation_id}")
            except Exception as e:
                logger.error(f"Error saving state for {conversation_id} after message: {e}")
                # Optionally notify client or handle error
                await websocket.send_text(f"System Error: Could not save conversation state.")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {current_user.username}, conversation_id: {conversation_id}")
    except Exception as e:
        logger.error(f"Error during WebSocket communication for {conversation_id}: {e}", exc_info=True)
        try:
            await websocket.send_text(f"System Error: {e}")
        except Exception as send_error:
            logger.error(f"Failed to send error message to client for {conversation_id}: {send_error}")
    finally:
        # Cleanup
        if current_user:
            # Remove this connection
            if connection_key in active_connections:
                del active_connections[connection_key]
            
            # Unregister from active sessions
            state.unregister_active_session(conversation_id, current_user.username)
            
            # Notify other users about disconnection
            await broadcast_to_conversation(
                conversation_id, 
                f"has left the conversation.", 
                exclude_user=current_user.username
            )
            
            # If no more active users in this conversation, remove from agency cache
            if not state.get_active_users(conversation_id) and conversation_id in agency_cache:
                del agency_cache[conversation_id]
            
            logger.info(f"Closing WebSocket connection handler for user {current_user.username}, conversation_id: {conversation_id}")
        
        db.close() 