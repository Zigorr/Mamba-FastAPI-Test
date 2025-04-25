from agency_swarm import Agency
from .CEO import CEO
from .Worker import Worker



def create_agency():
    # Instantiate agents
    ceo = CEO()
    worker = Worker()

    agency = Agency(
        [
            ceo, # User -> CEO
            [ceo, worker], # CEO -> Worker
        ],
        shared_instructions='./agency_manifesto.md'
    )

    return agency

# Remove the __main__ block if it exists, as agency creation is handled by main.py now
# if __name__ == "__main__":
#    ...
