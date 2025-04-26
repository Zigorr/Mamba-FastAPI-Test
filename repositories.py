from typing import List, Optional, Dict, Any, Type, TypeVar, Generic
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, desc
import datetime
import uuid

from models import User, Conversation, Message, UserSession, conversation_participants
from dto import (
    UserDto, CreateUserDto, 
    ConversationDto, CreateConversationDto,
    MessageDto, SendMessageDto,
    UserSessionDto
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
    
    def get_by_username(self, username: str) -> Optional[User]:
        """Get user by username."""
        return self.db.query(User).filter(User.username == username).first()
    
    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email."""
        return self.db.query(User).filter(User.email == email).first()
    
    def create_from_dto(self, user_dto: CreateUserDto, hashed_password: str) -> User:
        """Create a new user from DTO."""
        # Create a dictionary from the DTO
        user_dict = {
            "username": user_dto.username,
            "first_name": user_dto.first_name,
            "last_name": user_dto.last_name,
            "email": user_dto.email,
            "password": hashed_password
        }
        
        # Use the base create method with the dictionary
        return self.create(user_dict)
    
    def to_dto(self, user: User) -> UserDto:
        """Convert User model to UserDto."""
        return UserDto(
            username=user.username,
            first_name=user.first_name,
            last_name=user.last_name,
            email=user.email
        )

class ConversationRepository(BaseRepository[Conversation]):
    """Repository for Conversation entity."""
    
    def __init__(self, db: Session):
        super().__init__(db, Conversation)
    
    def get_by_id(self, conversation_id: str) -> Optional[Conversation]:
        """Get conversation by ID."""
        return self.db.query(Conversation).filter(Conversation.id == conversation_id).first()
    
    def get_for_user(self, username: str) -> List[Conversation]:
        """Get all conversations a user is part of."""
        user = self.db.query(User).filter(User.username == username).first()
        if not user:
            return []
        return user.conversations
    
    def create_from_dto(self, dto: CreateConversationDto, creator_username: str) -> Conversation:
        """Create a new conversation from DTO."""
        # Generate ID if not provided
        conversation_id = f"conv-{uuid.uuid4()}"
        
        # Create conversation
        db_conversation = Conversation(
            id=conversation_id,
            name=dto.name
        )
        self.db.add(db_conversation)
        
        # Ensure creator is in the participants list
        participants = dto.participants.copy()
        if creator_username not in participants:
            participants.append(creator_username)
        
        # Add participants
        for username in participants:
            user = self.db.query(User).filter(User.username == username).first()
            if user:
                db_conversation.participants.append(user)
        
        # Commit changes
        self.db.commit()
        self.db.refresh(db_conversation)
        
        return db_conversation
    
    def add_participant(self, conversation_id: str, username: str) -> bool:
        """Add a user to a conversation."""
        conversation = self.get_by_id(conversation_id)
        user = self.db.query(User).filter(User.username == username).first()
        
        if not conversation or not user:
            return False
        
        # Check if already a participant
        for participant in conversation.participants:
            if participant.username == username:
                return True  # Already a participant
        
        # Add to conversation
        conversation.participants.append(user)
        self.db.commit()
        
        return True
    
    def remove_participant(self, conversation_id: str, username: str) -> bool:
        """Remove a user from a conversation."""
        conversation = self.get_by_id(conversation_id)
        if not conversation:
            return False
        
        # Find the user in participants
        for participant in conversation.participants:
            if participant.username == username:
                conversation.participants.remove(participant)
                self.db.commit()
                return True
        
        return False  # User not in conversation
    
    def to_dto(self, conversation: Conversation) -> ConversationDto:
        """Convert Conversation model to ConversationDto."""
        return ConversationDto.from_db_model(conversation)

class MessageRepository(BaseRepository[Message]):
    """Repository for Message entity."""
    
    def __init__(self, db: Session):
        super().__init__(db, Message)
    
    def get_for_conversation(self, conversation_id: str, limit: int = 50, offset: int = 0) -> List[Message]:
        """Get messages for a conversation with pagination."""
        return self.db.query(Message).filter(
            Message.conversation_id == conversation_id
        ).order_by(desc(Message.timestamp)).offset(offset).limit(limit).all()
    
    def create_from_dto(self, dto: SendMessageDto, sender_username: str, is_from_agency: bool = False) -> Message:
        """Create a message from DTO."""
        message = Message(
            content=dto.content,
            conversation_id=dto.conversation_id,
            sender_username=sender_username,
            is_from_agency=is_from_agency
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def create_system_message(self, conversation_id: str, content: str) -> Message:
        """Create a system message."""
        message = Message(
            content=content,
            conversation_id=conversation_id,
            sender_username="System",
            is_from_agency=True
        )
        self.db.add(message)
        self.db.commit()
        self.db.refresh(message)
        return message
    
    def to_dto(self, message: Message) -> MessageDto:
        """Convert Message model to MessageDto."""
        return MessageDto.from_db_model(message)

class UserSessionRepository(BaseRepository[UserSession]):
    """Repository for UserSession entity."""
    
    def __init__(self, db: Session):
        super().__init__(db, UserSession)
    
    def get_active_session(self, username: str, conversation_id: str) -> Optional[UserSession]:
        """Get active session for a user in a conversation."""
        return self.db.query(UserSession).filter(
            and_(
                UserSession.user_username == username,
                UserSession.conversation_id == conversation_id,
                UserSession.is_active == True
            )
        ).first()
    
    def get_active_sessions_for_conversation(self, conversation_id: str) -> List[UserSession]:
        """Get all active sessions for a conversation."""
        return self.db.query(UserSession).filter(
            and_(
                UserSession.conversation_id == conversation_id,
                UserSession.is_active == True
            )
        ).all()
    
    def create_or_activate_session(self, username: str, conversation_id: str) -> UserSession:
        """Create or activate a user session."""
        # Check for existing inactive session
        session = self.db.query(UserSession).filter(
            and_(
                UserSession.user_username == username,
                UserSession.conversation_id == conversation_id,
                UserSession.is_active == False
            )
        ).first()
        
        if session:
            # Reactivate existing session
            session.is_active = True
            session.connected_at = datetime.datetime.utcnow()
            session.disconnected_at = None
        else:
            # Check if there's already an active session
            active_session = self.get_active_session(username, conversation_id)
            if not active_session:
                # Create new session
                session = UserSession(
                    user_username=username,
                    conversation_id=conversation_id,
                    connected_at=datetime.datetime.utcnow(),
                    is_active=True
                )
                self.db.add(session)
            else:
                # Already has active session, just return it
                return active_session
        
        self.db.commit()
        self.db.refresh(session)
        return session
    
    def deactivate_session(self, username: str, conversation_id: str) -> bool:
        """Deactivate a user session."""
        session = self.get_active_session(username, conversation_id)
        if not session:
            return False
        
        session.is_active = False
        session.disconnected_at = datetime.datetime.utcnow()
        self.db.commit()
        return True
    
    def to_dto(self, session: UserSession) -> UserSessionDto:
        """Convert UserSession model to UserSessionDto."""
        return UserSessionDto.from_db_model(session) 