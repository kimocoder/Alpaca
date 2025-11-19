"""
Unit tests for service layer.

Tests business logic, validation, and error handling in services.
"""
import sys
from pathlib import Path
import tempfile
import os
import sqlite3

import pytest

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from services.chat_service import ChatService
from services.message_service import MessageService
from services.model_service import ModelService
from services.instance_service import InstanceService
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from repositories.instance_repository import InstanceRepository
from core.error_handler import AlpacaError, ErrorCategory


# ============================================================================
# Test Fixtures
# ============================================================================

def create_test_database():
    """Create a temporary test database with required schema."""
    db_fd, db_path = tempfile.mkstemp(suffix='.db')
    os.close(db_fd)
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
        CREATE TABLE chat (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            folder TEXT,
            is_template INTEGER DEFAULT 0
        )
    """)
    
    cursor.execute("""
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            model TEXT,
            date_time TEXT,
            content TEXT,
            FOREIGN KEY (chat_id) REFERENCES chat(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE attachment (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            type TEXT,
            name TEXT,
            content TEXT,
            FOREIGN KEY (message_id) REFERENCES message(id) ON DELETE CASCADE
        )
    """)
    
    cursor.execute("""
        CREATE TABLE instance (
            id TEXT PRIMARY KEY,
            pinned INTEGER DEFAULT 0,
            type TEXT NOT NULL,
            properties TEXT
        )
    """)
    
    cursor.execute("""
        CREATE TABLE online_instance_model_list (
            id TEXT PRIMARY KEY,
            list TEXT
        )
    """)
    
    conn.commit()
    conn.close()
    
    return db_path


@pytest.fixture
def test_db():
    """Fixture that provides a test database."""
    db_path = create_test_database()
    yield db_path
    # Cleanup
    try:
        os.unlink(db_path)
    except:
        pass


# ============================================================================
# ChatService Tests
# ============================================================================

@pytest.mark.unit
def test_chat_service_create_chat(test_db):
    """Test creating a chat with valid data."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    
    assert chat_id is not None
    chat = chat_service.get_chat(chat_id)
    assert chat['name'] == "Test Chat"
    assert chat['folder'] is None
    assert chat['is_template'] is False


@pytest.mark.unit
def test_chat_service_create_chat_with_empty_name_fails(test_db):
    """Test that creating a chat with empty name fails."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    
    with pytest.raises(AlpacaError) as exc_info:
        chat_service.create_chat("")
    
    assert exc_info.value.category == ErrorCategory.VALIDATION


@pytest.mark.unit
def test_chat_service_duplicate_names_handled(test_db):
    """Test that duplicate chat names are handled."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    
    chat_id1 = chat_service.create_chat("Test Chat")
    chat_id2 = chat_service.create_chat("Test Chat")
    
    chat1 = chat_service.get_chat(chat_id1)
    chat2 = chat_service.get_chat(chat_id2)
    
    assert chat1['name'] == "Test Chat"
    assert chat2['name'] == "Test Chat (1)"


@pytest.mark.unit
def test_chat_service_update_chat(test_db):
    """Test updating a chat."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Original Name")
    success = chat_service.update_chat(chat_id, name="Updated Name")
    
    assert success is True
    chat = chat_service.get_chat(chat_id)
    assert chat['name'] == "Updated Name"


@pytest.mark.unit
def test_chat_service_delete_chat(test_db):
    """Test deleting a chat."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    message_service.create_message(chat_id, 'user', "Test message")
    
    deleted = chat_service.delete_chat(chat_id)
    
    assert deleted is True
    assert chat_service.get_chat(chat_id) is None


@pytest.mark.unit
def test_chat_service_load_messages_with_pagination(test_db):
    """Test loading messages with pagination."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    
    # Create 10 messages
    for i in range(10):
        message_service.create_message(chat_id, 'user', f"Message {i}")
    
    # Load first 5
    messages = chat_service.load_chat_messages(chat_id, limit=5, offset=0)
    assert len(messages) == 5
    
    # Load next 5
    messages = chat_service.load_chat_messages(chat_id, limit=5, offset=5)
    assert len(messages) == 5


# ============================================================================
# MessageService Tests
# ============================================================================

@pytest.mark.unit
def test_message_service_create_message(test_db):
    """Test creating a message."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    msg_id = message_service.create_message(chat_id, 'user', "Test content")
    
    assert msg_id is not None
    message = message_service.get_message(msg_id)
    assert message['role'] == 'user'
    assert message['content'] == "Test content"


@pytest.mark.unit
def test_message_service_invalid_role_fails(test_db):
    """Test that invalid role fails."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    
    with pytest.raises(AlpacaError) as exc_info:
        message_service.create_message(chat_id, 'invalid', "Test")
    
    assert exc_info.value.category == ErrorCategory.VALIDATION


@pytest.mark.unit
def test_message_service_update_message(test_db):
    """Test updating a message."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    msg_id = message_service.create_message(chat_id, 'user', "Original")
    
    success = message_service.update_message(msg_id, content="Updated")
    
    assert success is True
    message = message_service.get_message(msg_id)
    assert message['content'] == "Updated"


@pytest.mark.unit
def test_message_service_delete_message(test_db):
    """Test deleting a message."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    msg_id = message_service.create_message(chat_id, 'user', "Test")
    
    deleted = message_service.delete_message(msg_id)
    
    assert deleted is True
    assert message_service.get_message(msg_id) is None


@pytest.mark.unit
def test_message_service_search_messages(test_db):
    """Test searching messages."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    message_service.create_message(chat_id, 'user', "Hello world")
    message_service.create_message(chat_id, 'user', "Goodbye world")
    message_service.create_message(chat_id, 'user', "Something else")
    
    results = message_service.search_messages("world", chat_id)
    
    assert len(results) == 2


@pytest.mark.unit
def test_message_service_add_attachment(test_db):
    """Test adding an attachment to a message."""
    chat_service = ChatService(ChatRepository(test_db), MessageRepository(test_db))
    message_service = MessageService(MessageRepository(test_db))
    
    chat_id = chat_service.create_chat("Test Chat")
    msg_id = message_service.create_message(chat_id, 'user', "Test")
    
    attachment_id = message_service.add_attachment(
        msg_id,
        'image',
        'test.png',
        'base64content'
    )
    
    assert attachment_id is not None
    attachments = message_service.get_attachments(msg_id)
    assert len(attachments) == 1
    assert attachments[0]['name'] == 'test.png'


# ============================================================================
# ModelService Tests
# ============================================================================

@pytest.mark.unit
def test_model_service_validate_model_name(test_db):
    """Test model name validation."""
    model_service = ModelService(InstanceRepository(test_db))
    
    assert model_service.validate_model_name("llama2") is True
    assert model_service.validate_model_name("mistral:7b") is True
    assert model_service.validate_model_name("codellama:13b-instruct") is True
    assert model_service.validate_model_name("") is False
    assert model_service.validate_model_name("   ") is False


@pytest.mark.unit
def test_model_service_parse_model_name(test_db):
    """Test parsing model names."""
    model_service = ModelService(InstanceRepository(test_db))
    
    parsed = model_service.parse_model_name("llama2:13b-instruct")
    assert parsed['base'] == "llama2"
    assert parsed['tag'] == "13b"
    assert parsed['variant'] == "instruct"
    
    parsed = model_service.parse_model_name("mistral")
    assert parsed['base'] == "mistral"
    assert parsed['tag'] == ""
    assert parsed['variant'] == ""


@pytest.mark.unit
def test_model_service_format_display_name(test_db):
    """Test formatting model display names."""
    model_service = ModelService(InstanceRepository(test_db))
    
    display = model_service.format_model_display_name("llama2:13b-instruct")
    assert "Llama2" in display
    assert "13b" in display
    assert "instruct" in display


@pytest.mark.unit
def test_model_service_get_model_size(test_db):
    """Test extracting model size."""
    model_service = ModelService(InstanceRepository(test_db))
    
    assert model_service.get_model_size("llama2:7b") == "7b"
    assert model_service.get_model_size("mistral:13b") == "13b"
    assert model_service.get_model_size("llama2") is None


@pytest.mark.unit
def test_model_service_sort_models(test_db):
    """Test sorting models."""
    model_service = ModelService(InstanceRepository(test_db))
    
    models = ["llama2:70b", "llama2:7b", "mistral:13b", "llama2:13b"]
    sorted_models = model_service.sort_models(models)
    
    # Should be sorted by base name, then size
    assert sorted_models[0] == "llama2:7b"
    assert sorted_models[1] == "llama2:13b"
    assert sorted_models[2] == "llama2:70b"
    assert sorted_models[3] == "mistral:13b"


@pytest.mark.unit
def test_model_service_filter_models(test_db):
    """Test filtering models."""
    model_service = ModelService(InstanceRepository(test_db))
    
    models = ["llama2:7b", "llama2:13b", "mistral:7b", "codellama:13b"]
    
    # Filter by search term
    filtered = model_service.filter_models(models, search_term="llama2")
    assert len(filtered) == 2
    
    # Filter by size
    filtered = model_service.filter_models(models, min_size=10)
    assert len(filtered) == 2
    assert all("13b" in m for m in filtered)


# ============================================================================
# InstanceService Tests
# ============================================================================

@pytest.mark.unit
def test_instance_service_create_instance(test_db):
    """Test creating an instance."""
    instance_service = InstanceService(InstanceRepository(test_db))
    
    instance_id = instance_service.create_instance(
        'local',
        {'model_directory': '/path/to/models'}
    )
    
    assert instance_id is not None
    instance = instance_service.get_instance(instance_id)
    assert instance['type'] == 'local'
    assert instance['properties']['model_directory'] == '/path/to/models'


@pytest.mark.unit
def test_instance_service_invalid_type_fails(test_db):
    """Test that invalid instance type fails."""
    instance_service = InstanceService(InstanceRepository(test_db))
    
    with pytest.raises(AlpacaError) as exc_info:
        instance_service.create_instance('invalid_type', {})
    
    assert exc_info.value.category == ErrorCategory.VALIDATION


@pytest.mark.unit
def test_instance_service_remote_requires_url(test_db):
    """Test that remote instance requires URL."""
    instance_service = InstanceService(InstanceRepository(test_db))
    
    with pytest.raises(AlpacaError) as exc_info:
        instance_service.create_instance('remote', {})
    
    assert exc_info.value.category == ErrorCategory.VALIDATION
    assert 'url' in exc_info.value.message.lower()


@pytest.mark.unit
def test_instance_service_pin_unpin(test_db):
    """Test pinning and unpinning instances."""
    instance_service = InstanceService(InstanceRepository(test_db))
    
    instance_id = instance_service.create_instance(
        'local',
        {'model_directory': '/path'}
    )
    
    # Pin
    success = instance_service.pin_instance(instance_id)
    assert success is True
    
    instance = instance_service.get_instance(instance_id)
    assert instance['pinned'] is True
    
    # Unpin
    success = instance_service.unpin_instance(instance_id)
    assert success is True
    
    instance = instance_service.get_instance(instance_id)
    assert instance['pinned'] is False


@pytest.mark.unit
def test_instance_service_get_display_name(test_db):
    """Test getting instance display names."""
    instance_service = InstanceService(InstanceRepository(test_db))
    
    # Local instance
    instance_id = instance_service.create_instance('local', {})
    instance = instance_service.get_instance(instance_id)
    display = instance_service.get_instance_display_name(instance)
    assert "Local" in display
    
    # Remote instance
    instance_id = instance_service.create_instance(
        'remote',
        {'url': 'http://example.com'}
    )
    instance = instance_service.get_instance(instance_id)
    display = instance_service.get_instance_display_name(instance)
    assert "Remote" in display
    assert "example.com" in display


@pytest.mark.unit
def test_instance_service_validate_connection(test_db):
    """Test validating instance connection."""
    instance_service = InstanceService(InstanceRepository(test_db))
    
    # Valid instance
    instance_id = instance_service.create_instance(
        'remote',
        {'url': 'http://example.com'}
    )
    result = instance_service.validate_instance_connection(instance_id)
    assert result['success'] is True
    
    # Invalid instance (non-existent)
    result = instance_service.validate_instance_connection('non-existent')
    assert result['success'] is False
