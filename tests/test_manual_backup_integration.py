"""
Integration test for manual backup functionality.
Validates Requirement 20.1: Export all chats and settings.
"""

import unittest
import tempfile
import os
import sqlite3
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.backup import BackupService


class TestManualBackupIntegration(unittest.TestCase):
    """Integration tests for manual backup creation."""
    
    def setUp(self):
        """Set up a realistic database for testing."""
        # Create a temporary database
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        # Create the database schema with all tables
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create all relevant tables
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
        
        cursor.execute("""
            CREATE TABLE prompt (
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT,
                created_at DATETIME NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE bookmark (
                id TEXT NOT NULL PRIMARY KEY,
                message_id TEXT NOT NULL,
                created_at DATETIME NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE model_pin (
                id TEXT NOT NULL PRIMARY KEY,
                model_name TEXT NOT NULL,
                instance_id TEXT NOT NULL,
                pin_order INTEGER NOT NULL
            )
        """)
        
        cursor.execute("""
            CREATE TABLE statistics (
                id TEXT NOT NULL PRIMARY KEY,
                event_type TEXT NOT NULL,
                model TEXT,
                tokens_used INTEGER,
                response_time_ms INTEGER,
                timestamp DATETIME NOT NULL
            )
        """)
        
        # Insert test data
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)",
            ("chat1", "Work Chat", "work", 0)
        )
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)",
            ("chat2", "Personal Chat", "personal", 0)
        )
        
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg1", "chat1", "user", "llama2", "2024/01/15 10:30:00", "What is Python?")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg2", "chat1", "assistant", "llama2", "2024/01/15 10:30:15", "Python is a programming language.")
        )
        
        cursor.execute(
            "INSERT INTO prompt (id, name, content, category, created_at) VALUES (?, ?, ?, ?, ?)",
            ("prompt1", "Code Review", "Please review this code", "development", "2024/01/15 10:00:00")
        )
        
        cursor.execute(
            "INSERT INTO bookmark (id, message_id, created_at) VALUES (?, ?, ?)",
            ("bookmark1", "msg2", "2024/01/15 11:00:00")
        )
        
        cursor.execute(
            "INSERT INTO model_pin (id, model_name, instance_id, pin_order) VALUES (?, ?, ?, ?)",
            ("pin1", "llama2", "instance1", 1)
        )
        
        cursor.execute(
            "INSERT INTO statistics (id, event_type, model, tokens_used, response_time_ms, timestamp) VALUES (?, ?, ?, ?, ?, ?)",
            ("stat1", "message", "llama2", 150, 2500, "2024/01/15 10:30:15")
        )
        
        conn.commit()
        conn.close()
        
        # Create backup service
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
    
    def test_manual_backup_exports_all_chats_and_settings(self):
        """
        Test that manual backup exports all chats and settings.
        Validates Requirement 20.1.
        """
        backup_path = os.path.join(self.backup_dir, "manual_backup.db")
        
        # Create backup
        result = self.backup_service.create_backup(backup_path)
        
        # Verify backup was created successfully
        self.assertTrue(result, "Backup creation should succeed")
        self.assertTrue(os.path.exists(backup_path), "Backup file should exist")
        
        # Verify all tables are present in backup
        conn = sqlite3.connect(backup_path)
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT name FROM sqlite_master 
            WHERE type='table' AND name NOT LIKE 'sqlite_%'
            ORDER BY name
        """)
        
        tables = [row[0] for row in cursor.fetchall()]
        
        # Check that all important tables are backed up
        expected_tables = ['chat', 'message', 'attachment', 'prompt', 
                          'bookmark', 'model_pin', 'statistics']
        
        for table in expected_tables:
            self.assertIn(table, tables, f"Table '{table}' should be in backup")
        
        # Verify data integrity - check that all data is present
        cursor.execute("SELECT COUNT(*) FROM chat")
        chat_count = cursor.fetchone()[0]
        self.assertEqual(chat_count, 2, "All chats should be backed up")
        
        cursor.execute("SELECT COUNT(*) FROM message")
        message_count = cursor.fetchone()[0]
        self.assertEqual(message_count, 2, "All messages should be backed up")
        
        cursor.execute("SELECT COUNT(*) FROM prompt")
        prompt_count = cursor.fetchone()[0]
        self.assertEqual(prompt_count, 1, "All prompts should be backed up")
        
        cursor.execute("SELECT COUNT(*) FROM bookmark")
        bookmark_count = cursor.fetchone()[0]
        self.assertEqual(bookmark_count, 1, "All bookmarks should be backed up")
        
        cursor.execute("SELECT COUNT(*) FROM model_pin")
        pin_count = cursor.fetchone()[0]
        self.assertEqual(pin_count, 1, "All model pins should be backed up")
        
        cursor.execute("SELECT COUNT(*) FROM statistics")
        stats_count = cursor.fetchone()[0]
        self.assertEqual(stats_count, 1, "All statistics should be backed up")
        
        # Verify specific data content
        cursor.execute("SELECT name, folder FROM chat WHERE id = 'chat1'")
        chat_data = cursor.fetchone()
        self.assertEqual(chat_data[0], "Work Chat", "Chat name should be preserved")
        self.assertEqual(chat_data[1], "work", "Chat folder should be preserved")
        
        cursor.execute("SELECT content FROM message WHERE id = 'msg1'")
        message_content = cursor.fetchone()[0]
        self.assertEqual(message_content, "What is Python?", "Message content should be preserved")
        
        conn.close()
    
    def test_backup_file_size_is_reasonable(self):
        """Test that backup file has reasonable size (not empty, not corrupted)."""
        backup_path = os.path.join(self.backup_dir, "size_test_backup.db")
        
        # Create backup
        self.backup_service.create_backup(backup_path)
        
        # Check file size
        file_size = os.path.getsize(backup_path)
        
        # SQLite database should be at least a few KB
        self.assertGreater(file_size, 1024, "Backup file should be larger than 1KB")
        
        # Should be less than 100MB for this test data
        self.assertLess(file_size, 100 * 1024 * 1024, "Backup file should be reasonable size")
    
    def test_backup_can_be_opened_as_valid_sqlite_database(self):
        """Test that backup file is a valid SQLite database."""
        backup_path = os.path.join(self.backup_dir, "valid_db_backup.db")
        
        # Create backup
        self.backup_service.create_backup(backup_path)
        
        # Try to open as SQLite database
        try:
            conn = sqlite3.connect(backup_path)
            cursor = conn.cursor()
            
            # Execute a simple query
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            tables = cursor.fetchall()
            
            conn.close()
            
            # Should have at least one table
            self.assertGreater(len(tables), 0, "Backup should contain tables")
            
        except sqlite3.Error as e:
            self.fail(f"Backup file is not a valid SQLite database: {e}")


if __name__ == '__main__':
    unittest.main()
