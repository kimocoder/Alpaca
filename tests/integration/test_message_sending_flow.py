"""
Integration test for message sending flow.

Feature: alpaca-code-quality-improvements
Tests the complete flow from UI to database for message sending,
including persistence, retrieval, and error handling.

Validates: Requirements 9.1
"""
import os
import sys
import uuid
import tempfile
import sqlite3
from pathlib import Path
from datetime import datetime
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add src directory to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from services.message_service import MessageService
from services.chat_service import ChatService
from repositories.message_repository import MessageRepository
from repositories.chat_repository import ChatRepository
from core.error_handler import AlpacaError, ErrorCategory


class TestMessageSendingFlow:
    """Integration tests for the complete message sending flow."""
    
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
            CREATE TABLE attachment (
                id TEXT PRIMARY KEY,
                message_id TEXT NOT NULL,
                type TEXT,
                name TEXT,
                content TEXT,
                FOREIGN KEY (message_id) REFERENCES message(id) ON DELETE CASCADE
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
        message_repo = MessageRepository(db_path=test_db)
        chat_repo = ChatRepository(db_path=test_db)
        message_service = MessageService(message_repo=message_repo)
        chat_service = ChatService(chat_repo=chat_repo, message_repo=message_repo)
        
        return {
            'message_service': message_service,
            'chat_service': chat_service,
            'message_repo': message_repo,
            'chat_repo': chat_repo
        }
    
    def test_complete_message_sending_flow(self, services):
        """
        Test the complete flow of sending a message from creation to database.
        
        This test validates:
        1. Chat creation
        2. User message creation
        3. Message persistence to database
        4. Message retrieval from database
        5. Data integrity throughout the flow
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Step 1: Create a chat (simulating UI chat creation)
        chat_id = chat_service.create_chat(name="Test Chat", folder_id=None)
        assert chat_id is not None
        assert len(chat_id) > 0
        
        # Verify chat was created
        chat = chat_service.get_chat(chat_id)
        assert chat is not None
        assert chat['name'] == "Test Chat"
        assert chat['folder'] is None
        
        # Step 2: Create a user message (simulating user typing and sending)
        message_content = "Hello, this is a test message!"
        message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content=message_content,
            model=None
        )
        assert message_id is not None
        assert len(message_id) > 0
        
        # Step 3: Verify message was persisted to database
        saved_message = message_service.get_message(message_id)
        assert saved_message is not None
        assert saved_message['id'] == message_id
        assert saved_message['chat_id'] == chat_id
        assert saved_message['role'] == 'user'
        assert saved_message['content'] == message_content
        assert saved_message['model'] == ''
        assert saved_message['date_time'] is not None
        
        # Step 4: Retrieve messages for the chat
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == 1
        assert messages[0]['id'] == message_id
        assert messages[0]['content'] == message_content
        
        # Step 5: Create an assistant response (simulating bot response)
        bot_message_content = "This is the assistant's response."
        bot_message_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content=bot_message_content,
            model='test-model'
        )
        
        # Step 6: Verify both messages are in the chat
        all_messages = message_service.get_messages_for_chat(chat_id)
        assert len(all_messages) == 2
        
        # Verify order (should be chronological)
        assert all_messages[0]['role'] == 'user'
        assert all_messages[1]['role'] == 'assistant'
        assert all_messages[1]['model'] == 'test-model'
    
    def test_message_persistence_with_attachments(self, services):
        """
        Test message sending with attachments.
        
        Validates that attachments are properly saved and retrieved
        along with the message.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat and message
        chat_id = chat_service.create_chat(name="Chat with Attachments")
        message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Message with attachment"
        )
        
        # Add attachment
        attachment_id = message_service.add_attachment(
            message_id=message_id,
            file_type='image',
            file_name='test.png',
            file_content='base64encodedcontent'
        )
        
        assert attachment_id is not None
        
        # Retrieve attachments
        attachments = message_service.get_attachments(message_id)
        assert len(attachments) == 1
        assert attachments[0]['name'] == 'test.png'
        assert attachments[0]['type'] == 'image'
        assert attachments[0]['content'] == 'base64encodedcontent'
    
    def test_message_retrieval_with_pagination(self, services):
        """
        Test message retrieval with pagination.
        
        Validates that messages can be loaded in batches for
        performance optimization.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Chat with Many Messages")
        
        # Create 100 messages
        message_ids = []
        for i in range(100):
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='user' if i % 2 == 0 else 'assistant',
                content=f"Message {i}"
            )
            message_ids.append(msg_id)
        
        # Test pagination - first batch
        first_batch = message_service.get_messages_for_chat(
            chat_id=chat_id,
            limit=50,
            offset=0
        )
        assert len(first_batch) == 50
        assert first_batch[0]['content'] == "Message 0"
        
        # Test pagination - second batch
        second_batch = message_service.get_messages_for_chat(
            chat_id=chat_id,
            limit=50,
            offset=50
        )
        assert len(second_batch) == 50
        assert second_batch[0]['content'] == "Message 50"
        
        # Test getting all messages
        all_messages = message_service.get_messages_for_chat(
            chat_id=chat_id,
            limit=None
        )
        assert len(all_messages) == 100
    
    def test_error_handling_invalid_role(self, services):
        """
        Test error handling when creating a message with invalid role.
        
        Validates that proper validation errors are raised and
        the database remains consistent.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Test Chat")
        
        # Try to create message with invalid role
        with pytest.raises(AlpacaError) as exc_info:
            message_service.create_message(
                chat_id=chat_id,
                role='invalid_role',
                content="Test message"
            )
        
        # Verify error details
        error = exc_info.value
        assert error.category == ErrorCategory.VALIDATION
        assert error.recoverable is True
        assert 'role' in error.user_message.lower()
        
        # Verify no message was created
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == 0
    
    def test_error_handling_empty_attachment_name(self, services):
        """
        Test error handling when adding attachment with empty name.
        
        Validates that validation errors prevent invalid data
        from being saved.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat and message
        chat_id = chat_service.create_chat(name="Test Chat")
        message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Test message"
        )
        
        # Try to add attachment with empty name
        with pytest.raises(AlpacaError) as exc_info:
            message_service.add_attachment(
                message_id=message_id,
                file_type='image',
                file_name='',
                file_content='content'
            )
        
        # Verify error details
        error = exc_info.value
        assert error.category == ErrorCategory.VALIDATION
        assert error.recoverable is True
        
        # Verify no attachment was created
        attachments = message_service.get_attachments(message_id)
        assert len(attachments) == 0
    
    def test_error_handling_database_failure(self, services):
        """
        Test error handling when database operations fail.
        
        Validates that database errors are properly caught and
        converted to user-friendly errors.
        """
        message_service = services['message_service']
        
        # Try to create message with non-existent chat
        # This should fail due to foreign key constraint
        with pytest.raises(AlpacaError) as exc_info:
            message_service.create_message(
                chat_id='non-existent-chat-id',
                role='user',
                content="Test message"
            )
        
        # Verify error details
        error = exc_info.value
        assert error.category == ErrorCategory.DATABASE
        assert error.recoverable is True
        assert 'save' in error.user_message.lower() or 'create' in error.user_message.lower()
    
    def test_message_update_flow(self, services):
        """
        Test updating a message after it's been sent.
        
        Validates that messages can be edited and the changes
        are properly persisted.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat and message
        chat_id = chat_service.create_chat(name="Test Chat")
        message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Original content"
        )
        
        # Update message content
        updated = message_service.update_message(
            message_id=message_id,
            content="Updated content"
        )
        assert updated is True
        
        # Verify update was persisted
        message = message_service.get_message(message_id)
        assert message['content'] == "Updated content"
        
        # Update model
        updated = message_service.update_message(
            message_id=message_id,
            model='new-model'
        )
        assert updated is True
        
        # Verify model update
        message = message_service.get_message(message_id)
        assert message['model'] == 'new-model'
    
    def test_message_deletion_flow(self, services):
        """
        Test deleting a message and its attachments.
        
        Validates that deletion properly removes all related data.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat and message with attachment
        chat_id = chat_service.create_chat(name="Test Chat")
        message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Message to delete"
        )
        
        # Add attachment
        attachment_id = message_service.add_attachment(
            message_id=message_id,
            file_type='image',
            file_name='test.png',
            file_content='content'
        )
        
        # Verify message and attachment exist
        assert message_service.get_message(message_id) is not None
        assert len(message_service.get_attachments(message_id)) == 1
        
        # Delete message
        deleted = message_service.delete_message(message_id)
        assert deleted is True
        
        # Verify message and attachments are gone
        assert message_service.get_message(message_id) is None
        assert len(message_service.get_attachments(message_id)) == 0
    
    def test_chat_state_preservation_on_error(self, services):
        """
        Test that chat state is preserved when message creation fails.
        
        Validates: Property 4 - Chat State Preservation on Error
        This ensures that if message creation fails, the chat remains
        in a consistent state and can be retried.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with initial message
        chat_id = chat_service.create_chat(name="Test Chat")
        first_message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="First message"
        )
        
        # Get initial state
        initial_messages = message_service.get_messages_for_chat(chat_id)
        initial_count = len(initial_messages)
        assert initial_count == 1
        
        # Try to create message with invalid role (should fail)
        try:
            message_service.create_message(
                chat_id=chat_id,
                role='invalid_role',
                content="This should fail"
            )
        except AlpacaError:
            pass  # Expected
        
        # Verify chat state is unchanged
        messages_after_error = message_service.get_messages_for_chat(chat_id)
        assert len(messages_after_error) == initial_count
        assert messages_after_error[0]['id'] == first_message_id
        
        # Verify we can still add valid messages (retry capability)
        retry_message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Retry message"
        )
        
        # Verify retry succeeded
        final_messages = message_service.get_messages_for_chat(chat_id)
        assert len(final_messages) == 2
        assert final_messages[1]['id'] == retry_message_id
    
    def test_concurrent_message_creation(self, services):
        """
        Test creating multiple messages in quick succession.
        
        Validates that the system can handle rapid message creation
        without data corruption.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Concurrent Test Chat")
        
        # Create multiple messages rapidly
        message_ids = []
        for i in range(10):
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='user' if i % 2 == 0 else 'assistant',
                content=f"Concurrent message {i}"
            )
            message_ids.append(msg_id)
        
        # Verify all messages were created
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == 10
        
        # Verify all message IDs are unique
        retrieved_ids = [msg['id'] for msg in messages]
        assert len(set(retrieved_ids)) == 10
        
        # Verify content integrity
        for i, msg in enumerate(messages):
            assert f"Concurrent message {i}" in msg['content']
    
    def test_message_search_integration(self, services):
        """
        Test message search functionality in the context of message flow.
        
        Validates that messages can be searched after being sent.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with multiple messages
        chat_id = chat_service.create_chat(name="Search Test Chat")
        
        message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Hello world"
        )
        message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Hello there"
        )
        message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Goodbye world"
        )
        
        # Search for "Hello"
        results = message_service.search_messages("Hello", chat_id=chat_id)
        assert len(results) == 2
        assert all('Hello' in msg['content'] or 'Hello' in msg['content'] for msg in results)
        
        # Search for "world"
        results = message_service.search_messages("world", chat_id=chat_id)
        assert len(results) == 2
        
        # Search for "Goodbye"
        results = message_service.search_messages("Goodbye", chat_id=chat_id)
        assert len(results) == 1
        assert results[0]['content'] == "Goodbye world"
    
    def test_empty_message_handling(self, services):
        """
        Test handling of empty or whitespace-only messages.
        
        Validates that empty messages are handled gracefully.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Empty Message Test")
        
        # Create message with empty content (should be allowed but stored as empty)
        message_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content=""
        )
        
        # Verify message was created with empty content
        message = message_service.get_message(message_id)
        assert message is not None
        assert message['content'] == ""
        
        # Create message with whitespace-only content
        message_id2 = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="   \n\t  "
        )
        
        # Verify message was created (content preserved as-is)
        message2 = message_service.get_message(message_id2)
        assert message2 is not None
        assert message2['content'] == "   \n\t  "
