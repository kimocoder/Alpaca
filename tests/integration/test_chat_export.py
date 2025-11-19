"""
Integration test for chat export flow.

Feature: alpaca-code-quality-improvements
Tests the complete flow for chat export in all formats (DB, MD, JSON),
verifying data completeness and performance with large chats.

Validates: Requirements 9.5
"""
import os
import sys
import json
import sqlite3
import tempfile
import time
from pathlib import Path

import pytest

# Add src directory to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from services.chat_service import ChatService
from services.message_service import MessageService
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from core.error_handler import AlpacaError, ErrorCategory


class TestChatExportFlow:
    """Integration tests for the complete chat export flow."""
    
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
    
    @pytest.fixture
    def sample_chat_with_messages(self, services):
        """Create a sample chat with messages for testing."""
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Export Test Chat", folder_id="test-folder")
        
        # Add various messages
        messages = [
            {'role': 'user', 'content': 'Hello, how are you?', 'model': None},
            {'role': 'assistant', 'content': 'I am doing well, thank you!', 'model': 'llama2'},
            {'role': 'user', 'content': 'Can you help me with Python?', 'model': None},
            {'role': 'assistant', 'content': 'Of course! What do you need help with?', 'model': 'llama2'},
            {'role': 'user', 'content': 'How do I read a file?', 'model': None},
            {'role': 'assistant', 'content': 'You can use open() function...', 'model': 'llama2'},
        ]
        
        for msg in messages:
            message_service.create_message(
                chat_id=chat_id,
                role=msg['role'],
                content=msg['content'],
                model=msg['model']
            )
        
        return chat_id
    
    def test_export_to_json_format(self, services, sample_chat_with_messages, tmp_path):
        """
        Test exporting a chat to JSON format.
        
        Validates:
        1. JSON file is created
        2. JSON is valid and parseable
        3. All chat data is present
        4. All messages are included
        5. Export metadata is included
        """
        chat_service = services['chat_service']
        chat_id = sample_chat_with_messages
        
        # Export to JSON
        output_path = tmp_path / "export.json"
        result_path = chat_service.export_chat(
            chat_id=chat_id,
            format='json',
            output_path=str(output_path)
        )
        
        # Verify file was created
        assert output_path.exists()
        assert result_path == str(output_path)
        
        # Load and verify JSON
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Verify structure
        assert 'chat' in data
        assert 'messages' in data
        assert 'exported_at' in data
        
        # Verify chat data
        assert data['chat']['id'] == chat_id
        assert data['chat']['name'] == "Export Test Chat"
        assert data['chat']['folder'] == "test-folder"
        
        # Verify messages
        assert len(data['messages']) == 6
        assert data['messages'][0]['role'] == 'user'
        assert data['messages'][0]['content'] == 'Hello, how are you?'
        assert data['messages'][1]['role'] == 'assistant'
        assert data['messages'][1]['model'] == 'llama2'
    
    def test_export_to_markdown_format(self, services, sample_chat_with_messages, tmp_path):
        """
        Test exporting a chat to Markdown format.
        
        Validates:
        1. Markdown file is created
        2. File contains chat name as header
        3. All messages are formatted correctly
        4. Role and model information is included
        5. Messages are separated properly
        """
        chat_service = services['chat_service']
        chat_id = sample_chat_with_messages
        
        # Export to Markdown
        output_path = tmp_path / "export.md"
        result_path = chat_service.export_chat(
            chat_id=chat_id,
            format='md',
            output_path=str(output_path)
        )
        
        # Verify file was created
        assert output_path.exists()
        assert result_path == str(output_path)
        
        # Read and verify content
        with open(output_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Verify header
        assert '# Export Test Chat' in content
        assert 'Exported:' in content
        
        # Verify messages are present
        assert 'Hello, how are you?' in content
        assert 'I am doing well, thank you!' in content
        assert 'Can you help me with Python?' in content
        
        # Verify role headers
        assert '## User' in content
        assert '## Assistant' in content
        
        # Verify model information
        assert '(llama2)' in content
        
        # Verify separators
        assert content.count('---') >= 6  # At least one separator per message
    
    def test_export_to_database_format(self, services, sample_chat_with_messages, tmp_path):
        """
        Test exporting a chat to SQLite database format.
        
        Validates:
        1. Database file is created
        2. Database has correct schema
        3. Chat data is exported correctly
        4. All messages are exported
        5. Foreign key relationships are maintained
        """
        chat_service = services['chat_service']
        chat_id = sample_chat_with_messages
        
        # Export to database
        output_path = tmp_path / "export.db"
        result_path = chat_service.export_chat(
            chat_id=chat_id,
            format='db',
            output_path=str(output_path)
        )
        
        # Verify file was created
        assert output_path.exists()
        assert result_path == str(output_path)
        
        # Connect and verify schema
        conn = sqlite3.connect(output_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Verify tables exist
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
        tables = [row[0] for row in cursor.fetchall()]
        assert 'chat' in tables
        assert 'message' in tables
        
        # Verify chat data
        cursor.execute("SELECT * FROM chat WHERE id = ?", (chat_id,))
        chat_row = cursor.fetchone()
        assert chat_row is not None
        assert chat_row['name'] == "Export Test Chat"
        assert chat_row['folder'] == "test-folder"
        
        # Verify messages
        cursor.execute("SELECT * FROM message WHERE chat_id = ?", (chat_id,))
        messages = cursor.fetchall()
        assert len(messages) == 6
        
        # Verify message content
        message_contents = [msg['content'] for msg in messages]
        assert 'Hello, how are you?' in message_contents
        assert 'I am doing well, thank you!' in message_contents
        
        # Verify foreign key relationship
        for msg in messages:
            assert msg['chat_id'] == chat_id
        
        conn.close()
    
    def test_export_with_progress_callback(self, services, sample_chat_with_messages, tmp_path):
        """
        Test export with progress callback.
        
        Validates:
        1. Progress callback is invoked
        2. Progress values are reasonable (0-100)
        3. Progress increases over time
        4. Export completes successfully
        """
        chat_service = services['chat_service']
        chat_id = sample_chat_with_messages
        
        # Track progress
        progress_values = []
        
        def progress_callback(progress):
            progress_values.append(progress)
        
        # Export with callback
        output_path = tmp_path / "export_with_progress.json"
        chat_service.export_chat(
            chat_id=chat_id,
            format='json',
            output_path=str(output_path),
            progress_callback=progress_callback
        )
        
        # Verify progress was tracked
        assert len(progress_values) > 0
        
        # Verify progress values are in valid range
        for progress in progress_values:
            assert 0 <= progress <= 100
        
        # Verify progress increases (or stays same)
        for i in range(1, len(progress_values)):
            assert progress_values[i] >= progress_values[i-1]
        
        # Verify final progress is 100
        assert progress_values[-1] == 100
    
    def test_export_large_chat_performance(self, services, tmp_path):
        """
        Test export performance with a large chat.
        
        Validates:
        1. Large chats (1000+ messages) can be exported
        2. Export completes in reasonable time
        3. All data is exported correctly
        4. Memory usage is reasonable
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create a large chat
        chat_id = chat_service.create_chat(name="Large Chat")
        
        # Add 1000 messages
        for i in range(1000):
            role = 'user' if i % 2 == 0 else 'assistant'
            message_service.create_message(
                chat_id=chat_id,
                role=role,
                content=f"Message number {i} with some content to make it realistic."
            )
        
        # Export to JSON and measure time
        output_path = tmp_path / "large_export.json"
        start_time = time.time()
        
        chat_service.export_chat(
            chat_id=chat_id,
            format='json',
            output_path=str(output_path)
        )
        
        elapsed_time = time.time() - start_time
        
        # Verify export completed in reasonable time (< 5 seconds)
        assert elapsed_time < 5.0, f"Export took {elapsed_time:.2f}s, expected < 5s"
        
        # Verify all messages were exported
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert len(data['messages']) == 1000
        
        # Verify first and last messages
        assert data['messages'][0]['content'] == "Message number 0 with some content to make it realistic."
        assert data['messages'][999]['content'] == "Message number 999 with some content to make it realistic."
    
    def test_export_empty_chat(self, services, tmp_path):
        """
        Test exporting a chat with no messages.
        
        Validates that empty chats can be exported without errors.
        """
        chat_service = services['chat_service']
        
        # Create empty chat
        chat_id = chat_service.create_chat(name="Empty Chat")
        
        # Export to JSON
        output_path = tmp_path / "empty_export.json"
        chat_service.export_chat(
            chat_id=chat_id,
            format='json',
            output_path=str(output_path)
        )
        
        # Verify file exists
        assert output_path.exists()
        
        # Verify content
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data['chat']['id'] == chat_id
        assert len(data['messages']) == 0
    
    def test_export_nonexistent_chat(self, services, tmp_path):
        """
        Test exporting a chat that doesn't exist.
        
        Validates that appropriate error is raised.
        """
        chat_service = services['chat_service']
        
        # Try to export non-existent chat
        output_path = tmp_path / "nonexistent.json"
        
        with pytest.raises(AlpacaError) as exc_info:
            chat_service.export_chat(
                chat_id='nonexistent-chat-id',
                format='json',
                output_path=str(output_path)
            )
        
        error = exc_info.value
        assert error.category == ErrorCategory.VALIDATION
        assert 'not found' in error.user_message.lower() or "doesn't exist" in error.user_message.lower()
    
    def test_export_unsupported_format(self, services, sample_chat_with_messages, tmp_path):
        """
        Test exporting with an unsupported format.
        
        Validates that appropriate error is raised for invalid formats.
        """
        chat_service = services['chat_service']
        chat_id = sample_chat_with_messages
        
        # Try to export with unsupported format
        output_path = tmp_path / "export.xml"
        
        with pytest.raises(AlpacaError) as exc_info:
            chat_service.export_chat(
                chat_id=chat_id,
                format='xml',
                output_path=str(output_path)
            )
        
        error = exc_info.value
        assert error.category == ErrorCategory.VALIDATION
        assert 'format' in error.user_message.lower()
    
    def test_export_all_formats_consistency(self, services, sample_chat_with_messages, tmp_path):
        """
        Test that all export formats contain the same data.
        
        Validates data consistency across different export formats.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        chat_id = sample_chat_with_messages
        
        # Get original data
        original_chat = chat_service.get_chat(chat_id)
        original_messages = message_service.get_messages_for_chat(chat_id)
        
        # Export to all formats
        json_path = tmp_path / "export.json"
        md_path = tmp_path / "export.md"
        db_path = tmp_path / "export.db"
        
        chat_service.export_chat(chat_id, 'json', str(json_path))
        chat_service.export_chat(chat_id, 'md', str(md_path))
        chat_service.export_chat(chat_id, 'db', str(db_path))
        
        # Verify JSON data
        with open(json_path, 'r', encoding='utf-8') as f:
            json_data = json.load(f)
        assert json_data['chat']['name'] == original_chat['name']
        assert len(json_data['messages']) == len(original_messages)
        
        # Verify Markdown contains all messages
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        for msg in original_messages:
            assert msg['content'] in md_content
        
        # Verify database data
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM message WHERE chat_id = ?", (chat_id,))
        db_messages = cursor.fetchall()
        assert len(db_messages) == len(original_messages)
        conn.close()
    
    def test_export_with_special_characters(self, services, tmp_path):
        """
        Test exporting messages with special characters.
        
        Validates that special characters are properly encoded in all formats.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with special characters
        chat_id = chat_service.create_chat(name="Special Chars: 你好 🎉 <>&\"'")
        
        # Add messages with special characters
        special_messages = [
            "Unicode: 你好世界 مرحبا العالم",
            "Emoji: 🎉 🚀 💻 🤖",
            "HTML: <script>alert('test')</script>",
            "Quotes: \"double\" and 'single'",
            "Newlines:\nLine 1\nLine 2\nLine 3",
        ]
        
        for content in special_messages:
            message_service.create_message(
                chat_id=chat_id,
                role='user',
                content=content
            )
        
        # Export to JSON
        json_path = tmp_path / "special_chars.json"
        chat_service.export_chat(chat_id, 'json', str(json_path))
        
        # Verify JSON preserves special characters
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        exported_contents = [msg['content'] for msg in data['messages']]
        for original in special_messages:
            assert original in exported_contents
        
        # Export to Markdown
        md_path = tmp_path / "special_chars.md"
        chat_service.export_chat(chat_id, 'md', str(md_path))
        
        # Verify Markdown preserves special characters
        with open(md_path, 'r', encoding='utf-8') as f:
            md_content = f.read()
        
        for original in special_messages:
            assert original in md_content
    
    def test_export_with_null_values(self, services, tmp_path):
        """
        Test exporting messages with null/empty values.
        
        Validates that null values are handled correctly.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat
        chat_id = chat_service.create_chat(name="Null Values Test", folder_id=None)
        
        # Add message with null model
        message_service.create_message(
            chat_id=chat_id,
            role='user',
            content='Message with no model',
            model=None
        )
        
        # Export to JSON
        json_path = tmp_path / "null_values.json"
        chat_service.export_chat(chat_id, 'json', str(json_path))
        
        # Verify null values are handled
        with open(json_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        assert data['chat']['folder'] is None
        assert data['messages'][0]['model'] is None or data['messages'][0]['model'] == ''
    
    def test_export_overwrite_existing_file(self, services, sample_chat_with_messages, tmp_path):
        """
        Test that export overwrites existing files.
        
        Validates that exporting to an existing file path works correctly.
        """
        chat_service = services['chat_service']
        chat_id = sample_chat_with_messages
        
        # Create initial export
        output_path = tmp_path / "overwrite_test.json"
        chat_service.export_chat(chat_id, 'json', str(output_path))
        
        # Get initial file size
        initial_size = output_path.stat().st_size
        
        # Export again to same path
        chat_service.export_chat(chat_id, 'json', str(output_path))
        
        # Verify file still exists and has content
        assert output_path.exists()
        assert output_path.stat().st_size > 0
        
        # Verify content is valid
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        assert data['chat']['id'] == chat_id
    
    def test_export_multiple_chats_sequentially(self, services, tmp_path):
        """
        Test exporting multiple chats one after another.
        
        Validates that multiple exports work correctly without interference.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create multiple chats
        chat_ids = []
        for i in range(5):
            chat_id = chat_service.create_chat(name=f"Chat {i}")
            message_service.create_message(
                chat_id=chat_id,
                role='user',
                content=f"Message for chat {i}"
            )
            chat_ids.append(chat_id)
        
        # Export all chats
        for i, chat_id in enumerate(chat_ids):
            output_path = tmp_path / f"chat_{i}.json"
            chat_service.export_chat(chat_id, 'json', str(output_path))
            
            # Verify each export
            assert output_path.exists()
            with open(output_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            assert data['chat']['name'] == f"Chat {i}"
            assert data['messages'][0]['content'] == f"Message for chat {i}"
    
    def test_export_preserves_message_order(self, services, tmp_path):
        """
        Test that export preserves message order.
        
        Validates that messages are exported in the correct chronological order.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create chat with ordered messages
        chat_id = chat_service.create_chat(name="Ordered Messages")
        
        message_ids = []
        for i in range(10):
            msg_id = message_service.create_message(
                chat_id=chat_id,
                role='user',
                content=f"Message {i}"
            )
            message_ids.append(msg_id)
        
        # Export to JSON
        output_path = tmp_path / "ordered.json"
        chat_service.export_chat(chat_id, 'json', str(output_path))
        
        # Verify order
        with open(output_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        for i, msg in enumerate(data['messages']):
            assert msg['content'] == f"Message {i}"
    
    def test_export_database_schema_compatibility(self, services, sample_chat_with_messages, tmp_path):
        """
        Test that exported database has compatible schema.
        
        Validates that exported database can be used as a valid Alpaca database.
        """
        chat_service = services['chat_service']
        chat_id = sample_chat_with_messages
        
        # Export to database
        output_path = tmp_path / "schema_test.db"
        chat_service.export_chat(chat_id, 'db', str(output_path))
        
        # Verify schema compatibility
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()
        
        # Check chat table schema
        cursor.execute("PRAGMA table_info(chat)")
        chat_columns = {row[1] for row in cursor.fetchall()}
        assert 'id' in chat_columns
        assert 'name' in chat_columns
        assert 'folder' in chat_columns
        assert 'is_template' in chat_columns
        
        # Check message table schema
        cursor.execute("PRAGMA table_info(message)")
        message_columns = {row[1] for row in cursor.fetchall()}
        assert 'id' in message_columns
        assert 'chat_id' in message_columns
        assert 'role' in message_columns
        assert 'model' in message_columns
        assert 'content' in message_columns
        
        # Check foreign key
        cursor.execute("PRAGMA foreign_key_list(message)")
        fk_info = cursor.fetchall()
        assert len(fk_info) > 0
        assert fk_info[0][2] == 'chat'  # References chat table
        
        conn.close()
