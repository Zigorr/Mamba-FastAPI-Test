import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, HTTPException, status, Query
from fastapi.responses import HTMLResponse
from fastapi.security import OAuth2PasswordRequestForm
import os
from dotenv import load_dotenv
import asyncio
import logging
import pickle
from typing import Dict
import certifi

# State and Auth
import state
import auth
from auth import get_current_user, create_access_token

# Agency
from agency_swarm import Agency
from ClientManagementAgency.CEO import CEO
from ClientManagementAgency.Worker import Worker

load_dotenv(override=True)
os.environ["SSL_CERT_FILE"] = certifi.where()

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = FastAPI()

# Simple HTML page for WebSocket client
html = """
<!DOCTYPE html>
<html>
<head><title>Agency Chat</title></head>
<body>
    <h1>WebSocket Chat with Agency</h1>
    <div id="loginSection">
        <h2>Login</h2>
        <form action="" onsubmit="loginUser(event)">
            <label>Username: <input type="text" id="username" autocomplete="off" value="testuser"/></label>
            <button>Login</button>
        </form>
        <div id="loginStatus"></div>
    </div>

    <div id="chatSection" style="display: none;">
        <h2>Chat</h2>
        <div>Token: <span id="tokenDisplay"></span></div>
        <form action="" onsubmit="sendMessage(event)">
            <label>Conversation ID: <input type="text" id="conversationId" autocomplete="off" value="conv-1"/></label><br>
            <label>Message: <input type="text" id="messageText" autocomplete="off"/></label>
            <button>Send</button>
        </form>
        <ul id='messages'></ul>
        <button onclick="disconnectWs()">Disconnect</button>
    </div>

    <script>
        var ws = null;
        var currentToken = null;

        async function loginUser(event) {
            event.preventDefault();
            const username = document.getElementById("username").value;
            const loginStatus = document.getElementById("loginStatus");
            try {
                const response = await fetch('/login', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/x-www-form-urlencoded',
                    },
                    body: `username=${encodeURIComponent(username)}&password=` // Sending dummy password
                });
                if (!response.ok) {
                    const errorData = await response.json();
                    throw new Error(errorData.detail || `Login failed: ${response.statusText}`);
                }
                const data = await response.json();
                currentToken = data.access_token;
                loginStatus.textContent = "Login successful!";
                document.getElementById("tokenDisplay").textContent = currentToken;
                document.getElementById("loginSection").style.display = "none";
                document.getElementById("chatSection").style.display = "block";
            } catch (error) {
                loginStatus.textContent = `Login error: ${error.message}`;
                console.error("Login error:", error);
            }
        }

        function connectWebSocket(conversationId, token) {
            if (ws) {
                ws.close();
            }
            const url = `ws://${window.location.host}/chat/${conversationId}?token=${encodeURIComponent(token)}`;
            console.log(`Connecting to ${url}`);
            ws = new WebSocket(url);
            ws.onopen = function(event) {
                console.log("WebSocket connection established");
                addMessage("System: Connected.");
            };
            ws.onmessage = function(event) {
                addMessage(`Agency: ${event.data}`);
            };
            ws.onerror = function(event) {
                console.error("WebSocket error observed:", event);
                addMessage("System: Error connecting or communicating.");
            };
            ws.onclose = function(event) {
                console.log(`WebSocket connection closed: ${event.code} ${event.reason}`);
                addMessage(`System: Disconnected (${event.code}). ${event.reason}`);
                ws = null;
            };
        }

        function sendMessage(event) {
            event.preventDefault();
            const conversationInput = document.getElementById("conversationId");
            const messageInput = document.getElementById("messageText");
            const conversationId = conversationInput.value;
            
            if (!currentToken) {
                 addMessage("System: Please login first.");
                 return;
            }

            // Only create new connection if we don't have one or if conversation ID changed
            if (!ws || ws.readyState === WebSocket.CLOSED) {
                connectWebSocket(conversationId, currentToken);
                // Wait a moment for connection before sending
                setTimeout(() => {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(messageInput.value);
                        addMessage(`You: ${messageInput.value}`);
                        messageInput.value = '';
                    } else {
                        addMessage("System: Connection not ready. Please try sending again.");
                    }
                }, 500);
            } else if (ws.readyState === WebSocket.OPEN) {
                // If we have an open connection, just send the message
                ws.send(messageInput.value);
                addMessage(`You: ${messageInput.value}`);
                messageInput.value = '';
            } else {
                addMessage("System: WebSocket is not open. State: " + ws.readyState);
            }
        }

        // Add event listener for conversation ID changes
        conversationInput.addEventListener('change', function() {
            const newConversationId = this.value;
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.close();
                addMessage(`System: Switching to conversation ${newConversationId}...`);
            }
        });
        
        function disconnectWs() {
             if (ws) {
                ws.close();
             }
        }

        function addMessage(message) {
            const messages = document.getElementById('messages');
            const messageItem = document.createElement('li');
            messageItem.textContent = message;
            messages.appendChild(messageItem);
            // Scroll to bottom
            messages.scrollTop = messages.scrollHeight;
        }
    </script>
</body>
</html>
"""

def load_threads(conversation_id):
    return pickle.loads(state.threads.get(conversation_id, pickle.dumps({})))

def save_threads(conversation_id: str, threads: dict):
    state.threads[conversation_id] = pickle.dumps(threads)

def load_settings(conversation_id: str):
    return pickle.loads(state.settings.get(conversation_id, pickle.dumps([])))

def save_settings(conversation_id: str, settings: list):
    state.settings[conversation_id] = pickle.dumps(settings)

def load_shared_state(conversation_id: str):
    return state.shared_states.get(conversation_id, {})

