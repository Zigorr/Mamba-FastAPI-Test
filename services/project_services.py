from api_clients import OpenAIClient, FireCrawlClient
import logging
from sqlalchemy.orm import Session # type: ignore # Add Session import
from repositories import ProjectRepository, ConversationRepository, MessageRepository # Add repo imports
from models import Project, Conversation, Message # Add model imports
from fastapi import HTTPException, status # type: ignore # Add HTTPException
from dto import UpdateProjectSpecificDto, ProjectDto # Import necessary DTOs

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

async def update_project_specific_fields(project_id: str, user_email: str, update_data: UpdateProjectSpecificDto, db: Session) -> ProjectDto:
    """
    Updates specific fields of a project after verifying ownership.
    Handles partial updates based on the provided DTO.
    """
    project_repo = ProjectRepository(db)
    project = project_repo.get_by_id(project_id)

    if not project:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Project not found"
        )
    
    if project.user_email != user_email:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User not authorized to update this project"
        )
    
    # Prepare updates dictionary, excluding None values from the DTO
    updates_dict = update_data.model_dump(exclude_unset=True)
    
    if not updates_dict:
        # If no actual update values were provided, return current state
        logger.info(f"No update values provided for project {project_id} by user {user_email}. Returning current state.")
        return project_repo.to_dto(project)

    try:
        # Apply the updates using the repository method
        updated_project = project_repo.update_specific_fields(project, updates_dict)
        
        # Commit the changes (assuming session management handles commit/rollback on success/failure)
        db.commit()
        db.refresh(updated_project)
        logger.info(f"Project {project_id} updated successfully by user {user_email}. Fields updated: {list(updates_dict.keys())}")
        
        return project_repo.to_dto(updated_project)
    
    except Exception as e:
        db.rollback() # Explicit rollback on error within the service
        logger.error(f"Error updating project {project_id} for user {user_email}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while updating the project: {e}"
        )

# Ensure necessary repository methods exist:
# - ConversationRepository: get_for_project_raw(project_id) -> List[Conversation]
# - ConversationRepository: delete_conversations_by_ids(conversation_ids: List[str])
# - MessageRepository: delete_messages_by_conversation_ids(conversation_ids: List[str])
# - ProjectRepository: delete(project: Project)
