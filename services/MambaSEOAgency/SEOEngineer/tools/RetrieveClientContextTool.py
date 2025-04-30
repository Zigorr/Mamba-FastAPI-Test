from agency_swarm.tools import BaseTool

class RetrieveClientContextTool(BaseTool):
    """
    A tool to retrieve the client context from the shared state.
    """
    def run(self):
        """
        Main execution method for the RetrieveClientContextTool.
        Retrieves the client context from the shared state and returns it.
        """
        print("Retrieving client context...")
        client_context = self._shared_state.get('client_context', None)
        if client_context:
            return client_context
        else:
            return "No client context found."

