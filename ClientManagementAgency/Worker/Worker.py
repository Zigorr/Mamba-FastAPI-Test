from agency_swarm import Agent


class Worker(Agent):
    def __init__(self):
        super().__init__(
            name="Worker",
            description="Retrieves client data from shared state when requested.",
            instructions="./instructions.md",
            tools_folder="./tools",
            # Available tools: RecallClientData
        )

    def response_validator(self, message):
        return message
