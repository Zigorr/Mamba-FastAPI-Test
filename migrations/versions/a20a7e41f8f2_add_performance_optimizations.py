"""Add performance optimizations

Revision ID: a20a7e41f8f2
Revises: 
Create Date: 2025-04-27

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import Column, String, ForeignKey, DateTime, Text, Boolean, Integer, JSON, Index
from sqlalchemy.sql import text


# revision identifiers, used by Alembic.
revision = 'a20a7e41f8f2'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new indexes for performance optimization
    
    # User table indexes
    op.create_index('idx_user_name_email', 'users', ['first_name', 'last_name', 'email'])
    
    # Conversation table indexes
    op.create_index('idx_conv_user_updated', 'conversations', ['user_username', 'updated_at'])
    
    # Message table indexes
    op.create_index('idx_message_conv_timestamp', 'messages', ['conversation_id', 'timestamp'])
    
    # UserSession table indexes
    op.create_index('idx_session_user_conv_active', 'user_sessions', ['user_username', 'conversation_id', 'is_active'])


def downgrade() -> None:
    # Remove the indexes
    op.drop_index('idx_user_name_email', table_name='users')
    op.drop_index('idx_conv_user_updated', table_name='conversations')
    op.drop_index('idx_message_conv_timestamp', table_name='messages')
    op.drop_index('idx_session_user_conv_active', table_name='user_sessions') 