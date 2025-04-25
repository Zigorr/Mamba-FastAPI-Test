# In-memory storage (replace with a real database in production)

# Stores agency data instances keyed by conversation_id
conversations = {}
threads = {}
settings = {}
shared_states = {}

# Simple user store (replace with secure user management)
# Key: username, Value: user info (e.g., {'username': 'user1'})
# In a real app, you'd store hashed passwords here.
users = {
    "testuser": {"username": "testuser"} # Example user
} 