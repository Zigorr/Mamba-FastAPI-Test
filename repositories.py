from typing import List, Optional, Dict, Any, Type, TypeVar, Generic
from sqlalchemy.orm import Session, load_only
from sqlalchemy import and_, or_, desc, select, asc
from sqlalchemy.sql import func
import datetime
import uuid
import pickle

from models import User, Conversation, Message, Project
from dto import (
    UserDto, CreateUserDto, 
    ConversationDto, CreateConversationDto,
    MessageDto, SendMessageDto,
    ProjectDto, CreateProjectDto,
)

T = TypeVar('T')

class BaseRepository(Generic[T]):
    """Base repository with common CRUD operations."""
    
    def __init__(self, db: Session, model: Type[T]):
        self.db = db
        self.model = model
    
    def get_by_id(self, id_value):
        """Get entity by ID."""
        return self.db.query(self.model).get(id_value)
    
    def get_all(self):
        """Get all entities."""
        return self.db.query(self.model).all()
    
    def create(self, dto_dict):
        """Create entity from DTO dictionary."""
        entity = self.model(**dto_dict)
        self.db.add(entity)
        self.db.commit()
        self.db.refresh(entity)
        return entity
    
    def update(self, id_value, dto_dict):
        """Update entity with values from DTO dictionary."""
        entity = self.get_by_id(id_value)
        if not entity:
            return None
        
        for key, value in dto_dict.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        
        self.db.commit()
        self.db.refresh(entity)
        return entity
    
    def delete(self, id_value):
        """Delete entity by ID."""
        entity = self.get_by_id(id_value)
        if entity:
            self.db.delete(entity)
            self.db.commit()
            return True
        return False

class UserRepository(BaseRepository[User]):
    """Repository for User entity."""
    
    def __init__(self, db: Session):
        super().__init__(db, User)
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.db.query(User).filter(User.email == email).first()
    
    def create_from_dto(self, user_data: CreateUserDto, hashed_password: str) -> User:
        """Creates a User from CreateUserDto."""
        db_user = User(
            email=user_data.email,
            first_name=user_data.first_name,
            last_name=user_data.last_name,
            password=hashed_password,
        )
        self.db.add(db_user)
        return db_user
    
    def to_dto(self, user: User) -> UserDto:
        """Convert User model to UserDto."""
        return UserDto(
            email=user.email,
            first_name=user.first_name,
            last_name=user.last_name
        )

class ProjectRepository(BaseRepository[Project]):
    """Repository for Project entity."""
    
    def __init__(self, db: Session):
        super().__init__(db, Project)
    
    def get_by_id(self, project_id: str) -> Optional[Project]:
        """Get project by ID."""
        return self.db.query(Project).filter(Project.id == project_id).first()
    
    def get_for_user(self, email: str) -> List[Project]:
        """Get all projects for a specific user."""
        return self.db.query(Project).filter(Project.user_email == email).all()
    
    def create_from_dto(self, dto: CreateProjectDto, user_email: str) -> Project:
        """Create a new project from DTO."""
        # Generate ID if not provided
        project_id = f"proj-{uuid.uuid4()}"
        
        # Create project
        db_project = Project(
            id=project_id,
            name=dto.name,
            website_url=dto.website_url,
            project_data=dto.project_data or {},
            user_email=user_email  # Set the owner of the project
        )
        self.db.add(db_project)
        
        # Commit changes
        self.db.commit()
        self.db.refresh(db_project)
        
        return db_project
    
    def to_dto(self, project: Project) -> ProjectDto:
        """Convert Project model to ProjectDto."""
        return ProjectDto(
            id=project.id,
            name=project.name,
            website_url=project.website_url,
            project_data=project.project_data,
            user_email=project.user_email
        )
    
    def update_project_data(self, project_id: str, project_data: Dict[str, Any]) -> Optional[Project]:
        """Update the project_data field of a project."""
        project = self.get_by_id(project_id)
        if not project:
            return None
            
        project.project_data = project_data
        self.db.commit()
        self.db.refresh(project)
        return project

