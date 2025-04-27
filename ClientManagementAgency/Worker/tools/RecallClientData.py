from agency_swarm.tools import BaseTool
from pydantic import Field
import os
from dotenv import load_dotenv

load_dotenv()

class RecallClientData(BaseTool):
    """
    Recalls the client's name from the shared state. Use this tool when you need
    to retrieve the client name previously saved by another agent.
    """

    def run(self):
        """
        Retrieves the client name from the shared state using the key 'client_name'.
        Returns the client name if found, or a message indicating it was not found.
        """
        try:
            client_name = self._shared_state.get("client_name")
            if client_name:
                print(f"Internal Tool Message: Retrieved client name: '{client_name}'")
                return f"Retrieved client name: '{client_name}'"
            else:
                print(f"Internal Tool Message: Client name not found in shared state.")
                return "Client name not found in shared state."
        except Exception as e:
            return f"Error retrieving client name from shared state: {e}"

if __name__ == "__main__":
    # Test the tool
    from agency_swarm.util.shared_state import SharedState

    # Initialize shared state for testing
    shared_state = SharedState()

    # Test case 1: Name not set
    print("Test Case 1: Name not set")
    tool_recall_1 = RecallClientData(_shared_state=shared_state)
    result_1 = tool_recall_1.run()
    print(result_1)
    assert "not found" in result_1

    # Set a value in shared state (simulating SaveClientData)
    shared_state.set("client_name", "Another Test Client")
    print("\nShared state set: client_name='Another Test Client'")

    # Test case 2: Name is set
    print("\nTest Case 2: Name is set")
    tool_recall_2 = RecallClientData(_shared_state=shared_state)
    result_2 = tool_recall_2.run()
    print(result_2)
    assert "Another Test Client" in result_2 