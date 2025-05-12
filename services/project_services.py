from api_clients import OpenAIClient, FireCrawlClient
import logging
from sqlalchemy.orm import Session # type: ignore # Add Session import
from repositories import ProjectRepository, ConversationRepository, MessageRepository # Add repo imports
from models import Project, Conversation, Message # Add model imports
from fastapi import HTTPException, status # type: ignore # Add HTTPException

logger = logging.getLogger(__name__)

def extract_project_data(project_url: str):
    # Get the company summary
    try:
        crawled_data = FireCrawlClient._crawl(project_url)
        company_data = OpenAIClient.extract_company_data(crawled_data)
    except Exception as e:
        logger.error(f"Error extracting project data: {e}")
        raise e;

    return company_data

def generate_project_data(
        project_name: str,
        products_description: str,
        personas_description: str,
        competitors_description: str
    ):
    try:
        # Get the project data
        company_data = OpenAIClient.generate_company_data(products_description, personas_description, competitors_description, project_name)
        return company_data
    except Exception as e:
        logger.error(f"Error generating project data: {e}")
        raise e;

async def delete_project_and_data(project_id: str, user_email: str, db: Session):
    """
    Deletes a project and all associated conversations and messages.
    Ensures the user owns the project before deletion.
    """
    project_repo = ProjectRepository(db)
    conversation_repo = ConversationRepository(db)
    message_repo = MessageRepository(db)

    # Verify project exists and belongs to the user (redundant check, but safe)
    project = project_repo.get_by_id(project_id)
    if not project:
        # Project already deleted or never existed, return successfully (idempotency)
        logger.info(f"Project {project_id} not found during service-level delete for user {user_email}. Assuming already deleted.")
        return # No error, just return

    if project.user_email != user_email:
        # This should ideally be caught by the endpoint, but raise error just in case
        logger.error(f"Authorization error in service: User {user_email} attempted to delete project {project_id} owned by {project.user_email}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not authorized to delete this project"
        )

    try:
        # 1. Get all conversation IDs for the project
        conversation_ids = [conv.id for conv in conversation_repo.get_for_project_raw(project_id)]
        
        if conversation_ids:
            # 2. Delete all messages associated with those conversations
            message_repo.delete_messages_by_conversation_ids(conversation_ids)
            logger.info(f"Deleted messages for conversations associated with project {project_id}")

            # 3. Delete all conversations associated with the project
            conversation_repo.delete_conversations_by_ids(conversation_ids)
            logger.info(f"Deleted conversations associated with project {project_id}")

        # 4. Delete the project itself
        project_repo.delete(project)
        logger.info(f"Deleted project {project_id} successfully for user {user_email}")

        # Commit the transaction
        # db.commit() # The endpoint context manager should handle commit/rollback

    except Exception as e:
        # db.rollback() # Endpoint context manager handles rollback
        logger.error(f"Error during deletion of project {project_id} for user {user_email}: {e}", exc_info=True)
        # Re-raise a generic server error to be caught by the endpoint
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while deleting project data: {e}"
        )

# Ensure necessary repository methods exist:
# - ConversationRepository: get_for_project_raw(project_id) -> List[Conversation]
# - ConversationRepository: delete_conversations_by_ids(conversation_ids: List[str])
# - MessageRepository: delete_messages_by_conversation_ids(conversation_ids: List[str])
# - ProjectRepository: delete(project: Project)