class ConversationRepository(BaseRepository[Conversation]):
    """Repository for Conversation entity."""
    
    def __init__(self, db: Session):
        super().__init__(db, Conversation)
    
    def get_by_id(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
    
    def get_for_user(self, email: str, limit: int = 50, offset: int = 0, ascending: bool = False, project_id: Optional[str] = None) -> List[Conversation]:
        """
        Get conversations owned by a user with pagination.
        
        Args:
            email: The user's email
            limit: Maximum number of conversations (0 for all)
            offset: Number of conversations to skip
            ascending: If True, order by updated_at ascending (oldest first), 
                      otherwise descending (newest first)
            project_id: Optional filter for conversations belonging to a specific project
        
        Returns:
            List of conversations, with pinned conversations first, then sorted by updated_at
        """
        # Base query for user's conversations
        query = self.db.query(Conversation).filter(
            Conversation.user_email == email
        )
        
        # Filter by project if specified
        if project_id:
            query = query.filter(Conversation.project_id == project_id)
        
        # Sort by is_pinned (True first) and then by updated_at
        if ascending:
            query = query.order_by(Conversation.is_pinned.desc(), Conversation.updated_at.asc())
        else:
            query = query.order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
        
        # Apply offset if specified
        if offset > 0:
            query = query.offset(offset)
        
        # Apply limit if specified (non-zero)
        if limit > 0:
            query = query.limit(limit)
            
        return query.all()
    
    def get_for_project(self, project_id: str, limit: int = 50, offset: int = 0, ascending: bool = False) -> List[Conversation]:
        """
        Get conversations for a specific project with pagination.
        
        Args:
            project_id: The project ID
            limit: Maximum number of conversations (0 for all)
            offset: Number of conversations to skip
            ascending: If True, order by updated_at ascending (oldest first), 
                      otherwise descending (newest first)
        
        Returns:
            List of conversations, with pinned conversations first, then sorted by updated_at
        """
        # Base query for project's conversations
        query = self.db.query(Conversation).filter(
            Conversation.project_id == project_id
        )
        
        # Sort by is_pinned (True first) and then by updated_at
        if ascending:
            query = query.order_by(Conversation.is_pinned.desc(), Conversation.updated_at.asc())
        else:
            query = query.order_by(Conversation.is_pinned.desc(), Conversation.updated_at.desc())
        
        # Apply offset if specified
        if offset > 0:
            query = query.offset(offset)
        
        # Apply limit if specified (non-zero)
        if limit > 0:
            query = query.limit(limit)
            
        return query.all()
    
    def create_from_dto(self, dto: CreateConversationDto, creator_email: str) -> Conversation:
        """Create a new conversation from DTO."""
        # Generate ID if not provided
        conversation_id = f"conv-{uuid.uuid4()}"
        
        # Convert to DB dict
        db_dict = dto.to_db_dict(creator_email)
        
        # Create conversation
        db_conversation = Conversation(
            id=conversation_id,
            **db_dict
        )
        self.db.add(db_conversation)
        
        # Commit changes
        self.db.commit()
        self.db.refresh(db_conversation)
        
        return db_conversation
    
    def to_dto(self, conversation: Conversation) -> ConversationDto:
        """Convert Conversation model to ConversationDto."""
        return ConversationDto(
            id=conversation.id,
            name=conversation.name,
            user_email=conversation.user_email,
            project_id=conversation.project_id,
            shared_state=conversation.shared_state,
            threads=conversation.threads,
            settings=conversation.settings,
            is_pinned=conversation.is_pinned
        )
    
    def _update_project_timestamp(self, conversation_id: str):
        """Helper method to update the project's updated_at timestamp when a conversation is updated."""
        conversation = self.get_by_id(conversation_id)
        if conversation and conversation.project_id:
            self.db.query(Project).filter(Project.id == conversation.project_id).update(
                {Project.updated_at: func.now()}
            )
            self.db.commit()

    def update(self, id_value, dto_dict):
        """Update entity with values from DTO dictionary."""
        entity = self.get_by_id(id_value)
        if not entity:
            return None
        
        for key, value in dto_dict.items():
            if hasattr(entity, key):
                setattr(entity, key, value)
        
        self.db.commit()
        self.db.refresh(entity)
        self._update_project_timestamp(id_value)
        return entity
    
    def load_threads(self, conversation_id: str) -> Optional[dict]:
        """Load only the 'threads' field of a conversation."""
        stmt = select(Conversation.threads).filter(Conversation.id == conversation_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        return result

    def save_threads(self, conversation_id: str, threads: dict):
        """Save only the 'threads' field of a conversation."""
        self.db.query(Conversation).filter(Conversation.id == conversation_id).update({Conversation.threads: threads, Conversation.updated_at: func.now()})
        self.db.commit()
        self._update_project_timestamp(conversation_id)

    def load_settings(self, conversation_id: str) -> Optional[list]: # Assuming settings is a list
        """Load only the 'settings' field of a conversation."""
        stmt = select(Conversation.settings).filter(Conversation.id == conversation_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        return result

    def save_settings(self, conversation_id: str, settings: list):
        """Save only the 'settings' field of a conversation."""
        self.db.query(Conversation).filter(Conversation.id == conversation_id).update({Conversation.settings: settings, Conversation.updated_at: func.now()})
        self.db.commit()
        self._update_project_timestamp(conversation_id)

    def load_shared_state(self, conversation_id: str) -> Optional[dict]:
        """Load only the 'shared_state' field of a conversation."""
        stmt = select(Conversation.shared_state).filter(Conversation.id == conversation_id)
        result = self.db.execute(stmt).scalar_one_or_none()
        return result

    def save_shared_state(self, conversation_id: str, shared_state: dict):
        """Save only the 'shared_state' field of a conversation."""
        self.db.query(Conversation).filter(Conversation.id == conversation_id).update({Conversation.shared_state: shared_state, Conversation.updated_at: func.now()})
        self.db.commit()
        self._update_project_timestamp(conversation_id)

    def update_conversation(self, conversation_id: str) -> Optional[Conversation]:
        """Manually update the `updated_at` timestamp for a conversation."""
        updated = self.db.query(Conversation).filter(
            Conversation.id == conversation_id
        ).update(
            {Conversation.updated_at: func.now()}
        )
        if updated:
            self.db.commit()
            self._update_project_timestamp(conversation_id)
            return self.get_by_id(conversation_id)
        return None

    def delete_conversation(self, conversation_id: str) -> bool:
        """Deletes a conversation and its associated messages (via cascade)."""
        conversation = self.get_by_id(conversation_id)
        if conversation:
            self.db.delete(conversation)
            self.db.commit()
            return True
        return False

    def toggle_pin(self, conversation_id: str) -> Optional[Conversation]:
        """Toggle the pinned status of a conversation."""
        conversation = self.get_by_id(conversation_id)
        if not conversation:
            return None
        
        # Toggle the is_pinned status and update timestamp
        self.db.query(Conversation).filter(Conversation.id == conversation_id).update({
            Conversation.is_pinned: not conversation.is_pinned,
            Conversation.updated_at: func.now()
        })
        self.db.commit()
        self._update_project_timestamp(conversation_id)
        return self.get_by_id(conversation_id)

class MessageRepository(BaseRepository[Message]):
    """Repository for Message entity."""
    
    def __init__(self, db: Session):
        super().__init__(db, Message)
    
    def get_for_conversation(self, conversation_id: str, limit: int = 50, offset: int = 0) -> List[Message]:
        """Get messages for a conversation with pagination."""
        # Use select() for better query control
        query = select(Message).where(
            Message.conversation_id == conversation_id
        ).order_by(desc(Message.timestamp)).offset(offset).limit(limit)
        
        # Execute with connection for better performance
        result = self.db.execute(query)
        return result.scalars().all()
    
    def get_conversation_history(self, conversation_id: str) -> List[Message]:
        """Get all messages for a conversation in chronological order (oldest first)."""
        query = select(Message).where(
            Message.conversation_id == conversation_id
        ).order_by(asc(Message.timestamp))
        
        result = self.db.execute(query)
        return result.scalars().all()
    
    def get_messages_flexible(self, conversation_id: str, limit: int = 50, offset: int = 0, ascending: bool = False) -> List[Message]:
        """
        Get messages for a conversation with flexible options.
        
        Args:
            conversation_id: The ID of the conversation
            limit: Maximum number of messages to return (0 for all messages)
            offset: Number of messages to skip
            ascending: If True, order by timestamp ascending (oldest first), otherwise descending (newest first)
            
        Returns:
            List of messages
        """
        # Build the base query
        query = select(Message).where(Message.conversation_id == conversation_id)
        
        # Add ordering
        if ascending:
            query = query.order_by(asc(Message.timestamp))
        else:
            query = query.order_by(desc(Message.timestamp))
        
        # Add offset
        if offset > 0:
            query = query.offset(offset)
        
        # Add limit (if not zero)
        if limit > 0:
            query = query.limit(limit)
        
        # Execute the query
        result = self.db.execute(query)
        return result.scalars().all()
    
    def count_for_conversation(self, conversation_id: str) -> int:
        """Get the total count of messages in a conversation efficiently."""
        # Use func.count() for an efficient database count query
        query = select(func.count(Message.id)).where(Message.conversation_id == conversation_id)
        count = self.db.execute(query).scalar_one_or_none()
        return count if count is not None else 0
    
    def create_from_dto(self, dto: SendMessageDto, sender_email: str, is_from_agency: bool = False) -> Message:
        """Create a message from DTO."""
        message = Message(
            content=dto.content,
            conversation_id=dto.conversation_id,
            sender_email=sender_email,
            is_from_agency=is_from_agency
        )
        conversation_repo = ConversationRepository(self.db)
        conversation_repo.update_conversation(dto.conversation_id)
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def create_system_message(self, conversation_id: str, content: str, is_from_agency: bool = True) -> Message:
        """Create a system message."""
        message = Message(
            content=content,
            conversation_id=conversation_id,
            sender_email=None,
            is_from_agency=is_from_agency
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def to_dto(self, message: Message) -> MessageDto:
        """Convert Message model to MessageDto."""
        return MessageDto.from_db_model(message)
    
    def bulk_create_messages(self, messages_data: List[Dict[str, Any]]) -> List[Message]:
        """Create multiple messages in a single database transaction."""
        messages = [Message(**data) for data in messages_data]
        
        # Add all messages in one go
        self.db.add_all(messages)
        
        # Commit the transaction
        self.db.commit()
        
        return messages
