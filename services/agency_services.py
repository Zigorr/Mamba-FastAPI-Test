from agency_swarm import Agency
from .MambaSEOAgency.SEOEngineer import SEOEngineer
import logging
from fastapi import HTTPException, status
from cachetools import TTLCache # Changed from LRUCache to TTLCache
from threading import Lock
logger = logging.getLogger(__name__)

# Define a maximum number of agency instances to keep in memory.
# Adjust this based on your 1GB RAM limit and typical Agency instance size.
# Start with a lower number for a 1GB droplet if Agency instances are heavy.
MAX_AGENCY_CACHE_SIZE = 25 # Example: Allows 25 active agencies in memory; adjust as needed
AGENCY_TTL_SECONDS = 60 # Cache agency instances for 60 seconds of inactivity

class ThreadSafeTTLCache:
    def __init__(self, maxsize: int, ttl: int):
        self.cache = TTLCache(maxsize, ttl)
        self.lock = Lock()

    def __getitem__(self, key):
        with self.lock:
            return self.cache[key]

    def __setitem__(self, key, value):
        with self.lock:
            self.cache[key] = value

    def __contains__(self, key):
        with self.lock:
            return key in self.cache

    def __repr__(self):
        with self.lock:
            return repr(self.cache)
        
    def __len__(self):
        with self.lock:
            return len(self.cache)

class AgencyService:
    # Use an LRU cache for agency instances
    agency_cache: ThreadSafeTTLCache = ThreadSafeTTLCache(maxsize=MAX_AGENCY_CACHE_SIZE, ttl=AGENCY_TTL_SECONDS)

    @classmethod
    def initialize_agency(cls, conversation_id: str, conversation_repo):
        # TTLCache automatically handles expiration. 
        # Accessing the item (even just checking for presence via __contains__ or get)
        # does NOT reset its TTL by default with cachetools TTLCache as it does with some other TTL caches.
        # If the item is fetched via __getitem__ (e.g. cls.agency_cache[conversation_id]), it's just returned if not expired.
        # If it's expired, it will raise a KeyError, and we'll reinitialize.
        try:
            agency = cls.agency_cache[conversation_id]
            logger.debug(f"Reusing cached agency for conversation {conversation_id}")
            return agency
        except KeyError: # Happens if not in cache OR if expired
            logger.info(f"Initializing new agency instance for conversation {conversation_id} (cache miss or TTL expired).")
        
        # CRITICAL: Investigate SEOEngineer and Agency for resource loading.
        # If they load heavy models/data not specific to a conversation,
        # those should be loaded ONCE globally or as class-level attributes in those classes.
        # This is more important than instance caching if init is heavy.
        try:
            # Ensure SEOEngineer is lightweight on init or shares heavy resources globally.
            ceo = SEOEngineer()

            agency = Agency(
                [ceo], # Assuming 'agency_members' is the correct param name
                                      # If it's just `[ceo]`, change it back.
                shared_instructions='./MambaSEOAgency/agency_manifesto.md', # Verify this path carefully!
                threads_callbacks={
                    'load': lambda: conversation_repo.load_threads(conversation_id),
                    'save': lambda threads: conversation_repo.save_threads(conversation_id, threads),
                },
                settings_callbacks={
                    'load': lambda: conversation_repo.load_settings(conversation_id),
                    'save': lambda settings: conversation_repo.save_settings(conversation_id, settings),
                }
            )

            # Load initial shared state into the new agency instance
            # Using the optimized load_shared_state from ConversationRepository
            initial_shared_state = conversation_repo.load_shared_state(conversation_id)
            if initial_shared_state is not None:
                for k, v in initial_shared_state.items():
                    agency.shared_state.set(k, v)
            
            # Persist any initial state changes made by Agency creation itself (if any).
            # The agency.shared_state.data might contain initial defaults set by the Agency.
            conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)
            
            cls.agency_cache[conversation_id] = agency
            logger.info(f"Cached new agency instance for conversation {conversation_id}. Cache size: {len(cls.agency_cache)}/{cls.agency_cache.maxsize}")

        except FileNotFoundError as e:
            logger.error(f"Manifesto file not found for agency init: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Agency initialization failed: Manifesto not found at {e.filename}")
        except Exception as e:
            logger.error(f"Error initializing agency or its state for {conversation_id}: {e}", exc_info=True)
            if not isinstance(e, HTTPException):
                 raise HTTPException(
                    status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                    detail=f"Failed to initialize agency or conversation state: {str(e)}"
                )
            else:
                raise e # Re-raise if it's already an HTTPException
        return agency

    # get_completion is called on the agency instance in main.py, not a static/class method here.
    # If get_completion method of the agency_swarm.Agency object is resource-intensive:
    # 1. Ensure any models it uses are loaded efficiently (once if possible within Agency/SEOEngineer).
    # 2. For long-running tasks, consider FastAPI's BackgroundTasks in main.py
    #    to avoid blocking web requests, especially on a 1GB server.

# Remove the __main__ block if it existed
