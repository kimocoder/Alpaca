"""
Unit tests for the ExportService class.
Tests export functionality for Markdown and JSON formats.
"""

import unittest
import tempfile
import os
import sqlite3
import json
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.export import ExportService


class TestExportService(unittest.TestCase):
    """Test cases for ExportService functionality."""
    
    def setUp(self):
        """Set up a temporary database for testing."""
        # Create a temporary database
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        # Create the database schema
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute("""
            CREATE TABLE chat (
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT,
                is_template INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE message (
                id TEXT NOT NULL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT,
                date_time DATETIME NOT NULL,
                content TEXT NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE attachment (
                id TEXT NOT NULL PRIMARY KEY,
                message_id TEXT NOT NULL,
                type TEXT NOT NULL,
                name TEXT NOT NULL,
                content TEXT NOT NULL
            )
        """)
        
        # Insert test data
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("chat1", "Test Chat")
        )
        
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg1", "chat1", "user", None, "2024/01/15 10:30:00", "Hello, how are you?")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg2", "chat1", "assistant", "llama2", "2024/01/15 10:30:15", "I'm doing well, thank you!")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg3", "chat1", "user", None, "2024/01/15 10:31:00", "```python\nprint('Hello World')\n```")
        )
        
        # Insert attachment
        cursor.execute(
            "INSERT INTO attachment (id, message_id, type, name, content) VALUES (?, ?, ?, ?, ?)",
            ("att1", "msg1", "image", "test.png", "base64encodedcontent")
        )
        
        conn.commit()
        conn.close()
        
        # Create export service with custom db path
        self.export_service = ExportService(db_path=self.db_path)
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_export_to_markdown_basic(self):
        """Test basic Markdown export functionality."""
        markdown = self.export_service.export_to_markdown("chat1")
        
        # Check that markdown contains expected elements
        self.assertIn("# Test Chat", markdown)
        self.assertIn("## User", markdown)
        self.assertIn("## Assistant", markdown)
        self.assertIn("Hello, how are you?", markdown)
        self.assertIn("I'm doing well, thank you!", markdown)
    
    def test_export_to_markdown_preserves_code_blocks(self):
        """Test that Markdown export preserves code blocks."""
        markdown = self.export_service.export_to_markdown("chat1")
        
        # Check that code blocks are preserved
        self.assertIn("```python", markdown)
        self.assertIn("print('Hello World')", markdown)
        self.assertIn("```", markdown)
    
    def test_export_to_markdown_includes_model_name(self):
        """Test that Markdown export includes model names when available."""
        markdown = self.export_service.export_to_markdown("chat1")
        
        # Check that model name is included
        self.assertIn("llama2", markdown)
    
    def test_export_to_markdown_includes_timestamps(self):
        """Test that Markdown export includes timestamps."""
        markdown = self.export_service.export_to_markdown("chat1")
        
        # Check that timestamps are included
        self.assertIn("2024/01/15", markdown)
    
    def test_export_to_markdown_nonexistent_chat(self):
        """Test that exporting nonexistent chat raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.export_service.export_to_markdown("nonexistent")
        
        self.assertIn("not found", str(context.exception))
    
    def test_export_to_json_basic(self):
        """Test basic JSON export functionality."""
        json_str = self.export_service.export_to_json("chat1")
        data = json.loads(json_str)
        
        # Check structure
        self.assertIn("chat", data)
        self.assertIn("messages", data)
        self.assertEqual(data["chat"]["id"], "chat1")
        self.assertEqual(data["chat"]["name"], "Test Chat")
        self.assertEqual(len(data["messages"]), 3)
    
    def test_export_to_json_includes_metadata(self):
        """Test that JSON export includes metadata when requested."""
        json_str = self.export_service.export_to_json("chat1", include_metadata=True)
        data = json.loads(json_str)
        
        # Check metadata
        self.assertIn("export_metadata", data)
        self.assertIn("exported_at", data["export_metadata"])
        
        # Check message metadata
        for message in data["messages"]:
            self.assertIn("timestamp", message)
            if message["role"] == "assistant":
                self.assertIn("model", message)
    
    def test_export_to_json_excludes_metadata(self):
        """Test that JSON export excludes metadata when not requested."""
        json_str = self.export_service.export_to_json("chat1", include_metadata=False)
        data = json.loads(json_str)
        
        # Check that export metadata is not present
        self.assertNotIn("export_metadata", data)
        
        # Check that message metadata is not present
        for message in data["messages"]:
            self.assertNotIn("timestamp", message)
            self.assertNotIn("model", message)
    
    def test_export_to_json_includes_attachments(self):
        """Test that JSON export includes attachments."""
        json_str = self.export_service.export_to_json("chat1")
        data = json.loads(json_str)
        
        # Find message with attachment
        message_with_attachment = None
        for message in data["messages"]:
            if message["id"] == "msg1":
                message_with_attachment = message
                break
        
        self.assertIsNotNone(message_with_attachment)
        self.assertIn("attachments", message_with_attachment)
        self.assertEqual(len(message_with_attachment["attachments"]), 1)
        self.assertEqual(message_with_attachment["attachments"][0]["name"], "test.png")
    
    def test_export_to_json_nonexistent_chat(self):
        """Test that exporting nonexistent chat raises ValueError."""
        with self.assertRaises(ValueError) as context:
            self.export_service.export_to_json("nonexistent")
        
        self.assertIn("not found", str(context.exception))
    
    def test_get_chat_list(self):
        """Test getting list of available chats."""
        chats = self.export_service.get_chat_list()
        
        self.assertEqual(len(chats), 1)
        self.assertEqual(chats[0]["id"], "chat1")
        self.assertEqual(chats[0]["name"], "Test Chat")


if __name__ == '__main__':
    unittest.main()
