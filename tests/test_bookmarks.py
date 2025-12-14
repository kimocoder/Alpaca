"""
Unit tests for bookmark functionality.
Tests bookmark CRUD operations and persistence.
"""

import unittest
import tempfile
import os
import sqlite3
import datetime
import uuid


def generate_uuid() -> str:
    """Generate a unique ID."""
    return f"{datetime.datetime.today().strftime('%Y%m%d%H%M%S%f')}{uuid.uuid4().hex}"


class SQLiteConnection:
    """Context manager for SQLite connections."""
    
    def __init__(self, db_path):
        self.sql_path = db_path
        self.sqlite_con = None
        self.cursor = None
    
    def __enter__(self):
        self.sqlite_con = sqlite3.connect(self.sql_path)
        self.cursor = self.sqlite_con.cursor()
        return self
    
    def __exit__(self, exception_type, exception_val, traceback):
        if self.sqlite_con.in_transaction:
            self.sqlite_con.commit()
        self.sqlite_con.close()


class BookmarkOperations:
    """Bookmark database operations."""
    
    @staticmethod
    def add_bookmark(db_path, message_id: str) -> str:
        """Add a bookmark for a message and return the bookmark ID."""
        bookmark_id = generate_uuid()
        with SQLiteConnection(db_path) as c:
            # Check if bookmark already exists
            existing = c.cursor.execute(
                "SELECT id FROM bookmark WHERE message_id=?", (message_id,)
            ).fetchone()
            
            if existing:
                return existing[0]
            
            c.cursor.execute(
                "INSERT INTO bookmark (id, message_id, created_at) VALUES (?, ?, ?)",
                (bookmark_id, message_id, datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
            )
        return bookmark_id
    
    @staticmethod
    def remove_bookmark(db_path, message_id: str) -> bool:
        """Remove a bookmark for a message."""
        with SQLiteConnection(db_path) as c:
            result = c.cursor.execute(
                "SELECT id FROM bookmark WHERE message_id=?", (message_id,)
            ).fetchone()
            
            if not result:
                return False
            
            c.cursor.execute(
                "DELETE FROM bookmark WHERE message_id=?", (message_id,)
            )
        return True
    
    @staticmethod
    def is_bookmarked(db_path, message_id: str) -> bool:
        """Check if a message is bookmarked."""
        with SQLiteConnection(db_path) as c:
            result = c.cursor.execute(
                "SELECT id FROM bookmark WHERE message_id=?", (message_id,)
            ).fetchone()
        return result is not None
    
    @staticmethod
    def get_bookmarks(db_path) -> list:
        """Get all bookmarked messages with their chat information."""
        with SQLiteConnection(db_path) as c:
            bookmarks = c.cursor.execute(
                """SELECT b.id, b.message_id, b.created_at, m.content, m.date_time, 
                   m.role, m.model, c.id, c.name 
                   FROM bookmark b 
                   JOIN message m ON b.message_id = m.id 
                   JOIN chat c ON m.chat_id = c.id 
                   ORDER BY b.created_at DESC"""
            ).fetchall()
        return bookmarks


class TestBookmarks(unittest.TestCase):
    """Test cases for bookmark functionality."""
    
    def setUp(self):
        """Set up a temporary database for testing."""
        # Create a temporary database
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        # Create test data
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
        
        # Insert test chat
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("test_chat_1", "Test Chat")
        )
        
        # Insert test messages
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg_1", "test_chat_1", "user", None, "2024/01/01 10:00:00", "Hello")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg_2", "test_chat_1", "assistant", "llama2", "2024/01/01 10:01:00", "Hi there!")
        )
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_add_bookmark(self):
        """Test adding a bookmark to a message."""
        bookmark_id = BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        self.assertIsNotNone(bookmark_id)
        self.assertTrue(BookmarkOperations.is_bookmarked(self.db_path, "msg_1"))
    
    def test_add_duplicate_bookmark(self):
        """Test that adding a duplicate bookmark returns existing ID."""
        bookmark_id_1 = BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        bookmark_id_2 = BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        self.assertEqual(bookmark_id_1, bookmark_id_2)
    
    def test_remove_bookmark(self):
        """Test removing a bookmark from a message."""
        BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        self.assertTrue(BookmarkOperations.is_bookmarked(self.db_path, "msg_1"))
        
        result = BookmarkOperations.remove_bookmark(self.db_path, "msg_1")
        self.assertTrue(result)
        self.assertFalse(BookmarkOperations.is_bookmarked(self.db_path, "msg_1"))
    
    def test_remove_nonexistent_bookmark(self):
        """Test removing a bookmark that doesn't exist."""
        result = BookmarkOperations.remove_bookmark(self.db_path, "msg_999")
        self.assertFalse(result)
    
    def test_is_bookmarked(self):
        """Test checking if a message is bookmarked."""
        self.assertFalse(BookmarkOperations.is_bookmarked(self.db_path, "msg_1"))
        
        BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        self.assertTrue(BookmarkOperations.is_bookmarked(self.db_path, "msg_1"))
    
    def test_get_bookmarks(self):
        """Test retrieving all bookmarks."""
        BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        BookmarkOperations.add_bookmark(self.db_path, "msg_2")
        
        bookmarks = BookmarkOperations.get_bookmarks(self.db_path)
        self.assertEqual(len(bookmarks), 2)
        
        # Check that bookmarks contain expected data
        bookmark_message_ids = [b[1] for b in bookmarks]
        self.assertIn("msg_1", bookmark_message_ids)
        self.assertIn("msg_2", bookmark_message_ids)
    
    def test_bookmark_persistence(self):
        """Test that bookmarks persist across database connections."""
        BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        
        # Close and reopen connection
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        result = cursor.execute(
            "SELECT id FROM bookmark WHERE message_id=?", ("msg_1",)
        ).fetchone()
        conn.close()
        
        self.assertIsNotNone(result)
    
    def test_bookmark_with_chat_info(self):
        """Test that get_bookmarks returns chat information."""
        BookmarkOperations.add_bookmark(self.db_path, "msg_1")
        
        bookmarks = BookmarkOperations.get_bookmarks(self.db_path)
        self.assertEqual(len(bookmarks), 1)
        
        # Check bookmark structure
        bookmark = bookmarks[0]
        self.assertEqual(bookmark[1], "msg_1")  # message_id
        self.assertEqual(bookmark[3], "Hello")  # content
        self.assertEqual(bookmark[7], "test_chat_1")  # chat_id
        self.assertEqual(bookmark[8], "Test Chat")  # chat_name


if __name__ == '__main__':
    unittest.main()
