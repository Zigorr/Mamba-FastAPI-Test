from agency_swarm.tools import BaseTool
from pydantic import Field
from dotenv import load_dotenv

# load_dotenv(override=True)

class CollectBusinessInfoTool(BaseTool):
    """
    This tool is used to collect business information from the user.
    It triggers the React UI to display the form.
    """

    # No fields needed as this tool just triggers the UI interaction

    def run(self):
        """
        Prompts the React UI to display the form.
        """
        try:
            # 1. Tell the UI to show the form
            self._shared_state.set('action', 'collect_business_info')
            return "Successfully triggered the UI to display the form. Prompt the user to fill out the form and submit."
        except Exception as e:
            return f"An unexpected error occurred: {e}"
