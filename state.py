import threading
from typing import Dict, Any, Set

# In-memory storage (replace with a real database in production)

# Stores agency data instances keyed by conversation_id
conversations = {}
threads = {}
settings = {}
shared_states = {}

# Client names storage - maps conversation_id to client name
client_names = {}

# Active sessions tracking
# Maps conversation_id to a set of active user connections
active_sessions: Dict[str, Set[str]] = {}

# Conversation locks for thread safety during state updates
conversation_locks: Dict[str, threading.RLock] = {}

# User sessions - tracks which conversations a user is part of
# Key: username, Value: set of conversation_ids
user_sessions: Dict[str, Set[str]] = {}

# Simple user store (replace with secure user management)
# Key: username, Value: user info (e.g., {'username': 'user1'})
# In a real app, you'd store hashed passwords here.
users = {
    "testuser": {"username": "testuser"}, # Example user
    "TheOne1" : {"username": "TheOne1"}
}

def get_conversation_lock(conversation_id: str) -> threading.RLock:
    """Get or create a lock for a specific conversation."""
    if conversation_id not in conversation_locks:
        conversation_locks[conversation_id] = threading.RLock()
    return conversation_locks[conversation_id]

def register_active_session(conversation_id: str, username: str) -> None:
    """Register an active user session for a conversation."""
    # Create the active sessions set if it doesn't exist
    if conversation_id not in active_sessions:
        active_sessions[conversation_id] = set()
    
    # Add user to the active sessions
    active_sessions[conversation_id].add(username)
    
    # Register this conversation in the user's sessions
    if username not in user_sessions:
        user_sessions[username] = set()
    user_sessions[username].add(conversation_id)

def unregister_active_session(conversation_id: str, username: str) -> None:
    """Remove a user session from a conversation."""
    if conversation_id in active_sessions and username in active_sessions[conversation_id]:
        active_sessions[conversation_id].remove(username)
        
        # Clean up empty conversations
        if not active_sessions[conversation_id]:
            del active_sessions[conversation_id]
    
    # Remove from user sessions
    if username in user_sessions and conversation_id in user_sessions[username]:
        user_sessions[username].remove(conversation_id)
        
        # Clean up empty user sessions
        if not user_sessions[username]:
            del user_sessions[username]

def get_active_users(conversation_id: str) -> Set[str]:
    """Get all active users in a conversation."""
    return active_sessions.get(conversation_id, set()).copy()

def get_user_conversations(username: str) -> Set[str]:
    """Get all conversations a user is active in."""
    return user_sessions.get(username, set()).copy() 