"""
Unit tests for the BackupService class.
Tests backup creation, restoration, and scheduling functionality.
"""

import unittest
import tempfile
import os
import sqlite3
from datetime import datetime
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.backup import BackupService, BackupInfo


class TestBackupService(unittest.TestCase):
    """Test cases for BackupService functionality."""
    
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
            ("chat1", "Test Chat 1")
        )
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("chat2", "Test Chat 2")
        )
        
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg1", "chat1", "user", "llama2", "2024/01/15 10:30:00", "Hello, how are you today?")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg2", "chat1", "assistant", "llama2", "2024/01/15 10:30:15", "I'm doing well, thank you!")
        )
        
        conn.commit()
        conn.close()
        
        # Create backup service with custom db path
        self.backup_service = BackupService(db_path=self.db_path)
        
        # Create temporary backup directory
        self.backup_dir = tempfile.mkdtemp()
    
    def tearDown(self):
        """Clean up temporary files."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
        
        # Clean up backup directory
        if os.path.exists(self.backup_dir):
            for file in os.listdir(self.backup_dir):
                os.remove(os.path.join(self.backup_dir, file))
            os.rmdir(self.backup_dir)
    
    def test_create_backup_success(self):
        """Test that backup creation succeeds."""
        backup_path = os.path.join(self.backup_dir, "test_backup.db")
        
        result = self.backup_service.create_backup(backup_path)
        
        self.assertTrue(result)
        self.assertTrue(os.path.exists(backup_path))
    
    def test_backup_contains_all_tables(self):
        """Test that backup contains all tables from source database."""
        backup_path = os.path.join(self.backup_dir, "test_backup.db")
        
        self.backup_service.create_backup(backup_path)
        
        # Check tables in backup
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()
        
        self.assertIn('chat', tables)
        self.assertIn('message', tables)
        self.assertIn('attachment', tables)
    
    def test_backup_contains_all_data(self):
        """Test that backup contains all data from source database."""
        backup_path = os.path.join(self.backup_dir, "test_backup.db")
        
        self.backup_service.create_backup(backup_path)
        
        # Check data in backup
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        
        cursor.execute("SELECT COUNT(*) FROM chat")
        chat_count = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM message")
        message_count = cursor.fetchone()[0]
        
        conn.close()
        
        self.assertEqual(chat_count, 2)
        self.assertEqual(message_count, 2)
    
    def test_restore_backup_replace_mode(self):
        """Test restoring backup in replace mode."""
        backup_path = os.path.join(self.backup_dir, "test_backup.db")
        
        # Create backup
        self.backup_service.create_backup(backup_path)
        
        # Modify original database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("DELETE FROM message")
        conn.commit()
        conn.close()
        
        # Restore backup (replace mode)
        result = self.backup_service.restore_backup(backup_path, merge=False)
        
        self.assertTrue(result)
        
        # Verify data is restored
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM message")
        message_count = cursor.fetchone()[0]
        conn.close()
        
        self.assertEqual(message_count, 2)
    
    def test_restore_backup_merge_mode(self):
        """Test restoring backup in merge mode."""
        backup_path = os.path.join(self.backup_dir, "test_backup.db")
        
        # Create backup
        self.backup_service.create_backup(backup_path)
        
        # Add new data to original database
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("chat3", "Test Chat 3")
        )
        conn.commit()
        conn.close()
        
        # Restore backup (merge mode)
        result = self.backup_service.restore_backup(backup_path, merge=True)
        
        self.assertTrue(result)
        
        # Verify both old and new data exist
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM chat")
        chat_count = cursor.fetchone()[0]
        conn.close()
        
        # Should have original 2 chats plus the new one
        self.assertGreaterEqual(chat_count, 2)
    
    def test_restore_nonexistent_backup(self):
        """Test that restoring nonexistent backup fails gracefully."""
        backup_path = os.path.join(self.backup_dir, "nonexistent.db")
        
        result = self.backup_service.restore_backup(backup_path)
        
        self.assertFalse(result)
    
    def test_get_backup_info(self):
        """Test getting information about a backup file."""
        backup_path = os.path.join(self.backup_dir, "test_backup.db")
        
        self.backup_service.create_backup(backup_path)
        
        info = self.backup_service.get_backup_info(backup_path)
        
        self.assertIsNotNone(info)
        self.assertIsInstance(info, BackupInfo)
        self.assertEqual(info.path, backup_path)
        self.assertIsInstance(info.created_at, datetime)
        self.assertGreater(info.size_bytes, 0)
        self.assertIn('chat', info.tables_included)
        self.assertIn('message', info.tables_included)
    
    def test_get_backup_info_nonexistent(self):
        """Test getting info for nonexistent backup returns None."""
        backup_path = os.path.join(self.backup_dir, "nonexistent.db")
        
        info = self.backup_service.get_backup_info(backup_path)
        
        self.assertIsNone(info)
    
    def test_backup_schedule_table_created(self):
        """Test that backup_schedule table is created."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name='backup_schedule'
        """)
        
        result = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(result)


if __name__ == '__main__':
    unittest.main()
