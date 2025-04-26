"""
Debug script to test agency_swarm shared state behavior with multiple conversations
"""
import os
from dotenv import load_dotenv
from agency_swarm import Agency
from agency_swarm.util.shared_state import SharedState
from ClientManagementAgency.CEO import CEO
from ClientManagementAgency.Worker import Worker

load_dotenv()

def create_agency(conversation_id):
    """Create a test agency for the given conversation ID"""
    print(f"\n--- Creating agency for conversation {conversation_id} ---")
    ceo = CEO() 
    worker = Worker()
    
    agency = Agency(
        [ceo, [ceo, worker]],
        shared_instructions='./ClientManagementAgency/agency_manifesto.md',
        # No callbacks for this test
    )
    
    print(f"Agency for conv {conversation_id} initialized with shared_state: {agency.shared_state.data}")
    return agency

def test_multi_agency_shared_state():
    """Test multiple agencies with separate shared states"""
    # Create two separate agencies with different conversation IDs
    agency1 = create_agency("conv1")
    agency2 = create_agency("conv2")
    
    # Set client name in agency1
    print("\n--- Setting client name in agency1 ---")
    agency1.shared_state.set("client_name", "Alice")
    print(f"Agency1 shared_state after setting: {agency1.shared_state.data}")
    print(f"Agency2 shared_state check (should be empty): {agency2.shared_state.data}")
    
    # Set client name in agency2 
    print("\n--- Setting client name in agency2 ---")
    agency2.shared_state.set("client_name", "Bob")
    print(f"Agency1 shared_state check (should still be Alice): {agency1.shared_state.data}")
    print(f"Agency2 shared_state after setting: {agency2.shared_state.data}")
    
    # Verify both agencies have separate state
    print("\n--- Final state verification ---")
    print(f"Agency1 client_name: {agency1.shared_state.data.get('client_name')}")
    print(f"Agency2 client_name: {agency2.shared_state.data.get('client_name')}")

if __name__ == "__main__":
    test_multi_agency_shared_state() 