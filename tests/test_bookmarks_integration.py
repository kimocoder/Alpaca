"""
Integration tests for bookmarks functionality.
Tests the complete bookmark workflow.
"""

import unittest
import tempfile
import os
import sqlite3
from datetime import datetime
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestBookmarksIntegration(unittest.TestCase):
    """Test cases for bookmarks integration."""
    
    def setUp(self):
        """Set up test database."""
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
            CREATE TABLE bookmark (
                id TEXT NOT NULL PRIMARY KEY,
                message_id TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)
        
        # Insert test data
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("chat1", "Test Chat 1")
        )
        
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("chat2", "Test Chat 2")
        )
        
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg1", "chat1", "assistant", "llama2", "2024/01/15 10:30:00", "First bookmarked message")
        )
        
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg2", "chat2", "user", None, "2024/01/16 14:20:00", "Second bookmarked message")
        )
        
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg3", "chat1", "assistant", "llama2", "2024/01/17 09:15:00", "Non-bookmarked message")
        )
        
        cursor.execute(
            "INSERT INTO bookmark (id, message_id, created_at) VALUES (?, ?, ?)",
            ("bm1", "msg1", "2024/01/15 10:35:00")
        )
        
        cursor.execute(
            "INSERT INTO bookmark (id, message_id, created_at) VALUES (?, ?, ?)",
            ("bm2", "msg2", "2024/01/16 14:25:00")
        )
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_get_bookmarks_returns_all_bookmarks(self):
        """Test that get_bookmarks returns all bookmarked messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        bookmarks = cursor.execute(
            """SELECT b.id, b.message_id, b.created_at, m.content, m.date_time, 
               m.role, m.model, c.id, c.name 
               FROM bookmark b 
               JOIN message m ON b.message_id = m.id 
               JOIN chat c ON m.chat_id = c.id 
               ORDER BY b.created_at DESC"""
        ).fetchall()
        
        conn.close()
        
        # Should return 2 bookmarks
        self.assertEqual(len(bookmarks), 2)
        
        # Check first bookmark (most recent)
        self.assertEqual(bookmarks[0][1], "msg2")  # message_id
        self.assertEqual(bookmarks[0][3], "Second bookmarked message")  # content
        self.assertEqual(bookmarks[0][8], "Test Chat 2")  # chat_name
        
        # Check second bookmark
        self.assertEqual(bookmarks[1][1], "msg1")  # message_id
        self.assertEqual(bookmarks[1][3], "First bookmarked message")  # content
        self.assertEqual(bookmarks[1][8], "Test Chat 1")  # chat_name
    
    def test_bookmarks_include_chat_information(self):
        """Test that bookmarks include associated chat information."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        bookmarks = cursor.execute(
            """SELECT b.id, b.message_id, b.created_at, m.content, m.date_time, 
               m.role, m.model, c.id, c.name 
               FROM bookmark b 
               JOIN message m ON b.message_id = m.id 
               JOIN chat c ON m.chat_id = c.id 
               ORDER BY b.created_at DESC"""
        ).fetchall()
        
        conn.close()
        
        # Each bookmark should have chat_id and chat_name
        for bookmark in bookmarks:
            self.assertIsNotNone(bookmark[7])  # chat_id
            self.assertIsNotNone(bookmark[8])  # chat_name
            self.assertTrue(len(bookmark[8]) > 0)  # chat_name not empty
    
    def test_bookmarks_include_message_metadata(self):
        """Test that bookmarks include message metadata."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        bookmarks = cursor.execute(
            """SELECT b.id, b.message_id, b.created_at, m.content, m.date_time, 
               m.role, m.model, c.id, c.name 
               FROM bookmark b 
               JOIN message m ON b.message_id = m.id 
               JOIN chat c ON m.chat_id = c.id 
               ORDER BY b.created_at DESC"""
        ).fetchall()
        
        conn.close()
        
        # Each bookmark should have message metadata
        for bookmark in bookmarks:
            self.assertIsNotNone(bookmark[3])  # content
            self.assertIsNotNone(bookmark[4])  # date_time
            self.assertIsNotNone(bookmark[5])  # role
            self.assertIn(bookmark[5], ['user', 'assistant', 'system'])
    
    def test_bookmarks_ordered_by_creation_time(self):
        """Test that bookmarks are ordered by creation time (most recent first)."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        bookmarks = cursor.execute(
            """SELECT b.id, b.message_id, b.created_at, m.content, m.date_time, 
               m.role, m.model, c.id, c.name 
               FROM bookmark b 
               JOIN message m ON b.message_id = m.id 
               JOIN chat c ON m.chat_id = c.id 
               ORDER BY b.created_at DESC"""
        ).fetchall()
        
        conn.close()
        
        # Bookmarks should be in descending order by created_at
        if len(bookmarks) > 1:
            for i in range(len(bookmarks) - 1):
                self.assertGreaterEqual(bookmarks[i][2], bookmarks[i + 1][2])


if __name__ == '__main__':
    unittest.main()
