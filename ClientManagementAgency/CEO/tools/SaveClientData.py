from agency_swarm.tools import BaseTool
from pydantic import Field
import os
from dotenv import load_dotenv

load_dotenv()

class SaveClientData(BaseTool):
    """
    Saves the client's name to the shared state. This tool should be used
    when the client's name needs to be stored for later retrieval by other agents.
    """
    client_name: str = Field(
        ..., description="The name of the client to be saved."
    )

    def run(self):
        """
        Saves the client name provided in the 'client_name' field to the shared state
        under the key 'client_name'.
        """
        try:
            self._shared_state.set("client_name", self.client_name)
            return f"Successfully saved client name '{self.client_name}' to shared state."
        except Exception as e:
            return f"Error saving client name to shared state: {e}"

if __name__ == "__main__":
    # Test the tool
    from agency_swarm.util.shared_state import SharedState

    # Initialize shared state for testing
    shared_state = SharedState()

    # Create and run the tool
    tool = SaveClientData(client_name="Test Client Inc.", _shared_state=shared_state)
    result = tool.run()
    print(result)

    # Verify the state was set
    retrieved_name = shared_state.get("client_name")
    print(f"Retrieved name from shared state: {retrieved_name}")
    assert retrieved_name == "Test Client Inc." 