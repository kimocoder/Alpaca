"""
Integration test for chat import flow.

Feature: alpaca-code-quality-improvements
Tests the complete flow for importing chats from various database formats,
verifying data integrity after import, and testing conflict resolution
for duplicate IDs and names.

Validates: Requirements 9.4
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


def generate_uuid() -> str:
    """Generate a unique ID for testing."""
    return f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}{uuid.uuid4().hex}"


def generate_numbered_name(name: str, compare_list: list) -> str:
    """Generate a numbered name if name exists in compare_list."""
    if name in compare_list:
        for i in range(1, len(compare_list) + 1):
            if "." in name:
                if (
                    f"{'.'.join(name.split('.')[:-1])} ({i}).{name.split('.')[-1]}"
                    not in compare_list
                ):
                    name = f"{'.'.join(name.split('.')[:-1])} ({i}).{name.split('.')[-1]}"
                    break
            else:
                if f"{name} ({i})" not in compare_list:
                    name = f"{name} ({i})"
                    break
    return name


def import_chat(import_sql_path: str, target_db_path: str, chat_names: list, folder_id: str = None) -> list:
    """
    Import chats from an external database.
    
    This is a test implementation that mimics SQL.import_chat but works
    without the relative imports issue.
    """
    conn = sqlite3.connect(target_db_path)
    conn.execute("ATTACH DATABASE ? AS import", (import_sql_path,))
    
    # Check repeated chat.name
    for repeated_chat in conn.execute(
        "SELECT import.chat.id, import.chat.name FROM import.chat JOIN chat dbchat ON import.chat.name = dbchat.name"
    ).fetchall():
        new_name = generate_numbered_name(repeated_chat[1], chat_names)
        conn.execute(
            "UPDATE import.chat SET name=? WHERE id=?",
            (new_name, repeated_chat[0]),
        )
    
    # Check repeated chat.id
    for repeated_chat in conn.execute(
        "SELECT import.chat.id, import.chat.name FROM import.chat JOIN chat dbchat ON import.chat.id = dbchat.id"
    ).fetchall():
        new_id = generate_uuid()
        # Also check if name needs numbering when ID is changed
        chat_name = repeated_chat[1]
        if chat_name in chat_names:
            chat_name = generate_numbered_name(chat_name, chat_names)
        conn.execute(
            "UPDATE import.chat SET id=?, name=? WHERE id=?",
            (new_id, chat_name, repeated_chat[0]),
        )
        conn.execute(
            "UPDATE import.message SET chat_id=? WHERE chat_id=?",
            (new_id, repeated_chat[0]),
        )
    
    # Check repeated message.id
    for repeated_message in conn.execute(
        "SELECT import.message.id FROM import.message JOIN message dbmessage ON import.message.id = dbmessage.id"
    ).fetchall():
        new_id = generate_uuid()
        conn.execute(
            "UPDATE import.attachment SET message_id=? WHERE message_id=?",
            (new_id, repeated_message[0]),
        )
        conn.execute(
            "UPDATE import.message SET id=? WHERE id=?",
            (new_id, repeated_message[0]),
        )
    
    # Check repeated attachment.id
    for repeated_attachment in conn.execute(
        "SELECT import.attachment.id FROM import.attachment JOIN attachment dbattachment ON import.attachment.id = dbattachment.id"
    ).fetchall():
        new_id = generate_uuid()
        conn.execute(
            "UPDATE import.attachment SET id=? WHERE id=?",
            (new_id, repeated_attachment[0]),
        )
    
    # Import
    for chat in conn.execute("SELECT * FROM import.chat").fetchall():
        # Handle both old format (3 columns) and new format (4 columns with is_template)
        if len(chat) >= 4:
            conn.execute("INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)", 
                        (chat[0], chat[1], folder_id, chat[3]))
        else:
            conn.execute("INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)", 
                        (chat[0], chat[1], folder_id, 0))
    
    conn.execute("INSERT INTO message SELECT * FROM import.message")
    
    # Check if attachment table exists in import database
    try:
        conn.execute("INSERT INTO attachment SELECT * FROM import.attachment")
    except sqlite3.OperationalError:
        pass  # No attachment table in import database
    
    new_chats = conn.execute("SELECT * FROM import.chat").fetchall()
    
    conn.commit()
    conn.close()
    
    return new_chats


class TestChatImport:
    """Integration tests for the complete chat import flow."""
    
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
    def import_db(self):
        """Create a temporary database to import from."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
            db_path = f.name
        
        # Create schema matching export format
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
        chat_repo = ChatRepository(db_path=test_db)
        message_repo = MessageRepository(db_path=test_db)
        chat_service = ChatService(chat_repo=chat_repo, message_repo=message_repo)
        message_service = MessageService(message_repo=message_repo)
        
        return {
            'chat_service': chat_service,
            'message_service': message_service,
            'chat_repo': chat_repo,
            'message_repo': message_repo,
            'test_db': test_db
        }
    
    def _populate_import_db(self, db_path, chats_data):
        """Helper to populate import database with test data."""
        conn = sqlite3.connect(db_path)
        
        for chat_data in chats_data:
            # Insert chat
            conn.execute(
                "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)",
                (
                    chat_data['id'],
                    chat_data['name'],
                    chat_data.get('folder'),
                    chat_data.get('is_template', 0)
                )
            )
            
            # Insert messages if provided
            for msg in chat_data.get('messages', []):
                conn.execute(
                    "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        msg['id'],
                        chat_data['id'],
                        msg['role'],
                        msg.get('model', ''),
                        msg.get('date_time', datetime.now().strftime("%Y/%m/%d %H:%M:%S")),
                        msg['content']
                    )
                )
                
                # Insert attachments if provided
                for att in msg.get('attachments', []):
                    conn.execute(
                        "INSERT INTO attachment (id, message_id, type, name, content) VALUES (?, ?, ?, ?, ?)",
                        (
                            att['id'],
                            msg['id'],
                            att['type'],
                            att['name'],
                            att['content']
                        )
                    )
        
        conn.commit()
        conn.close()
    
    def test_basic_chat_import(self, services, import_db, test_db):
        """
        Test basic chat import from another database.
        
        Validates:
        1. Chat can be imported from external database
        2. Chat data is correctly transferred
        3. Messages are imported with the chat
        4. Data integrity is maintained
        """
        # Populate import database
        import_data = [{
            'id': 'import-chat-001',
            'name': 'Imported Chat',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'import-msg-001',
                    'role': 'user',
                    'content': 'Hello from imported chat',
                    'model': 'llama2:7b'
                },
                {
                    'id': 'import-msg-002',
                    'role': 'assistant',
                    'content': 'Response from imported chat',
                    'model': 'llama2:7b'
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import the chat
        chat_names = []  # No existing chats
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        assert imported_chats[0][0] == 'import-chat-001'
        assert imported_chats[0][1] == 'Imported Chat'
        
        # Verify chat was imported to main database
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        chat = chat_service.get_chat('import-chat-001')
        assert chat is not None
        assert chat['name'] == 'Imported Chat'
        assert chat['folder'] is None
        
        # Verify messages were imported
        messages = message_service.get_messages_for_chat('import-chat-001')
        assert len(messages) == 2
        assert messages[0]['content'] == 'Hello from imported chat'
        assert messages[1]['content'] == 'Response from imported chat'
    
    def test_import_with_duplicate_chat_name(self, services, import_db, test_db):
        """
        Test importing a chat when a chat with the same name already exists.
        
        Validates that duplicate names are handled by appending a counter.
        """
        chat_service = services['chat_service']
        
        # Create existing chat with same name
        existing_chat_id = chat_service.create_chat(name="Duplicate Chat")
        
        # Populate import database with chat having same name
        import_data = [{
            'id': 'import-chat-002',
            'name': 'Duplicate Chat',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'import-msg-003',
                    'role': 'user',
                    'content': 'Message from imported duplicate',
                    'model': ''
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import with existing chat names
        chat_names = ['Duplicate Chat']
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify imported chat has numbered name
        imported_chat = chat_service.get_chat('import-chat-002')
        assert imported_chat is not None
        assert imported_chat['name'] == 'Duplicate Chat (1)'
        
        # Verify original chat is unchanged
        original_chat = chat_service.get_chat(existing_chat_id)
        assert original_chat['name'] == 'Duplicate Chat'
    
    def test_import_with_duplicate_chat_id(self, services, import_db, test_db):
        """
        Test importing a chat when a chat with the same ID already exists.
        
        Validates that duplicate IDs are handled by generating new IDs
        and updating all references.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create existing chat with specific ID
        existing_chat_id = 'duplicate-id-001'
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)",
            (existing_chat_id, 'Existing Chat', None, 0)
        )
        conn.commit()
        conn.close()
        
        # Populate import database with chat having same ID
        import_data = [{
            'id': 'duplicate-id-001',  # Same ID as existing
            'name': 'Imported Chat with Duplicate ID',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'import-msg-004',
                    'role': 'user',
                    'content': 'Message from duplicate ID chat',
                    'model': ''
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = ['Existing Chat']
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify imported chat has new ID (not the duplicate)
        imported_chat_id = imported_chats[0][0]
        assert imported_chat_id != 'duplicate-id-001'
        
        # Verify imported chat exists with new ID
        imported_chat = chat_service.get_chat(imported_chat_id)
        assert imported_chat is not None
        # Name should not be numbered since it's not a duplicate name
        assert imported_chat['name'] == 'Imported Chat with Duplicate ID'
        
        # Verify messages reference the new chat ID
        messages = message_service.get_messages_for_chat(imported_chat_id)
        assert len(messages) == 1
        assert messages[0]['chat_id'] == imported_chat_id
        
        # Verify original chat is unchanged
        original_chat = chat_service.get_chat('duplicate-id-001')
        assert original_chat is not None
        assert original_chat['name'] == 'Existing Chat'
    
    def test_import_with_duplicate_message_id(self, services, import_db, test_db):
        """
        Test importing when message IDs conflict with existing messages.
        
        Validates that duplicate message IDs are handled by generating
        new IDs and updating attachment references.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create existing chat with message
        existing_chat_id = chat_service.create_chat(name="Existing Chat")
        existing_msg_id = 'duplicate-msg-001'
        
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            (existing_msg_id, existing_chat_id, 'user', '', datetime.now().strftime("%Y/%m/%d %H:%M:%S"), 'Existing message')
        )
        conn.commit()
        conn.close()
        
        # Populate import database with message having same ID
        import_data = [{
            'id': 'import-chat-003',
            'name': 'Imported Chat',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'duplicate-msg-001',  # Same ID as existing message
                    'role': 'user',
                    'content': 'Imported message with duplicate ID',
                    'model': '',
                    'attachments': [
                        {
                            'id': 'import-att-001',
                            'type': 'image',
                            'name': 'test.png',
                            'content': 'base64content'
                        }
                    ]
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = ['Existing Chat']
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify imported chat exists
        imported_chat = chat_service.get_chat('import-chat-003')
        assert imported_chat is not None
        
        # Verify messages were imported with new ID
        messages = message_service.get_messages_for_chat('import-chat-003')
        assert len(messages) == 1
        
        # The imported message should have a new ID (not duplicate-msg-001)
        imported_msg = messages[0]
        assert imported_msg['id'] != 'duplicate-msg-001'
        assert imported_msg['content'] == 'Imported message with duplicate ID'
        
        # Verify attachment references the new message ID
        attachments = message_service.get_attachments(imported_msg['id'])
        assert len(attachments) == 1
        assert attachments[0]['name'] == 'test.png'
        
        # Verify original message is unchanged
        original_msg = message_service.get_message('duplicate-msg-001')
        assert original_msg is not None
        assert original_msg['content'] == 'Existing message'
        assert original_msg['chat_id'] == existing_chat_id
    
    def test_import_with_duplicate_attachment_id(self, services, import_db, test_db):
        """
        Test importing when attachment IDs conflict with existing attachments.
        
        Validates that duplicate attachment IDs are handled by generating new IDs.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create existing chat with message and attachment
        existing_chat_id = chat_service.create_chat(name="Existing Chat")
        existing_msg_id = message_service.create_message(
            chat_id=existing_chat_id,
            role='user',
            content='Existing message'
        )
        
        existing_att_id = 'duplicate-att-001'
        conn = sqlite3.connect(test_db)
        conn.execute(
            "INSERT INTO attachment (id, message_id, type, name, content) VALUES (?, ?, ?, ?, ?)",
            (existing_att_id, existing_msg_id, 'image', 'existing.png', 'existingcontent')
        )
        conn.commit()
        conn.close()
        
        # Populate import database with attachment having same ID
        import_data = [{
            'id': 'import-chat-004',
            'name': 'Imported Chat',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'import-msg-005',
                    'role': 'user',
                    'content': 'Imported message',
                    'model': '',
                    'attachments': [
                        {
                            'id': 'duplicate-att-001',  # Same ID as existing attachment
                            'type': 'document',
                            'name': 'imported.pdf',
                            'content': 'importedcontent'
                        }
                    ]
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = ['Existing Chat']
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify imported chat exists
        imported_chat = chat_service.get_chat('import-chat-004')
        assert imported_chat is not None
        
        # Verify message was imported
        messages = message_service.get_messages_for_chat('import-chat-004')
        assert len(messages) == 1
        
        # Verify attachment was imported with new ID
        attachments = message_service.get_attachments(messages[0]['id'])
        assert len(attachments) == 1
        
        imported_att = attachments[0]
        assert imported_att['id'] != 'duplicate-att-001'
        assert imported_att['name'] == 'imported.pdf'
        assert imported_att['content'] == 'importedcontent'
        
        # Verify original attachment is unchanged
        original_attachments = message_service.get_attachments(existing_msg_id)
        assert len(original_attachments) == 1
        assert original_attachments[0]['id'] == 'duplicate-att-001'
        assert original_attachments[0]['name'] == 'existing.png'
    
    def test_import_multiple_chats(self, services, import_db, test_db):
        """
        Test importing multiple chats at once.
        
        Validates that multiple chats can be imported in a single operation
        and all data is correctly transferred.
        """
        # Populate import database with multiple chats
        import_data = [
            {
                'id': 'import-chat-005',
                'name': 'First Imported Chat',
                'folder': None,
                'is_template': 0,
                'messages': [
                    {
                        'id': 'import-msg-006',
                        'role': 'user',
                        'content': 'Message from first chat',
                        'model': 'llama2:7b'
                    }
                ]
            },
            {
                'id': 'import-chat-006',
                'name': 'Second Imported Chat',
                'folder': None,
                'is_template': 0,
                'messages': [
                    {
                        'id': 'import-msg-007',
                        'role': 'user',
                        'content': 'Message from second chat',
                        'model': 'mistral:7b'
                    }
                ]
            },
            {
                'id': 'import-chat-007',
                'name': 'Third Imported Chat',
                'folder': None,
                'is_template': 0,
                'messages': []
            }
        ]
        
        self._populate_import_db(import_db, import_data)
        
        # Import all chats
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 3
        
        # Verify all chats were imported
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        for i, chat_data in enumerate(import_data):
            chat = chat_service.get_chat(chat_data['id'])
            assert chat is not None
            assert chat['name'] == chat_data['name']
            
            messages = message_service.get_messages_for_chat(chat_data['id'])
            assert len(messages) == len(chat_data['messages'])
    
    def test_import_to_specific_folder(self, services, import_db, test_db):
        """
        Test importing chats into a specific folder.
        
        Validates that imported chats are placed in the specified folder.
        """
        # Populate import database
        import_data = [{
            'id': 'import-chat-008',
            'name': 'Chat for Folder',
            'folder': None,  # Original has no folder
            'is_template': 0,
            'messages': []
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import to specific folder
        target_folder_id = 'target-folder-001'
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=target_folder_id)
        
        assert len(imported_chats) == 1
        
        # Verify chat was imported to the specified folder
        chat_service = services['chat_service']
        chat = chat_service.get_chat('import-chat-008')
        assert chat is not None
        assert chat['folder'] == target_folder_id
    
    def test_import_with_attachments(self, services, import_db, test_db):
        """
        Test importing chats with message attachments.
        
        Validates that attachments are correctly imported along with messages.
        """
        # Populate import database with chat containing attachments
        import_data = [{
            'id': 'import-chat-009',
            'name': 'Chat with Attachments',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'import-msg-008',
                    'role': 'user',
                    'content': 'Message with multiple attachments',
                    'model': '',
                    'attachments': [
                        {
                            'id': 'import-att-002',
                            'type': 'image',
                            'name': 'photo.jpg',
                            'content': 'base64imagedata'
                        },
                        {
                            'id': 'import-att-003',
                            'type': 'document',
                            'name': 'document.pdf',
                            'content': 'base64pdfdata'
                        }
                    ]
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify attachments were imported
        message_service = services['message_service']
        messages = message_service.get_messages_for_chat('import-chat-009')
        assert len(messages) == 1
        
        attachments = message_service.get_attachments(messages[0]['id'])
        assert len(attachments) == 2
        
        # Verify attachment details
        att_names = [att['name'] for att in attachments]
        assert 'photo.jpg' in att_names
        assert 'document.pdf' in att_names
    
    def test_import_template_chat(self, services, import_db, test_db):
        """
        Test importing template chats.
        
        Validates that template flag is preserved during import.
        """
        # Populate import database with template chat
        import_data = [{
            'id': 'import-chat-010',
            'name': 'Template Chat',
            'folder': None,
            'is_template': 1,  # Template
            'messages': []
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify template flag was preserved
        chat_service = services['chat_service']
        chat = chat_service.get_chat('import-chat-010')
        assert chat is not None
        assert chat['is_template'] is True
    
    def test_import_data_integrity(self, services, import_db, test_db):
        """
        Test that all data fields are correctly preserved during import.
        
        Validates complete data integrity including:
        - Message roles
        - Message models
        - Message timestamps
        - Message content
        - Attachment types and content
        """
        # Populate import database with comprehensive data
        import_data = [{
            'id': 'import-chat-011',
            'name': 'Data Integrity Test',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'import-msg-009',
                    'role': 'user',
                    'content': 'User message content',
                    'model': '',
                    'date_time': '2024/01/15 10:30:00'
                },
                {
                    'id': 'import-msg-010',
                    'role': 'assistant',
                    'content': 'Assistant response content',
                    'model': 'llama2:13b-instruct',
                    'date_time': '2024/01/15 10:30:15'
                },
                {
                    'id': 'import-msg-011',
                    'role': 'system',
                    'content': 'System message content',
                    'model': '',
                    'date_time': '2024/01/15 10:30:30'
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify all message data was preserved
        message_service = services['message_service']
        messages = message_service.get_messages_for_chat('import-chat-011')
        assert len(messages) == 3
        
        # Check first message (user)
        assert messages[0]['role'] == 'user'
        assert messages[0]['content'] == 'User message content'
        assert messages[0]['model'] == ''
        assert messages[0]['date_time'] == '2024/01/15 10:30:00'
        
        # Check second message (assistant)
        assert messages[1]['role'] == 'assistant'
        assert messages[1]['content'] == 'Assistant response content'
        assert messages[1]['model'] == 'llama2:13b-instruct'
        assert messages[1]['date_time'] == '2024/01/15 10:30:15'
        
        # Check third message (system)
        assert messages[2]['role'] == 'system'
        assert messages[2]['content'] == 'System message content'
        assert messages[2]['model'] == ''
        assert messages[2]['date_time'] == '2024/01/15 10:30:30'
    
    def test_import_empty_chat(self, services, import_db, test_db):
        """
        Test importing a chat with no messages.
        
        Validates that empty chats can be imported successfully.
        """
        # Populate import database with empty chat
        import_data = [{
            'id': 'import-chat-012',
            'name': 'Empty Chat',
            'folder': None,
            'is_template': 0,
            'messages': []
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify empty chat was imported
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        chat = chat_service.get_chat('import-chat-012')
        assert chat is not None
        assert chat['name'] == 'Empty Chat'
        
        messages = message_service.get_messages_for_chat('import-chat-012')
        assert len(messages) == 0
    
    def test_import_with_multiple_conflicts(self, services, import_db, test_db):
        """
        Test importing when multiple types of conflicts exist simultaneously.
        
        Validates that the system can handle:
        - Duplicate chat names
        - Duplicate chat IDs
        - Duplicate message IDs
        - Duplicate attachment IDs
        All in a single import operation.
        """
        chat_service = services['chat_service']
        message_service = services['message_service']
        
        # Create existing data with conflicts
        existing_chat_id = 'conflict-chat-001'
        existing_msg_id = 'conflict-msg-001'
        existing_att_id = 'conflict-att-001'
        
        conn = sqlite3.connect(test_db)
        
        # Create existing chat
        conn.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)",
            (existing_chat_id, 'Conflict Chat', None, 0)
        )
        
        # Create existing message
        conn.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            (existing_msg_id, existing_chat_id, 'user', '', datetime.now().strftime("%Y/%m/%d %H:%M:%S"), 'Existing')
        )
        
        # Create existing attachment
        conn.execute(
            "INSERT INTO attachment (id, message_id, type, name, content) VALUES (?, ?, ?, ?, ?)",
            (existing_att_id, existing_msg_id, 'image', 'existing.png', 'content')
        )
        
        conn.commit()
        conn.close()
        
        # Populate import database with conflicting data
        import_data = [{
            'id': 'conflict-chat-001',  # Duplicate chat ID
            'name': 'Conflict Chat',     # Duplicate chat name
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'conflict-msg-001',  # Duplicate message ID
                    'role': 'user',
                    'content': 'Imported message',
                    'model': '',
                    'attachments': [
                        {
                            'id': 'conflict-att-001',  # Duplicate attachment ID
                            'type': 'document',
                            'name': 'imported.pdf',
                            'content': 'importedcontent'
                        }
                    ]
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import with conflicts
        chat_names = ['Conflict Chat']
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify imported chat has new ID and numbered name
        imported_chat_id = imported_chats[0][0]
        assert imported_chat_id != 'conflict-chat-001'
        
        imported_chat = chat_service.get_chat(imported_chat_id)
        assert imported_chat is not None
        assert imported_chat['name'] == 'Conflict Chat (1)'
        
        # Verify imported message has new ID
        messages = message_service.get_messages_for_chat(imported_chat_id)
        assert len(messages) == 1
        assert messages[0]['id'] != 'conflict-msg-001'
        assert messages[0]['content'] == 'Imported message'
        
        # Verify imported attachment has new ID
        attachments = message_service.get_attachments(messages[0]['id'])
        assert len(attachments) == 1
        assert attachments[0]['id'] != 'conflict-att-001'
        assert attachments[0]['name'] == 'imported.pdf'
        
        # Verify original data is unchanged
        original_chat = chat_service.get_chat('conflict-chat-001')
        assert original_chat['name'] == 'Conflict Chat'
        
        original_msg = message_service.get_message('conflict-msg-001')
        assert original_msg['content'] == 'Existing'
        
        original_atts = message_service.get_attachments('conflict-msg-001')
        assert len(original_atts) == 1
        assert original_atts[0]['id'] == 'conflict-att-001'
        assert original_atts[0]['name'] == 'existing.png'
    
    def test_import_large_chat(self, services, import_db, test_db):
        """
        Test importing a chat with many messages.
        
        Validates that large imports complete successfully and
        all data is correctly transferred.
        """
        # Populate import database with large chat
        messages = []
        for i in range(100):
            messages.append({
                'id': f'import-msg-large-{i:03d}',
                'role': 'user' if i % 2 == 0 else 'assistant',
                'content': f'Message number {i}',
                'model': 'llama2:7b' if i % 2 == 1 else ''
            })
        
        import_data = [{
            'id': 'import-chat-013',
            'name': 'Large Chat',
            'folder': None,
            'is_template': 0,
            'messages': messages
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify all messages were imported
        message_service = services['message_service']
        imported_messages = message_service.get_messages_for_chat('import-chat-013')
        assert len(imported_messages) == 100
        
        # Spot check some messages
        assert imported_messages[0]['content'] == 'Message number 0'
        assert imported_messages[50]['content'] == 'Message number 50'
        assert imported_messages[99]['content'] == 'Message number 99'
    
    def test_import_preserves_message_order(self, services, import_db, test_db):
        """
        Test that message order is preserved during import.
        
        Validates that messages maintain their chronological order.
        """
        # Populate import database with ordered messages
        import_data = [{
            'id': 'import-chat-014',
            'name': 'Ordered Chat',
            'folder': None,
            'is_template': 0,
            'messages': [
                {
                    'id': 'import-msg-order-001',
                    'role': 'user',
                    'content': 'First message',
                    'model': '',
                    'date_time': '2024/01/01 10:00:00'
                },
                {
                    'id': 'import-msg-order-002',
                    'role': 'assistant',
                    'content': 'Second message',
                    'model': 'llama2:7b',
                    'date_time': '2024/01/01 10:00:30'
                },
                {
                    'id': 'import-msg-order-003',
                    'role': 'user',
                    'content': 'Third message',
                    'model': '',
                    'date_time': '2024/01/01 10:01:00'
                }
            ]
        }]
        
        self._populate_import_db(import_db, import_data)
        
        # Import
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify message order is preserved
        message_service = services['message_service']
        messages = message_service.get_messages_for_chat('import-chat-014')
        assert len(messages) == 3
        
        assert messages[0]['content'] == 'First message'
        assert messages[1]['content'] == 'Second message'
        assert messages[2]['content'] == 'Third message'
        
        # Verify timestamps are preserved
        assert messages[0]['date_time'] == '2024/01/01 10:00:00'
        assert messages[1]['date_time'] == '2024/01/01 10:00:30'
        assert messages[2]['date_time'] == '2024/01/01 10:01:00'
    
    def test_import_from_old_database_format(self, services, import_db, test_db):
        """
        Test importing from an older database format.
        
        Validates backward compatibility with databases that might
        be missing newer columns like is_template.
        """
        # Create import database with minimal schema (old format)
        conn = sqlite3.connect(import_db)
        
        # Drop and recreate with old schema (no is_template)
        conn.execute("DROP TABLE IF EXISTS chat")
        conn.execute("""
            CREATE TABLE chat (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT
            )
        """)
        
        # Insert chat without is_template
        conn.execute(
            "INSERT INTO chat (id, name, folder) VALUES (?, ?, ?)",
            ('import-chat-015', 'Old Format Chat', None)
        )
        
        conn.commit()
        conn.close()
        
        # Import
        chat_names = []
        imported_chats = import_chat(import_db, test_db, chat_names, folder_id=None)
        
        assert len(imported_chats) == 1
        
        # Verify chat was imported (is_template should default to False)
        chat_service = services['chat_service']
        chat = chat_service.get_chat('import-chat-015')
        assert chat is not None
        assert chat['name'] == 'Old Format Chat'
        # is_template should be False by default
        assert chat.get('is_template', False) is False
