"""
Unit tests for repository layer.

Tests CRUD operations, error handling, and connection pooling for all repositories.
"""
import os
import sys
import tempfile
import sqlite3
import json
from pathlib import Path

import pytest

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from repositories.base_repository import BaseRepository, ConnectionPool
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from repositories.instance_repository import InstanceRepository
from core.error_handler import AlpacaError


# ============================================================================
# ChatRepository Tests
# ============================================================================

def test_chat_repository_create(temp_db):
    """Test creating a new chat."""
    repo = ChatRepository(temp_db)
    
    chat = {
        'id': 'test-chat-1',
        'name': 'Test Chat',
        'folder': None,
        'is_template': False
    }
    
    chat_id = repo.create(chat)
    assert chat_id == 'test-chat-1'
    
    # Verify it was created
    retrieved = repo.get_by_id('test-chat-1')
    assert retrieved is not None
    assert retrieved['name'] == 'Test Chat'
    assert retrieved['folder'] is None
    assert retrieved['is_template'] is False


def test_chat_repository_get_by_id(temp_db):
    """Test retrieving a chat by ID."""
    repo = ChatRepository(temp_db)
    
    # Create a chat
    chat = {
        'id': 'test-chat-2',
        'name': 'Another Chat',
        'folder': 'folder-1',
        'is_template': True
    }
    repo.create(chat)
    
    # Retrieve it
    retrieved = repo.get_by_id('test-chat-2')
    assert retrieved is not None
    assert retrieved['id'] == 'test-chat-2'
    assert retrieved['name'] == 'Another Chat'
    assert retrieved['folder'] == 'folder-1'
    assert retrieved['is_template'] is True
    
    # Try to get non-existent chat
    not_found = repo.get_by_id('non-existent')
    assert not_found is None


def test_chat_repository_update(temp_db):
    """Test updating a chat."""
    repo = ChatRepository(temp_db)
    
    # Create a chat
    chat = {
        'id': 'test-chat-3',
        'name': 'Original Name',
        'folder': None,
        'is_template': False
    }
    repo.create(chat)
    
    # Update it
    success = repo.update('test-chat-3', {'name': 'Updated Name', 'is_template': True})
    assert success is True
    
    # Verify update
    retrieved = repo.get_by_id('test-chat-3')
    assert retrieved['name'] == 'Updated Name'
    assert retrieved['is_template'] is True


def test_chat_repository_delete(temp_db):
    """Test deleting a chat."""
    repo = ChatRepository(temp_db)
    
    # Create a chat
    chat = {
        'id': 'test-chat-4',
        'name': 'To Delete',
        'folder': None,
        'is_template': False
    }
    repo.create(chat)
    
    # Verify it exists
    assert repo.exists('test-chat-4') is True
    
    # Delete it
    success = repo.delete('test-chat-4')
    assert success is True
    
    # Verify it's gone
    assert repo.exists('test-chat-4') is False


def test_chat_repository_get_by_folder(temp_db):
    """Test retrieving chats by folder."""
    repo = ChatRepository(temp_db)
    
    # Create chats in different folders
    repo.create({'id': 'chat-1', 'name': 'Chat 1', 'folder': None, 'is_template': False})
    repo.create({'id': 'chat-2', 'name': 'Chat 2', 'folder': 'folder-1', 'is_template': False})
    repo.create({'id': 'chat-3', 'name': 'Chat 3', 'folder': 'folder-1', 'is_template': False})
    repo.create({'id': 'chat-4', 'name': 'Chat 4', 'folder': 'folder-2', 'is_template': False})
    
    # Get chats in root folder
    root_chats = repo.get_by_folder(None)
    assert len(root_chats) == 1
    assert root_chats[0]['id'] == 'chat-1'
    
    # Get chats in folder-1
    folder1_chats = repo.get_by_folder('folder-1')
    assert len(folder1_chats) == 2
    chat_ids = {c['id'] for c in folder1_chats}
    assert chat_ids == {'chat-2', 'chat-3'}


# ============================================================================
# MessageRepository Tests
# ============================================================================

