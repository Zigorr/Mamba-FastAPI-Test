from agency_swarm import Agency
from .CEO import CEO
from .Worker import Worker
import logging
from fastapi import HTTPException, status

logger = logging.getLogger(__name__)


def initialize_agency(conversation_id, conversation_repo):
    ceo = CEO()
    worker = Worker()

    agency = Agency(
        [ceo, [ceo, worker]],
        shared_instructions='./ClientManagementAgency/agency_manifesto.md',
        threads_callbacks={
            'load': lambda: conversation_repo.load_threads(conversation_id),
            'save': lambda threads: conversation_repo.save_threads(conversation_id, threads),
        },
        settings_callbacks={
            'load': lambda: conversation_repo.load_settings(conversation_id),
            'save': lambda settings: conversation_repo.save_settings(conversation_id, settings),
        }
    )

    for k, v in conversation_repo.load_shared_state(conversation_id).items():
        agency.shared_state.set(k, v)
    logger.info(f"Created new agency instance for conversation {conversation_id}")
    try:
        conversation_repo.save_shared_state(conversation_id, agency.shared_state.data)
    except Exception as e:
        logger.error(f"Error saving initial state for {conversation_id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initialize conversation state"
        )
    return agency

# Remove the __main__ block if it exists, as agency creation is handled by main.py now
# if __name__ == "__main__":
#    ...
