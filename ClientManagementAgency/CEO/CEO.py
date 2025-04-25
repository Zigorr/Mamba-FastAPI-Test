from agency_swarm import Agent


class CEO(Agent):
    def __init__(self):
        super().__init__(
            name="CEO",
            description="Manages client interaction, task planning, and saving client data.",
            instructions="./instructions.md",
            tools_folder="./tools",
            # Available tools: SaveClientData
        )

    def response_validator(self, message):
        return message
