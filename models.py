from sqlalchemy import Column, String, ForeignKey, Table, DateTime, Text, Boolean, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func  # Import func
from database import Base
import datetime

# Association table for many-to-many relationship between users and conversations
conversation_participants = Table(
    "conversation_participants",
    Base.metadata,
    Column("user_username", String, ForeignKey("users.username"), primary_key=True),
    Column("conversation_id", String, ForeignKey("conversations.id"), primary_key=True),
    Column("joined_at", DateTime(timezone=True), server_default=func.now()),
    Column("is_active", Boolean, default=True)
)

class User(Base):
    __tablename__ = "users"

    username = Column(String, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    conversations = relationship(
        "Conversation", 
        secondary=conversation_participants,
        back_populates="participants"
    )
    messages = relationship("Message", back_populates="sender")

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Relationships
    participants = relationship(
        "User", 
        secondary=conversation_participants,
        back_populates="conversations"
    )
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    is_from_agency = Column(Boolean, default=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Foreign keys
    conversation_id = Column(String, ForeignKey("conversations.id"), index=True)
    sender_username = Column(String, ForeignKey("users.username"))
    
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="messages")

class UserSession(Base):
    __tablename__ = "user_sessions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_username = Column(String, ForeignKey("users.username"), index=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), index=True)
    connected_at = Column(DateTime(timezone=True), server_default=func.now())
    disconnected_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())
    
    # Add unique constraint to ensure one active session per user per conversation
    __table_args__ = (
        # No tuple for a single index
    ) 