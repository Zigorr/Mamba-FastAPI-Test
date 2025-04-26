import pickle
import logging
import threading
import state
from contextlib import contextmanager

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# A dictionary of locks for agency operations
agency_locks = {}

@contextmanager
def conversation_lock(conversation_id: str):
    """Context manager for thread-safe access to conversation data."""
    lock = state.get_conversation_lock(conversation_id)
    lock.acquire()
    try:
        yield
    finally:
        lock.release()

@contextmanager
def agency_lock(conversation_id: str):
    """Context manager for thread-safe access to agency instances."""
    if conversation_id not in agency_locks:
        agency_locks[conversation_id] = threading.RLock()
    
    lock = agency_locks[conversation_id]
    lock.acquire()
    try:
        yield
    finally:
        lock.release()

def load_threads(conversation_id):
    """Load thread data for a conversation (thread-safe)."""
    with conversation_lock(conversation_id):
        return pickle.loads(state.threads.get(conversation_id, pickle.dumps({})))

def save_threads(conversation_id: str, threads: dict):
    """Save thread data for a conversation (thread-safe)."""
    with conversation_lock(conversation_id):
        state.threads[conversation_id] = pickle.dumps(threads)

def load_settings(conversation_id: str):
    """Load settings for a conversation (thread-safe)."""
    with conversation_lock(conversation_id):
        return pickle.loads(state.settings.get(conversation_id, pickle.dumps([])))

def save_settings(conversation_id: str, settings: list):
    """Save settings for a conversation (thread-safe)."""
    with conversation_lock(conversation_id):
        state.settings[conversation_id] = pickle.dumps(settings)

def load_shared_state(conversation_id: str):
    """Load shared state for a conversation (thread-safe)."""
    with conversation_lock(conversation_id):
        try:
            # Initialize the shared state if it doesn't exist for this conversation
            if conversation_id not in state.shared_states:
                state.shared_states[conversation_id] = {}
                
            shared_state = state.shared_states.get(conversation_id, {}).copy()  # Create a copy to avoid reference issues
            
            # Check if we have a direct client name stored
            if conversation_id in state.client_names:
                # Make sure the client name is also in the shared state
                client_name = state.client_names.get(conversation_id)
                if client_name and 'client_name' not in shared_state:
                    shared_state['client_name'] = client_name
            
            # Return a fresh copy to avoid any reference issues
            return shared_state
        except Exception as e:
            logger.error(f"Error loading shared state: {e}")
            return {}

def save_shared_state(conversation_id: str, shared_state: dict):
    """Save shared state for a conversation (thread-safe)."""
    with conversation_lock(conversation_id):
        try:
            # Make a deep copy to ensure we don't have reference issues
            state_copy = shared_state.copy() if shared_state else {}
            
            # Store in shared_states for this specific conversation
            state.shared_states[conversation_id] = state_copy
            
            # Make sure the client name is also saved to our direct storage
            if 'client_name' in state_copy:
                # Save client name to direct storage as well
                state.client_names[conversation_id] = state_copy['client_name']
        except Exception as e:
            logger.error(f"Error saving shared state: {e}")

def get_client_name(conversation_id: str):
    """Get the client name for a conversation from any available source."""
    # Try direct client names dictionary first (more reliable)
    if conversation_id in state.client_names:
        return state.client_names[conversation_id]
    
    # Try shared state as fallback
    shared_state = state.shared_states.get(conversation_id, {})
    if 'client_name' in shared_state:
        return shared_state['client_name']
    
    return None

def set_client_name(conversation_id: str, client_name: str):
    """Set the client name in all appropriate locations."""
    with conversation_lock(conversation_id):
        # Set in the direct client names dictionary
        state.client_names[conversation_id] = client_name
        
        # Set in the shared states
        if conversation_id not in state.shared_states:
            state.shared_states[conversation_id] = {}
        
        state.shared_states[conversation_id]['client_name'] = client_name
        
        logger.info(f"Set client name '{client_name}' for conversation {conversation_id}")
        return True 