"""
Integration test for model switching flow.

Feature: alpaca-code-quality-improvements
Tests the complete flow for model selection persistence,
message generation with different models, and error handling
during model switches.

Validates: Requirements 9.3
"""
import os
import sys
import uuid
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch

import pytest

# Add src directory to path
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


class TestModelSwitching:
    """Integration tests for model switching flow."""
    
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
            CREATE TABLE instance (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                properties TEXT NOT NULL,
                pinned INTEGER DEFAULT 0
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
        chat_repo = ChatRepository(db_path=test_db)
        message_repo = MessageRepository(db_path=test_db)
        instance_repo = InstanceRepository(db_path=test_db)
        
        chat_service = ChatService(chat_repo=chat_repo, message_repo=message_repo)
        message_service = MessageService(message_repo=message_repo)
        model_service = ModelService(instance_repo=instance_repo)
        instance_service = InstanceService(instance_repo=instance_repo)
        
        return {
            'chat_service': chat_service,
            'message_service': message_service,
            'model_service': model_service,
            'instance_service': instance_service,
            'chat_repo': chat_repo,
            'message_repo': message_repo,
            'instance_repo': instance_repo
        }
    
    def test_model_selection_persistence(self, services):
        """
        Test that model selection persists across messages.
        
        Validates:
        1. Model can be set for a message
        2. Model is persisted to database
        3. Model can be retrieved with message
        4. Different messages can use different models
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create a chat
        chat_id = chat_service.create_chat(name="Model Test Chat")
        
        # Create first message with model A
        msg1_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Hello with model A",
            model='llama2:7b'
        )
        
        # Verify model was saved
        msg1 = message_service.get_message(msg1_id)
        assert msg1 is not None
        assert msg1['model'] == 'llama2:7b'
        
        # Create second message with model B
        msg2_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Response from model B",
            model='mistral:latest'
        )
        
        # Verify model was saved
        msg2 = message_service.get_message(msg2_id)
        assert msg2 is not None
        assert msg2['model'] == 'mistral:latest'
        
        # Verify both messages have correct models
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == 2
        assert messages[0]['model'] == 'llama2:7b'
        assert messages[1]['model'] == 'mistral:latest'
    
    def test_model_switching_between_messages(self, services):
        """
        Test switching models between consecutive messages.
        
        Validates that model changes are properly tracked
        across multiple message exchanges.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Model Switching Chat")
        
        # Simulate conversation with model switches
        models = ['llama2:7b', 'mistral:7b', 'codellama:13b', 'llama2:7b']
        message_ids = []
        
        for i, model in enumerate(models):
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='user' if i % 2 == 0 else 'assistant',
                content=f"Message {i} with {model}",
                model=model
            )
            message_ids.append(msg_id)
        
        # Verify all messages have correct models
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == 4
        
        for i, msg in enumerate(messages):
            assert msg['model'] == models[i]
            assert msg['id'] == message_ids[i]
    
    def test_message_generation_with_different_models(self, services):
        """
        Test generating messages with different models.
        
        Validates that the system can handle message generation
        with various model configurations.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Multi-Model Chat")
        
        # Test different model formats
        test_models = [
            'llama2',
            'llama2:7b',
            'llama2:13b-instruct',
            'mistral:latest',
            'codellama:7b-python',
            ''  # Empty model (default)
        ]
        
        for model in test_models:
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='assistant',
                content=f"Response from {model or 'default'}",
                model=model
            )
            
            # Verify message was created with correct model
            msg = message_service.get_message(msg_id)
            assert msg is not None
            assert msg['model'] == model
        
        # Verify all messages exist
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == len(test_models)
    
    def test_model_persistence_across_connections(self, services, test_db):
        """
        Test that model selection persists across database connections.
        
        Validates that model data is properly committed to the database
        and survives connection resets.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat and message with model
        chat_id = chat_service.create_chat(name="Persistence Test")
        msg_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Test message",
            model='llama2:13b'
        )
        
        # Create new service with fresh connection
        new_message_repo = MessageRepository(db_path=test_db)
        new_message_service = MessageService(message_repo=new_message_repo)
        
        # Verify model persisted
        msg = new_message_service.get_message(msg_id)
        assert msg is not None
        assert msg['model'] == 'llama2:13b'
    
    def test_model_update_after_creation(self, services):
        """
        Test updating the model of an existing message.
        
        Validates that model can be changed after message creation.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat and message
        chat_id = chat_service.create_chat(name="Model Update Test")
        msg_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Test message",
            model='llama2:7b'
        )
        
        # Verify initial model
        msg = message_service.get_message(msg_id)
        assert msg['model'] == 'llama2:7b'
        
        # Update model
        updated = message_service.update_message(
            message_id=msg_id,
            model='mistral:latest'
        )
        assert updated is True
        
        # Verify model was updated
        msg = message_service.get_message(msg_id)
        assert msg['model'] == 'mistral:latest'
    
    def test_error_handling_invalid_model_format(self, services):
        """
        Test error handling when using invalid model formats.
        
        Validates that the system handles invalid model names gracefully.
        Note: The system currently allows any string as a model name,
        so this test verifies that behavior.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Invalid Model Test")
        
        # Test with various potentially invalid formats
        # (Currently the system accepts any string)
        test_cases = [
            'invalid@model',
            'model with spaces',
            '123',
            'model/with/slashes',
            'very-long-model-name-that-might-cause-issues' * 10
        ]
        
        for model_name in test_cases:
            # Should not raise an error (system accepts any string)
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='assistant',
                content=f"Test with {model_name}",
                model=model_name
            )
            
            # Verify message was created
            msg = message_service.get_message(msg_id)
            assert msg is not None
            assert msg['model'] == model_name
    
    def test_model_switching_with_error_recovery(self, services):
        """
        Test that model switching can recover from errors.
        
        Validates that if a message creation fails, the next
        message with a different model can still succeed.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Error Recovery Test")
        
        # Create successful message with model A
        msg1_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="First message",
            model='llama2:7b'
        )
        
        # Try to create message with invalid role (should fail)
        try:
            message_service.create_message(
                chat_id=chat_id,
                role='invalid_role',
                content="This should fail",
                model='mistral:7b'
            )
            assert False, "Should have raised an error"
        except AlpacaError as e:
            assert e.category == ErrorCategory.VALIDATION
        
        # Create successful message with model B (recovery)
        msg2_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Recovery message",
            model='mistral:7b'
        )
        
        # Verify both successful messages exist with correct models
        messages = message_service.get_messages_for_chat(chat_id)
        assert len(messages) == 2
        assert messages[0]['id'] == msg1_id
        assert messages[0]['model'] == 'llama2:7b'
        assert messages[1]['id'] == msg2_id
        assert messages[1]['model'] == 'mistral:7b'
    
    def test_model_history_tracking(self, services):
        """
        Test tracking model usage history in a chat.
        
        Validates that we can retrieve which models were used
        in a conversation.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with multiple models
        chat_id = chat_service.create_chat(name="Model History Test")
        
        models_used = ['llama2:7b', 'mistral:7b', 'llama2:7b', 'codellama:13b']
        
        for i, model in enumerate(models_used):
            message_service.create_message(
                chat_id=chat_id,
                role='assistant',
                content=f"Message {i}",
                model=model
            )
        
        # Get all messages and extract unique models
        messages = message_service.get_messages_for_chat(chat_id)
        used_models = [msg['model'] for msg in messages]
        unique_models = list(dict.fromkeys(used_models))  # Preserve order
        
        # Verify model history
        assert used_models == models_used
        assert set(unique_models) == {'llama2:7b', 'mistral:7b', 'codellama:13b'}
        assert len(unique_models) == 3
    
    def test_empty_model_handling(self, services):
        """
        Test handling of messages with no model specified.
        
        Validates that messages can be created without a model
        and that empty model is properly stored and retrieved.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Empty Model Test")
        
        # Create message with empty model
        msg1_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Message without model",
            model=''
        )
        
        # Create message with None model (should be converted to empty string)
        msg2_id = message_service.create_message(
            chat_id=chat_id,
            role='user',
            content="Message with None model",
            model=None
        )
        
        # Verify both messages have empty model
        msg1 = message_service.get_message(msg1_id)
        msg2 = message_service.get_message(msg2_id)
        
        assert msg1['model'] == ''
        assert msg2['model'] == ''
    
    def test_model_switching_with_pagination(self, services):
        """
        Test model switching with paginated message retrieval.
        
        Validates that model information is preserved when
        loading messages in batches.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with many messages using different models
        chat_id = chat_service.create_chat(name="Pagination Test")
        
        models = ['llama2:7b', 'mistral:7b', 'codellama:13b']
        
        # Create 100 messages with rotating models
        for i in range(100):
            model = models[i % len(models)]
            message_service.create_message(
                chat_id=chat_id,
                role='assistant',
                content=f"Message {i}",
                model=model
            )
        
        # Load first batch
        batch1 = message_service.get_messages_for_chat(
            chat_id=chat_id,
            limit=50,
            offset=0
        )
        assert len(batch1) == 50
        
        # Verify models in first batch
        for i, msg in enumerate(batch1):
            expected_model = models[i % len(models)]
            assert msg['model'] == expected_model
        
        # Load second batch
        batch2 = message_service.get_messages_for_chat(
            chat_id=chat_id,
            limit=50,
            offset=50
        )
        assert len(batch2) == 50
        
        # Verify models in second batch
        for i, msg in enumerate(batch2):
            expected_model = models[(i + 50) % len(models)]
            assert msg['model'] == expected_model
    
    def test_model_search_filtering(self, services):
        """
        Test searching messages and verifying model information.
        
        Validates that search results include model information.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with messages from different models
        chat_id = chat_service.create_chat(name="Search Test")
        
        message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Hello from llama",
            model='llama2:7b'
        )
        message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Hello from mistral",
            model='mistral:7b'
        )
        message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Goodbye from llama",
            model='llama2:7b'
        )
        
        # Search for "Hello"
        results = message_service.search_messages("Hello", chat_id=chat_id)
        assert len(results) == 2
        
        # Verify model information is included in search results
        for msg in results:
            assert 'model' in msg
            assert msg['model'] in ['llama2:7b', 'mistral:7b']
    
    def test_concurrent_model_switches(self, services):
        """
        Test rapid model switching in quick succession.
        
        Validates that the system handles rapid model changes
        without data corruption.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Concurrent Switch Test")
        
        # Rapidly create messages with different models
        models = ['llama2:7b', 'mistral:7b', 'codellama:13b']
        message_ids = []
        
        for i in range(30):
            model = models[i % len(models)]
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='assistant',
                content=f"Rapid message {i}",
                model=model
            )
            message_ids.append((msg_id, model))
        
        # Verify all messages have correct models
        for msg_id, expected_model in message_ids:
            msg = message_service.get_message(msg_id)
            assert msg is not None
            assert msg['model'] == expected_model
    
    def test_model_deletion_with_messages(self, services):
        """
        Test that deleting messages preserves model information.
        
        Validates that model data is properly handled during
        message deletion operations.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with messages
        chat_id = chat_service.create_chat(name="Deletion Test")
        
        msg1_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Message 1",
            model='llama2:7b'
        )
        msg2_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Message 2",
            model='mistral:7b'
        )
        msg3_id = message_service.create_message(
            chat_id=chat_id,
            role='assistant',
            content="Message 3",
            model='codellama:13b'
        )
        
        # Delete middle message
        deleted = message_service.delete_message(msg2_id)
        assert deleted is True
        
        # Verify remaining messages still have correct models
        msg1 = message_service.get_message(msg1_id)
        msg3 = message_service.get_message(msg3_id)
        
        assert msg1['model'] == 'llama2:7b'
        assert msg3['model'] == 'codellama:13b'
        
        # Verify deleted message is gone
        assert message_service.get_message(msg2_id) is None
    
    def test_model_with_special_characters(self, services):
        """
        Test model names with special characters.
        
        Validates that model names with colons, hyphens, and
        other special characters are properly handled.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Special Chars Test")
        
        # Test various model name formats
        special_models = [
            'llama2:7b-instruct',
            'mistral:7b-v0.1',
            'codellama:13b-python-instruct',
            'model:tag-variant-v1.0',
            'model_with_underscores:latest'
        ]
        
        for model in special_models:
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='assistant',
                content=f"Test {model}",
                model=model
            )
            
            # Verify model was saved correctly
            msg = message_service.get_message(msg_id)
            assert msg['model'] == model
    
    def test_model_case_sensitivity(self, services):
        """
        Test that model names preserve case.
        
        Validates that model name case is preserved in storage
        and retrieval.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Case Test")
        
        # Test different cases
        models = [
            'Llama2:7B',
            'MISTRAL:LATEST',
            'CodeLlama:13b-Instruct',
            'lowercase:model',
            'MixedCase:Model'
        ]
        
        for model in models:
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='assistant',
                content=f"Test {model}",
                model=model
            )
            
            # Verify case is preserved
            msg = message_service.get_message(msg_id)
            assert msg['model'] == model
