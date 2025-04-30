from agency_swarm import Agent
from dotenv import load_dotenv

# Import the specific tools
from .tools.CollectBusinessInfoTool import CollectBusinessInfoTool
from .tools.BoFuListTool import BoFuListTool
from .tools.ToFuListTool import ToFuListTool
from .tools.RetrieveClientContextTool import RetrieveClientContextTool
#from .tools.DisplayKeywordsTool import DisplayKeywordsTool

# Load environment variables, especially OPENAI_API_KEY
load_dotenv("../.env") # Load .env from the agency root directory

class SEOEngineer(Agent):
    def __init__(self):
        super().__init__(
            name="SEOEngineer",
            description="Collects business information via a custom UI form, generates BoFu keywords, and displays them.",
            instructions="./instructions.md", # Path to the instructions file
            # Explicitly list the tools the agent can use
            tools=[
                CollectBusinessInfoTool,
                BoFuListTool,
                ToFuListTool,
                RetrieveClientContextTool
                #DisplayKeywordsTool
            ],
            tools_folder="./tools",
            temperature=0.2,
            max_prompt_tokens=25000,
            model="o3-mini-2025-01-31"
        )

    # If you needed to preload tools like CodeInterpreter or FileSearch:
    # from agency_swarm.tools import CodeInterpreter
    # def __init__(self):
    #     super().__init__(
    #         ...
    #         tools=[CodeInterpreter]
    #     )

    # No response validator needed for this simple agent
    # def response_validator(self, message):
    #     return message