def test_message_repository_create(temp_db):
    """Test creating a new message."""
    chat_repo = ChatRepository(temp_db)
    msg_repo = MessageRepository(temp_db)
    
    # Create a chat first
    chat_repo.create({'id': 'chat-1', 'name': 'Chat 1', 'folder': None, 'is_template': False})
    
    # Create a message
    message = {
        'id': 'msg-1',
        'chat_id': 'chat-1',
        'role': 'user',
        'model': None,
        'content': 'Hello, world!'
    }
    
    msg_id = msg_repo.create(message)
    assert msg_id == 'msg-1'
    
    # Verify it was created
    retrieved = msg_repo.get_by_id('msg-1')
    assert retrieved is not None
    assert retrieved['content'] == 'Hello, world!'
    assert retrieved['role'] == 'user'


def test_message_repository_get_by_chat(temp_db):
    """Test retrieving messages by chat."""
    chat_repo = ChatRepository(temp_db)
    msg_repo = MessageRepository(temp_db)
    
    # Create a chat
    chat_repo.create({'id': 'chat-1', 'name': 'Chat 1', 'folder': None, 'is_template': False})
    
    # Create multiple messages
    for i in range(5):
        msg_repo.create({
            'id': f'msg-{i}',
            'chat_id': 'chat-1',
            'role': 'user' if i % 2 == 0 else 'assistant',
            'model': 'test-model',
            'content': f'Message {i}'
        })
    
    # Get all messages
    messages = msg_repo.get_by_chat('chat-1')
    assert len(messages) == 5
    
    # Test pagination
    page1 = msg_repo.get_by_chat('chat-1', limit=2, offset=0)
    assert len(page1) == 2
    
    page2 = msg_repo.get_by_chat('chat-1', limit=2, offset=2)
    assert len(page2) == 2


def test_message_repository_count(temp_db):
    """Test counting messages in a chat."""
    chat_repo = ChatRepository(temp_db)
    msg_repo = MessageRepository(temp_db)
    
    # Create a chat
    chat_repo.create({'id': 'chat-1', 'name': 'Chat 1', 'folder': None, 'is_template': False})
    
    # Initially should be 0
    assert msg_repo.count_by_chat('chat-1') == 0
    
    # Add messages
    for i in range(3):
        msg_repo.create({
            'id': f'msg-{i}',
            'chat_id': 'chat-1',
            'role': 'user',
            'content': f'Message {i}'
        })
    
    # Should now be 3
    assert msg_repo.count_by_chat('chat-1') == 3


def test_message_repository_delete(temp_db):
    """Test deleting a message."""
    chat_repo = ChatRepository(temp_db)
    msg_repo = MessageRepository(temp_db)
    
    # Create a chat and message
    chat_repo.create({'id': 'chat-1', 'name': 'Chat 1', 'folder': None, 'is_template': False})
    msg_repo.create({
        'id': 'msg-1',
        'chat_id': 'chat-1',
        'role': 'user',
        'content': 'To delete'
    })
    
    # Delete the message
    success = msg_repo.delete('msg-1')
    assert success is True
    
    # Verify it's gone
    assert msg_repo.get_by_id('msg-1') is None


def test_message_repository_search(temp_db):
    """Test searching messages."""
    chat_repo = ChatRepository(temp_db)
    msg_repo = MessageRepository(temp_db)
    
    # Create a chat
    chat_repo.create({'id': 'chat-1', 'name': 'Chat 1', 'folder': None, 'is_template': False})
    
    # Create messages with different content
    msg_repo.create({'id': 'msg-1', 'chat_id': 'chat-1', 'role': 'user', 'content': 'Hello world'})
    msg_repo.create({'id': 'msg-2', 'chat_id': 'chat-1', 'role': 'user', 'content': 'Goodbye world'})
    msg_repo.create({'id': 'msg-3', 'chat_id': 'chat-1', 'role': 'user', 'content': 'Python programming'})
    
    # Search for "world"
    results = msg_repo.search('world', chat_id='chat-1')
    assert len(results) == 2
    
    # Search for "Python"
    results = msg_repo.search('Python', chat_id='chat-1')
    assert len(results) == 1
    assert results[0]['id'] == 'msg-3'


# ============================================================================
# InstanceRepository Tests
# ============================================================================

def test_instance_repository_create(temp_db):
    """Test creating a new instance."""
    repo = InstanceRepository(temp_db)
    
    instance = {
        'id': 'instance-1',
        'pinned': True,
        'type': 'ollama',
        'properties': {
            'name': 'Local Ollama',
            'url': 'http://localhost:11434'
        }
    }
    
    instance_id = repo.create(instance)
    assert instance_id == 'instance-1'
    
    # Verify it was created
    retrieved = repo.get_by_id('instance-1')
    assert retrieved is not None
    assert retrieved['pinned'] is True
    assert retrieved['type'] == 'ollama'
    assert retrieved['properties']['name'] == 'Local Ollama'


