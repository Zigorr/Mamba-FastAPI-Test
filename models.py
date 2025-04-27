from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Boolean, Integer, text, JSON, Index
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
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
    
    # Create compound index for frequently searched fields
    __table_args__ = (
        Index('idx_user_name_email', 'first_name', 'last_name', 'email'),
    )

class Conversation(Base):
    __tablename__ = "conversations"
    
    id = Column(String, primary_key=True, index=True)
    name = Column(String)
    # Foreign key to user
    user_username = Column(String, ForeignKey("users.username"), nullable=False)
    # New JSON fields for state storage
    shared_state = Column(JSON, nullable=True, default={})
    threads = Column(JSON, nullable=True, default={})
    settings = Column(JSON, nullable=True, default=[])
    # Relationships
    user = relationship("User", back_populates="conversations")
    messages = relationship("Message", back_populates="conversation", cascade="all, delete-orphan")
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
    
    # Add index to improve query performance on frequently filtered fields
    __table_args__ = (
        Index('idx_conv_user_updated', 'user_username', 'updated_at'),
    )

class Message(Base):
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    content = Column(Text)
    timestamp = Column(DateTime(timezone=True), server_default=text("NOW()"))
    is_from_agency = Column(Boolean, default=False)
    # Foreign keys
    conversation_id = Column(String, ForeignKey("conversations.id"), index=True)
    sender_username = Column(String, ForeignKey("users.username"))
    # Relationships
    conversation = relationship("Conversation", back_populates="messages")
    sender = relationship("User", back_populates="messages")
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
    
    # Add compound index for message filtering and sorting
    __table_args__ = (
        Index('idx_message_conv_timestamp', 'conversation_id', 'timestamp'),
    )
