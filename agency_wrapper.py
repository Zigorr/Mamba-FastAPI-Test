"""
Wrapper for agency_swarm Agency to ensure proper isolation of shared state between different agencies.
"""
from typing import Any, Dict, Optional, Callable
from agency_swarm import Agency as BaseAgency
from agency_swarm.util.shared_state import SharedState

class IsolatedSharedState(SharedState):
    """
    A custom SharedState implementation that ensures isolation.
    Each instance has its own conversation_id to avoid any shared references.
    """
    def __init__(self, conversation_id: str, initial_data: Optional[Dict[str, Any]] = None):
        super().__init__()
        self.conversation_id = conversation_id
        # Initialize with any provided data
        if initial_data:
            for key, value in initial_data.items():
                self.set(key, value)
        # Add an identifier to detect which conversation this belongs to
        self.set("__conversation_id", conversation_id)

class Agency(BaseAgency):
    """
    A wrapper around the agency_swarm Agency class that ensures proper isolation
    of shared state between different agency instances.
    """
    def __init__(
        self,
        agents,
        shared_instructions: Optional[str] = None,
        shared_state: Optional[Dict[str, Any]] = None,
        threads_callbacks: Optional[Dict[str, Callable]] = None,
        settings_callbacks: Optional[Dict[str, Callable]] = None,
        conversation_id: str = "default"
    ):
        # Create isolated shared state for this agency instance
        isolated_shared_state = IsolatedSharedState(conversation_id, shared_state)
        
        # Initialize the base Agency with our isolated shared state
        super().__init__(
            agents,  # First positional argument - should be the agents list
            shared_instructions=shared_instructions,
            threads_callbacks=threads_callbacks,
            settings_callbacks=settings_callbacks
        )
        
        # Replace the shared_state with our isolated version
        self.shared_state = isolated_shared_state
        self.conversation_id = conversation_id
        
        # Also ensure all agents and tools use this isolated shared state
        self._update_agent_shared_states()
    
    def _update_agent_shared_states(self):
        """
        Update all agents and their tools to use our isolated shared state.
        """
        try:
            # Check for private __agents attribute (could be dict or otherwise)
            if hasattr(self, '_BaseAgency__agents'):
                private_agents = self._BaseAgency__agents
                if isinstance(private_agents, dict):
                    for agent_name, agent in private_agents.items():
                        self._update_agent_shared_state(agent)
                elif isinstance(private_agents, list):
                    for agent in private_agents:
                        self._update_agent_shared_state(agent)
            
            # Check for agent_map attribute
            if hasattr(self, 'agent_map'):
                agent_map = self.agent_map
                if isinstance(agent_map, dict):
                    for agent_name, agent in agent_map.items():
                        self._update_agent_shared_state(agent)
            
            # Direct agents attribute
            if hasattr(self, 'agents'):
                agents = self.agents
                if isinstance(agents, list):
                    for agent in agents:
                        self._update_agent_shared_state(agent)
                elif isinstance(agents, dict):
                    for agent_name, agent in agents.items():
                        self._update_agent_shared_state(agent)
        except Exception:
            pass
    
    def _update_agent_shared_state(self, agent):
        """Helper method to update a single agent's shared state"""
        try:
            # Set the shared state for the agent
            agent._shared_state = self.shared_state
            
            # Set the shared state for all tools
            if hasattr(agent, 'tools'):
                for tool in agent.tools:
                    if hasattr(tool, '_shared_state'):
                        tool._shared_state = self.shared_state
        except Exception:
            pass
    
    def get_completion(self, message: str, **kwargs) -> str:
        """
        Override get_completion to ensure shared state isolation is maintained.
        """
        # Ensure shared state is still properly isolated before processing
        self._update_agent_shared_states()
        return super().get_completion(message, **kwargs) 