def test_instance_repository_get_all(temp_db):
    """Test retrieving all instances."""
    repo = InstanceRepository(temp_db)
    
    # Create multiple instances
    repo.create({
        'id': 'instance-1',
        'pinned': True,
        'type': 'ollama',
        'properties': {'name': 'Instance 1'}
    })
    repo.create({
        'id': 'instance-2',
        'pinned': False,
        'type': 'openai',
        'properties': {'name': 'Instance 2'}
    })
    
    # Get all
    instances = repo.get_all()
    assert len(instances) == 2


def test_instance_repository_update(temp_db):
    """Test updating an instance."""
    repo = InstanceRepository(temp_db)
    
    # Create an instance
    repo.create({
        'id': 'instance-1',
        'pinned': False,
        'type': 'ollama',
        'properties': {'name': 'Original'}
    })
    
    # Update it
    success = repo.update('instance-1', {
        'pinned': True,
        'properties': {'name': 'Updated'}
    })
    assert success is True
    
    # Verify update
    retrieved = repo.get_by_id('instance-1')
    assert retrieved['pinned'] is True
    assert retrieved['properties']['name'] == 'Updated'


def test_instance_repository_model_list(temp_db):
    """Test managing instance model lists."""
    repo = InstanceRepository(temp_db)
    
    # Create an instance
    repo.create({
        'id': 'instance-1',
        'pinned': False,
        'type': 'ollama',
        'properties': {'name': 'Test'}
    })
    
    # Initially empty
    models = repo.get_model_list('instance-1')
    assert models == []
    
    # Set model list
    repo.set_model_list('instance-1', ['model-1', 'model-2'])
    models = repo.get_model_list('instance-1')
    assert models == ['model-1', 'model-2']
    
    # Add a model
    repo.add_model_to_list('instance-1', 'model-3')
    models = repo.get_model_list('instance-1')
    assert 'model-3' in models
    
    # Remove a model
    repo.remove_model_from_list('instance-1', 'model-2')
    models = repo.get_model_list('instance-1')
    assert 'model-2' not in models


# ============================================================================
# Connection Pool Tests
# ============================================================================

def test_connection_pool_basic(temp_db):
    """Test basic connection pool operations."""
    pool = ConnectionPool(temp_db, pool_size=2)
    
    # Get a connection
    conn1 = pool.get_connection()
    assert conn1 is not None
    
    # Return it
    pool.return_connection(conn1)
    
    # Get it again
    conn2 = pool.get_connection()
    assert conn2 is not None
    
    pool.return_connection(conn2)
    pool.close_all()


def test_connection_pool_timeout(temp_db):
    """Test connection pool timeout."""
    pool = ConnectionPool(temp_db, pool_size=1)
    
    # Get the only connection
    conn1 = pool.get_connection()
    
    # Try to get another with short timeout
    with pytest.raises(AlpacaError) as exc_info:
        pool.get_connection(timeout=0.1)
    
    assert exc_info.value.category.value == "database"
    
    pool.return_connection(conn1)
    pool.close_all()


# ============================================================================
# Error Handling Tests
# ============================================================================

def test_repository_handles_sql_errors(temp_db):
    """Test that repositories properly handle SQL errors."""
    repo = ChatRepository(temp_db)
    
    # Try to create a chat with duplicate ID
    chat = {
        'id': 'test-chat',
        'name': 'Test',
        'folder': None,
        'is_template': False
    }
    repo.create(chat)
    
    # Try to create again with same ID
    with pytest.raises(AlpacaError) as exc_info:
        repo.create(chat)
    
    assert exc_info.value.category.value == "database"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Initialize database schema
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            folder TEXT,
            is_template INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            model TEXT,
            content TEXT NOT NULL,
            date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chat(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attachment (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES message(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instance (
            id TEXT PRIMARY KEY,
            pinned INTEGER NOT NULL,
            type TEXT NOT NULL,
            properties TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS online_instance_model_list (
            id TEXT PRIMARY KEY,
            list TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    BaseRepository.close_pool(db_path)
    try:
        os.unlink(db_path)
    except OSError:
        pass
