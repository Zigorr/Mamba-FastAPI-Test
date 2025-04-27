from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Boolean, Integer
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from database import Base
import datetime

class User(Base):
    __tablename__ = "users"

    username = Column(String, primary_key=True, index=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String, unique=True, index=True)
    password = Column(String)
    # Relationships
    conversations = relationship("Conversation", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="sender")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    # Foreign key to user
    user_username = Column(String, ForeignKey("users.username"), nullable=False)
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=func.now())
    is_from_agency = Column(Boolean, default=False)
    # Foreign keys
    conversation_id = Column(String, ForeignKey("conversations.id"), index=True)
    sender_username = Column(String, ForeignKey("users.username"))
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="messages")
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())

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