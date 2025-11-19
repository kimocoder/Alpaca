"""
Integration test for chat creation flow.

Feature: alpaca-code-quality-improvements
Tests the complete flow for chat creation and persistence,
including folder assignment and duplicate name handling.

Validates: Requirements 9.2
"""
import os
import sys
import uuid
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime

import pytest

# Add src directory to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from services.chat_service import ChatService
from services.message_service import MessageService
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from core.error_handler import AlpacaError, ErrorCategory


class TestChatCreationFlow:
    """Integration tests for the complete chat creation flow."""
    
    @pytest.fixture
    def test_db(self):
        """Create a temporary test database with schema."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name
        
        # Create schema
        conn = sqlite3.connect(db_path)
        conn.execute("""
            CREATE TABLE chat (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT,
                is_template INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
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
        conn.execute("""
            CREATE TABLE folder (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                parent_folder TEXT
            )
        """)
        conn.commit()
        conn.close()
        
        yield db_path
        
        # Cleanup
        try:
            os.unlink(db_path)
        except OSError:
            pass
    
    @pytest.fixture
    def services(self, test_db):
        """Create service instances with test database."""
        chat_repo = ChatRepository(db_path=test_db)
        message_repo = MessageRepository(db_path=test_db)
        chat_service = ChatService(chat_repo=chat_repo, message_repo=message_repo)
        message_service = MessageService(message_repo=message_repo)
        
        return {
            'chat_service': chat_service,
            'message_service': message_service,
            'chat_repo': chat_repo,
            'message_repo': message_repo
        }
    
    def test_basic_chat_creation(self, services):
        """
        Test basic chat creation and persistence.
        
        Validates:
        1. Chat can be created with a name
        2. Chat is persisted to database
        3. Chat can be retrieved by ID
        4. Chat has correct default values
        """
        chat_service = services['chat_service']
        
        # Create a chat
        chat_id = chat_service.create_chat(name="My First Chat")
        
        assert chat_id is not None
        assert len(chat_id) > 0
        
        # Retrieve the chat
        chat = chat_service.get_chat(chat_id)
        
        assert chat is not None
        assert chat['id'] == chat_id
        assert chat['name'] == "My First Chat"
        assert chat['folder'] is None
        assert chat['is_template'] is False
    
    def test_chat_creation_with_folder(self, services):
        """
        Test chat creation with folder assignment.
        
        Validates that chats can be organized into folders.
        """
        chat_service = services['chat_service']
        
        # Create a chat in a folder
        folder_id = "test-folder-001"
        chat_id = chat_service.create_chat(
            name="Chat in Folder",
            folder_id=folder_id
        )
        
        # Retrieve and verify
        chat = chat_service.get_chat(chat_id)
        assert chat['folder'] == folder_id
        
        # Verify we can get chats by folder
        chats_in_folder = chat_service.get_chats_in_folder(folder_id)
        assert len(chats_in_folder) == 1
        assert chats_in_folder[0]['id'] == chat_id
    
    def test_chat_creation_in_root_folder(self, services):
        """
        Test chat creation in root folder (no folder).
        
        Validates that chats without a folder are in the root.
        """
        chat_service = services['chat_service']
        
        # Create multiple chats in root
        chat_id1 = chat_service.create_chat(name="Root Chat 1")
        chat_id2 = chat_service.create_chat(name="Root Chat 2")
        
        # Get chats in root folder (folder_id=None)
        root_chats = chat_service.get_chats_in_folder(folder_id=None)
        
        assert len(root_chats) >= 2
        root_chat_ids = [chat['id'] for chat in root_chats]
        assert chat_id1 in root_chat_ids
        assert chat_id2 in root_chat_ids
    
    def test_duplicate_name_handling(self, services):
        """
        Test handling of duplicate chat names.
        
        Validates that when a duplicate name is used, the system
        automatically generates a unique name by appending a counter.
        """
        chat_service = services['chat_service']
        
        # Create first chat
        chat_id1 = chat_service.create_chat(name="Duplicate Name")
        chat1 = chat_service.get_chat(chat_id1)
        assert chat1['name'] == "Duplicate Name"
        
        # Create second chat with same name
        chat_id2 = chat_service.create_chat(name="Duplicate Name")
        chat2 = chat_service.get_chat(chat_id2)
        assert chat2['name'] == "Duplicate Name (1)"
        
        # Create third chat with same name
        chat_id3 = chat_service.create_chat(name="Duplicate Name")
        chat3 = chat_service.get_chat(chat_id3)
        assert chat3['name'] == "Duplicate Name (2)"
        
        # Verify all three chats exist with unique names
        assert chat1['name'] != chat2['name']
        assert chat1['name'] != chat3['name']
        assert chat2['name'] != chat3['name']
    
    def test_template_chat_creation(self, services):
        """
        Test creation of template chats.
        
        Validates that chats can be marked as templates.
        """
        chat_service = services['chat_service']
        
        # Create a template chat
        chat_id = chat_service.create_chat(
            name="My Template",
            is_template=True
        )
        
        # Verify it's marked as template
        chat = chat_service.get_chat(chat_id)
        assert chat['is_template'] is True
        
        # Verify it appears in templates list
        templates = chat_service.get_templates()
        template_ids = [t['id'] for t in templates]
        assert chat_id in template_ids
    
    def test_empty_name_validation(self, services):
        """
        Test validation of empty chat names.
        
        Validates that empty or whitespace-only names are rejected.
        """
        chat_service = services['chat_service']
        
        # Try to create chat with empty name
        with pytest.raises(AlpacaError) as exc_info:
            chat_service.create_chat(name="")
        
        error = exc_info.value
        assert error.category == ErrorCategory.VALIDATION
        assert error.recoverable is True
        assert 'name' in error.user_message.lower()
        
        # Try with whitespace-only name
        with pytest.raises(AlpacaError) as exc_info:
            chat_service.create_chat(name="   \n\t  ")
        
        error = exc_info.value
        assert error.category == ErrorCategory.VALIDATION
    
    def test_chat_creation_with_messages(self, services):
        """
        Test creating a chat and immediately adding messages.
        
        Validates the complete flow of chat creation followed by
        message addition.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Chat with Messages")
        
        # Add messages
        msg_id1 = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Hello!"
        )
        msg_id2 = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Hi there!"
        )
        
        # Verify messages are associated with chat
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == 2
        assert messages[0]['chat_id'] == chat_id
        assert messages[1]['chat_id'] == chat_id
    
    def test_chat_update_after_creation(self, services):
        """
        Test updating chat properties after creation.
        
        Validates that chat name and folder can be updated.
        """
        chat_service = services['chat_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Original Name")
        
        # Update name
        updated = chat_service.update_chat(chat_id, name="Updated Name")
        assert updated is True
        
        # Verify update
        chat = chat_service.get_chat(chat_id)
        assert chat['name'] == "Updated Name"
        
        # Update folder
        updated = chat_service.update_chat(chat_id, folder_id="new-folder")
        assert updated is True
        
        # Verify folder update
        chat = chat_service.get_chat(chat_id)
        assert chat['folder'] == "new-folder"
    
    def test_chat_deletion(self, services):
        """
        Test deleting a chat and its messages.
        
        Validates that deletion removes the chat and all associated data.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with messages
        chat_id = chat_service.create_chat(name="Chat to Delete")
        message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Message 1"
        )
        message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Message 2"
        )
        
        # Verify chat and messages exist
        assert chat_service.get_chat(chat_id) is not None
        assert len(message_service.get_messages_for_chat(chat_id)) == 2
        
        # Delete chat
        deleted = chat_service.delete_chat(chat_id)
        assert deleted is True
        
        # Verify chat is gone
        assert chat_service.get_chat(chat_id) is None
        
        # Verify messages are gone (cascade delete)
        assert len(message_service.get_messages_for_chat(chat_id)) == 0
    
    def test_multiple_chats_in_different_folders(self, services):
        """
        Test organizing multiple chats across different folders.
        
        Validates folder-based organization of chats.
        """
        chat_service = services['chat_service']
        
        # Create chats in different folders
        folder1_chat1 = chat_service.create_chat("Folder1 Chat1", folder_id="folder-1")
        folder1_chat2 = chat_service.create_chat("Folder1 Chat2", folder_id="folder-1")
        folder2_chat1 = chat_service.create_chat("Folder2 Chat1", folder_id="folder-2")
        root_chat = chat_service.create_chat("Root Chat", folder_id=None)
        
        # Verify folder1 has 2 chats
        folder1_chats = chat_service.get_chats_in_folder("folder-1")
        assert len(folder1_chats) == 2
        
        # Verify folder2 has 1 chat
        folder2_chats = chat_service.get_chats_in_folder("folder-2")
        assert len(folder2_chats) == 1
        
        # Verify root has at least 1 chat
        root_chats = chat_service.get_chats_in_folder(None)
        assert len(root_chats) >= 1
    
    def test_chat_name_trimming(self, services):
        """
        Test that chat names are trimmed of whitespace.
        
        Validates that leading/trailing whitespace is removed.
        """
        chat_service = services['chat_service']
        
        # Create chat with whitespace in name
        chat_id = chat_service.create_chat(name="  Trimmed Name  ")
        
        # Verify name is trimmed
        chat = chat_service.get_chat(chat_id)
        assert chat['name'] == "Trimmed Name"
        assert chat['name'] == chat['name'].strip()
    
    def test_chat_duplication(self, services):
        """
        Test duplicating an existing chat.
        
        Validates that a chat can be duplicated with all its messages.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create original chat with messages
        original_id = chat_service.create_chat(name="Original Chat")
        message_service.create_message(
            chat_id=original_id,
            role='user',
            content="Original message"
        )
        
        # Duplicate the chat
        duplicate_id = chat_service.duplicate_chat(original_id)
        
        assert duplicate_id != original_id
        
        # Verify duplicate has correct name
        duplicate = chat_service.get_chat(duplicate_id)
        assert duplicate['name'] == "Copy of Original Chat"
        
        # Verify messages were copied
        duplicate_messages = message_service.get_messages_for_chat(duplicate_id)
        assert len(duplicate_messages) == 1
        assert duplicate_messages[0]['content'] == "Original message"
        assert duplicate_messages[0]['chat_id'] == duplicate_id
    
    def test_chat_creation_persistence_across_connections(self, services, test_db):
        """
        Test that chat creation persists across database connections.
        
        Validates that data is properly committed to the database.
        """
        chat_service = services['chat_service']
        
        # Create a chat
        chat_id = chat_service.create_chat(name="Persistent Chat")
        
        # Create a new service with fresh connection
        new_chat_repo = ChatRepository(db_path=test_db)
        new_message_repo = MessageRepository(db_path=test_db)
        new_chat_service = ChatService(
            chat_repo=new_chat_repo,
            message_repo=new_message_repo
        )
        
        # Verify chat exists in new connection
        chat = new_chat_service.get_chat(chat_id)
        assert chat is not None
        assert chat['name'] == "Persistent Chat"
    
    def test_concurrent_chat_creation(self, services):
        """
        Test creating multiple chats rapidly.
        
        Validates that the system handles rapid chat creation without
        data corruption or ID conflicts.
        """
        chat_service = services['chat_service']
        
        # Create multiple chats rapidly
        chat_ids = []
        for i in range(20):
            chat_id = chat_service.create_chat(name=f"Concurrent Chat {i}")
            chat_ids.append(chat_id)
        
        # Verify all chats were created
        assert len(chat_ids) == 20
        
        # Verify all IDs are unique
        assert len(set(chat_ids)) == 20
        
        # Verify all chats can be retrieved
        for chat_id in chat_ids:
            chat = chat_service.get_chat(chat_id)
            assert chat is not None
    
    def test_chat_message_count(self, services):
        """
        Test getting message count for a chat.
        
        Validates that message counting works correctly.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Chat for Counting")
        
        # Initially should have 0 messages
        count = chat_service.get_message_count(chat_id)
        assert count == 0
        
        # Add messages
        for i in range(5):
            message_service.create_message(
                chat_id=chat_id,
                role='user',
                content=f"Message {i}"
            )
        
        # Verify count
        count = chat_service.get_message_count(chat_id)
        assert count == 5
    
    def test_template_vs_regular_chat(self, services):
        """
        Test distinction between template and regular chats.
        
        Validates that templates and regular chats are properly separated.
        """
        chat_service = services['chat_service']
        
        # Create regular chats
        regular1 = chat_service.create_chat(name="Regular 1", is_template=False)
        regular2 = chat_service.create_chat(name="Regular 2", is_template=False)
        
        # Create template chats
        template1 = chat_service.create_chat(name="Template 1", is_template=True)
        template2 = chat_service.create_chat(name="Template 2", is_template=True)
        
        # Get templates
        templates = chat_service.get_templates()
        template_ids = [t['id'] for t in templates]
        
        # Verify only templates are returned
        assert template1 in template_ids
        assert template2 in template_ids
        assert regular1 not in template_ids
        assert regular2 not in template_ids
    
    def test_chat_update_to_template(self, services):
        """
        Test converting a regular chat to a template.
        
        Validates that chats can be converted to templates after creation.
        """
        chat_service = services['chat_service']
        
        # Create regular chat
        chat_id = chat_service.create_chat(name="Regular Chat", is_template=False)
        
        # Verify it's not a template
        chat = chat_service.get_chat(chat_id)
        assert chat['is_template'] is False
        
        # Convert to template
        updated = chat_service.update_chat(chat_id, is_template=True)
        assert updated is True
        
        # Verify it's now a template
        chat = chat_service.get_chat(chat_id)
        assert chat['is_template'] is True
        
        # Verify it appears in templates
        templates = chat_service.get_templates()
        template_ids = [t['id'] for t in templates]
        assert chat_id in template_ids
