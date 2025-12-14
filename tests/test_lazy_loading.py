"""
Tests for lazy loading functionality in chat messages.
Tests the SQL functions for paginated message retrieval.
"""

import unittest
import sqlite3
import os
import tempfile


class TestLazyLoadingSQL(unittest.TestCase):
    """Test lazy loading SQL functions."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.db_path = self.temp_db.name
        self.temp_db.close()
        
        # Initialize database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS chat (
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT,
                is_template INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS message (
                id TEXT NOT NULL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT,
                date_time TEXT NOT NULL,
                content TEXT NOT NULL,
                FOREIGN KEY (chat_id) REFERENCES chat(id)
            )
        """)
        
        # Insert test chat
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("test_chat", "Test Chat")
        )
        
        # Insert 100 test messages
        for i in range(100):
            cursor.execute(
                "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
                (f"msg_{i}", "test_chat", "user" if i % 2 == 0 else "assistant", 
                 "llama2" if i % 2 == 1 else None, 
                 f"2024/01/01 {i:02d}:00:00", 
                 f"Test message {i}")
            )
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_get_message_count(self):
        """Test that message count query works correctly."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        count = cursor.execute(
            "SELECT COUNT(*) FROM message WHERE chat_id=?",
            ("test_chat",)
        ).fetchone()[0]
        
        conn.close()
        
        self.assertEqual(count, 100)
    
    def test_get_messages_paginated_first_batch(self):
        """Test getting the first batch of messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        messages = cursor.execute(
            "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC LIMIT ? OFFSET ?",
            ("test_chat", 10, 0)
        ).fetchall()
        
        conn.close()
        
        self.assertEqual(len(messages), 10)
        # First message should be msg_0
        self.assertEqual(messages[0][0], "msg_0")
        self.assertEqual(messages[0][4], "Test message 0")
    
    def test_get_messages_paginated_second_batch(self):
        """Test getting the second batch of messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        messages = cursor.execute(
            "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC LIMIT ? OFFSET ?",
            ("test_chat", 10, 10)
        ).fetchall()
        
        conn.close()
        
        self.assertEqual(len(messages), 10)
        # First message in second batch should be msg_10
        self.assertEqual(messages[0][0], "msg_10")
        self.assertEqual(messages[0][4], "Test message 10")
    
    def test_get_messages_paginated_last_batch(self):
        """Test getting the last batch of messages."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        messages = cursor.execute(
            "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC LIMIT ? OFFSET ?",
            ("test_chat", 10, 90)
        ).fetchall()
        
        conn.close()
        
        self.assertEqual(len(messages), 10)
        # Last message should be msg_99
        self.assertEqual(messages[-1][0], "msg_99")
        self.assertEqual(messages[-1][4], "Test message 99")
    
    def test_get_messages_paginated_partial_batch(self):
        """Test getting a partial batch when fewer messages remain."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        messages = cursor.execute(
            "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC LIMIT ? OFFSET ?",
            ("test_chat", 50, 75)
        ).fetchall()
        
        conn.close()
        
        # Should only get 25 messages (100 - 75)
        self.assertEqual(len(messages), 25)
        self.assertEqual(messages[0][0], "msg_75")
        self.assertEqual(messages[-1][0], "msg_99")
    
    def test_get_messages_paginated_ordering(self):
        """Test that messages are ordered by date_time ascending."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        messages = cursor.execute(
            "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC LIMIT ? OFFSET ?",
            ("test_chat", 100, 0)
        ).fetchall()
        
        conn.close()
        
        # Check that messages are in chronological order
        for i in range(len(messages) - 1):
            current_time = messages[i][3]
            next_time = messages[i + 1][3]
            self.assertLessEqual(current_time, next_time)
    
    def test_pagination_covers_all_messages(self):
        """Test that pagination can retrieve all messages without gaps."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        all_messages = []
        batch_size = 25
        offset = 0
        
        while True:
            batch = cursor.execute(
                "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC LIMIT ? OFFSET ?",
                ("test_chat", batch_size, offset)
            ).fetchall()
            
            if not batch:
                break
            
            all_messages.extend(batch)
            offset += batch_size
        
        conn.close()
        
        # Should have retrieved all 100 messages
        self.assertEqual(len(all_messages), 100)
        
        # Check that all message IDs are present
        message_ids = [msg[0] for msg in all_messages]
        expected_ids = [f"msg_{i}" for i in range(100)]
        self.assertEqual(sorted(message_ids), sorted(expected_ids))


if __name__ == '__main__':
    unittest.main()