def save_shared_state(conversation_id: str, shared_state: dict):
    state.shared_states[conversation_id] = shared_state

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.post("/login")
async def login_for_access_token(form_data: OAuth2PasswordRequestForm = Depends()):
    # Simple login: checks if username exists. No password check.
    user = state.users.get(form_data.username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(data={"sub": user["username"]})
    return {"access_token": access_token, "token_type": "bearer"}

@app.websocket("/chat/{conversation_id}")
async def websocket_endpoint(
    websocket: WebSocket, 
    conversation_id: str,
    token: str = Query(...), # Get token from query param
    # current_user: Dict = Depends(get_current_user) # Apply auth dependency
):
    # Manual token verification for WebSocket
    try:
        current_user = await get_current_user(token=token)
        logger.info(f"User {current_user['username']} authenticated for conversation {conversation_id}")
    except HTTPException as e:
        await websocket.accept() # Accept before closing with code
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason=f"Authentication failed: {e.detail}")
        logger.warning(f"WebSocket authentication failed for conv {conversation_id}: {e.detail}")
        return
    
    await websocket.accept()
    logger.info(f"WebSocket connection accepted for user {current_user['username']} and conversation_id: {conversation_id}")

    agency = None
    # Try to load existing conversation state
    if conversation_id in state.conversations:
        try:
            # pickled_agency = state.conversations[conversation_id]
            ceo = CEO()
            worker = Worker()

            agency = Agency(
                [ceo, [ceo, worker]],
                shared_instructions='./ClientManagementAgency/agency_manifesto.md',
                threads_callbacks={
                    'load': lambda: load_threads(conversation_id),
                    'save': lambda threads: save_threads(conversation_id, threads),
                },
                settings_callbacks={
                    'load': lambda: load_settings(conversation_id),
                    'save': lambda settings: save_settings(conversation_id, settings),
                }
            )

            for k, v in load_shared_state(conversation_id).items():
                agency.shared_state.set(k, v)

            logger.info(f"Loaded existing agency state for conversation {conversation_id}")
        except Exception as e:
            logger.error(f"Error unpickling state for {conversation_id}: {e}. Creating new agency.")
            # Fall through to create new agency

    # If no state or unpickling failed, create a new agency
    if agency is None:
        ceo = CEO()
        worker = Worker()

        agency = Agency(
            [ceo, [ceo, worker]],
            shared_instructions='./ClientManagementAgency/agency_manifesto.md',
            threads_callbacks={
                'load': lambda: load_threads(conversation_id),
                'save': lambda threads: save_threads(conversation_id, threads),
            },
            settings_callbacks={
                'load': lambda: load_settings(conversation_id),
                'save': lambda settings: save_settings(conversation_id, settings),
            }
        )

        for k, v in load_shared_state(conversation_id).items():
            agency.shared_state.set(k, v)
        logger.info(f"Created new agency instance for conversation {conversation_id}")
        # Initial save for new conversations
        try:
            save_shared_state(conversation_id, agency.shared_state.data)
        except Exception as e:
            logger.error(f"Error pickling initial state for {conversation_id}: {e}")
            # Decide how to handle - maybe close connection?
            await websocket.close(code=status.WS_1011_INTERNAL_ERROR, reason="Failed to initialize state")
            return

    # --- Agency Interaction Logic --- 
    async def on_message_callback(msg: str):
        """Callback function to send agency messages to WebSocket client."""
        logger.info(f"Sending message to client {current_user['username']} for conversation {conversation_id}: {msg[:100]}...")
        await websocket.send_text(msg)

    # Start receiving messages from the client
    try:
        while True:
            data = await websocket.receive_text()
            logger.info(f"Received message from client {current_user['username']} for conversation {conversation_id}: {data}")

            # Use agency.get_completion_async for async handling
            # Run the completion and wait for it before pickling the updated state
            async def get_completion_async():
                return agency.get_completion(message=data)

            completion_task = asyncio.create_task(
                get_completion_async()
            )
            
            # Wait for the agency processing to complete for this message
            completion_result = await completion_task
            logger.info(f"Agency processing complete for message in conversation {conversation_id}")

            # Send the completion result back to the client
            await on_message_callback(completion_result)

            # Pickle the updated agency state after completion
            try:
                save_shared_state(conversation_id, agency.shared_state.data)
                logger.info(f"Saved updated agency state for conversation {conversation_id}")
            except Exception as e:
                logger.error(f"Error pickling state for {conversation_id} after message: {e}")
                # Optionally notify client or handle error
                await websocket.send_text(f"System Error: Could not save conversation state.")

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for user {current_user['username']}, conversation_id: {conversation_id}")
        # State is already saved after each message, final save might be redundant
    except Exception as e:
        logger.error(f"Error during WebSocket communication for {conversation_id}: {e}", exc_info=True)
        try:
            await websocket.send_text(f"System Error: {e}")
        except Exception as send_error:
             logger.error(f"Failed to send error message to client for {conversation_id}: {send_error}")
    finally:
        # Final attempt to save state on close/error, might be redundant
        if agency and conversation_id:
             try:
                save_shared_state(conversation_id, agency.shared_state.data)
                logger.info(f"Final state save attempt for conversation {conversation_id} on disconnect/error.")
             except Exception as e:
                logger.error(f"Error during final state pickle for {conversation_id}: {e}")
        logger.info(f"Closing WebSocket connection handler for user {current_user['username']}, conversation_id: {conversation_id}")

if __name__ == "__main__":
    print("Starting FastAPI server...")
    print("Ensure .env file has OPENAI_API_KEY and SECRET_KEY")
    print(f"Default user: testuser (no password needed)")
    print("Access the chat interface at http://localhost:8000")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) 