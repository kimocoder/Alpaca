"""
Unit tests for database migrations.
"""
import sqlite3
import os
import tempfile
import pytest

from src.repositories.migration_manager import MigrationManager, Migration


def setup_test_migrations(manager):
    """Helper function to register test migrations."""
    # Migration 1: Add performance indexes
    def up_add_performance_indexes(cursor):
        """Add indexes for better query performance."""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_message_chat_id'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_message_chat_id ON message(chat_id)")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_message_date_time'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_message_date_time ON message(date_time)")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_chat_folder'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_chat_folder ON chat(folder)")
        
        cursor.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_attachment_message_id'")
        if not cursor.fetchone():
            cursor.execute("CREATE INDEX idx_attachment_message_id ON attachment(message_id)")
    
    def down_add_performance_indexes(cursor):
        """Remove performance indexes."""
        cursor.execute("DROP INDEX IF EXISTS idx_message_chat_id")
        cursor.execute("DROP INDEX IF EXISTS idx_message_date_time")
        cursor.execute("DROP INDEX IF EXISTS idx_chat_folder")
        cursor.execute("DROP INDEX IF EXISTS idx_attachment_message_id")
    
    manager.register_migration(Migration(
        version=1,
        description="Add performance indexes for message, chat, and attachment tables",
        up=up_add_performance_indexes,
        down=down_add_performance_indexes
    ))
    
    # Migration 2: Add full-text search index on message content
    def up_add_fts_index(cursor):
        """Add full-text search virtual table for message content."""
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_fts'")
        if not cursor.fetchone():
            # Create FTS5 virtual table
            cursor.execute("""
                CREATE VIRTUAL TABLE message_fts USING fts5(
                    message_id UNINDEXED,
                    content
                )
            """)
            
            # Populate FTS table with existing messages
            cursor.execute("""
                INSERT INTO message_fts(rowid, message_id, content)
                SELECT rowid, id, content FROM message
            """)
            
            # Create triggers to keep FTS table in sync
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS message_fts_insert AFTER INSERT ON message BEGIN
                    INSERT INTO message_fts(rowid, message_id, content)
                    VALUES (new.rowid, new.id, new.content);
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS message_fts_delete AFTER DELETE ON message BEGIN
                    DELETE FROM message_fts WHERE rowid = old.rowid;
                END
            """)
            
            cursor.execute("""
                CREATE TRIGGER IF NOT EXISTS message_fts_update AFTER UPDATE ON message BEGIN
                    UPDATE message_fts SET content = new.content WHERE rowid = new.rowid;
                END
            """)
    
    def down_add_fts_index(cursor):
        """Remove full-text search virtual table."""
        cursor.execute("DROP TRIGGER IF EXISTS message_fts_insert")
        cursor.execute("DROP TRIGGER IF EXISTS message_fts_delete")
        cursor.execute("DROP TRIGGER IF EXISTS message_fts_update")
        cursor.execute("DROP TABLE IF EXISTS message_fts")
    
    manager.register_migration(Migration(
        version=2,
        description="Add full-text search index on message content",
        up=up_add_fts_index,
        down=down_add_fts_index
    ))


def create_base_tables(conn):
    """Helper to create base database tables for testing."""
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE message (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            model TEXT,
            date_time DATETIME NOT NULL,
            content TEXT NOT NULL
        )
    """)
    cursor.execute("""
        CREATE TABLE chat (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            folder TEXT,
            is_template INTEGER NOT NULL DEFAULT 0
        )
    """)
    cursor.execute("""
        CREATE TABLE attachment (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL
        )
    """)
    conn.commit()


class TestMigrations:
    """Test database migration functionality."""
    
    def test_migration_manager_initialization(self):
        """Test that migration manager initializes correctly."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            manager = MigrationManager(db_path)
            
            # Check that migration table exists
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
                ).fetchone()
                assert result is not None
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_performance_indexes_migration(self):
        """Test that performance indexes are created correctly."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # Create base tables
            with sqlite3.connect(db_path) as conn:
                create_base_tables(conn)
            
            # Apply migrations
            manager = MigrationManager(db_path)
            setup_test_migrations(manager)
            applied = manager.migrate(target_version=1)
            
            assert 1 in applied
            
            # Verify indexes exist
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Check for idx_message_chat_id
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_message_chat_id'"
                ).fetchone()
                assert result is not None, "idx_message_chat_id index not found"
                
                # Check for idx_message_date_time
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_message_date_time'"
                ).fetchone()
                assert result is not None, "idx_message_date_time index not found"
                
                # Check for idx_chat_folder
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_chat_folder'"
                ).fetchone()
                assert result is not None, "idx_chat_folder index not found"
                
                # Check for idx_attachment_message_id
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_attachment_message_id'"
                ).fetchone()
                assert result is not None, "idx_attachment_message_id index not found"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_fts_index_migration(self):
        """Test that full-text search index is created correctly."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # Create base tables
            with sqlite3.connect(db_path) as conn:
                create_base_tables(conn)
                
                # Insert some test messages
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO message (id, chat_id, role, model, date_time, content)
                    VALUES ('msg1', 'chat1', 'user', 'test-model', '2024-01-01 12:00:00', 'Hello world')
                """)
                cursor.execute("""
                    INSERT INTO message (id, chat_id, role, model, date_time, content)
                    VALUES ('msg2', 'chat1', 'assistant', 'test-model', '2024-01-01 12:00:01', 'Hi there')
                """)
                conn.commit()
            
            # Apply migrations
            manager = MigrationManager(db_path)
            setup_test_migrations(manager)
            applied = manager.migrate()
            
            assert 2 in applied
            
            # Verify FTS table exists
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Check for message_fts table
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='message_fts'"
                ).fetchone()
                assert result is not None, "message_fts table not found"
                
                # Check that FTS table is populated
                result = cursor.execute(
                    "SELECT COUNT(*) FROM message_fts"
                ).fetchone()
                assert result[0] == 2, f"Expected 2 messages in FTS table, got {result[0]}"
                
                # Test FTS search
                result = cursor.execute(
                    "SELECT message_id FROM message_fts WHERE content MATCH 'hello'"
                ).fetchone()
                assert result is not None, "FTS search failed"
                assert result[0] == 'msg1', f"Expected msg1, got {result[0]}"
                
                # Check that triggers exist
                triggers = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'message_fts_%'"
                ).fetchall()
                assert len(triggers) == 3, f"Expected 3 triggers, got {len(triggers)}"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_fts_triggers_work(self):
        """Test that FTS triggers keep the index in sync."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # Create base tables and apply migrations
            with sqlite3.connect(db_path) as conn:
                create_base_tables(conn)
            
            manager = MigrationManager(db_path)
            setup_test_migrations(manager)
            manager.migrate()
            
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                
                # Test INSERT trigger
                cursor.execute("""
                    INSERT INTO message (id, chat_id, role, model, date_time, content)
                    VALUES ('msg3', 'chat1', 'user', 'test-model', '2024-01-01 12:00:00', 'Python programming')
                """)
                conn.commit()
                
                result = cursor.execute(
                    "SELECT message_id FROM message_fts WHERE content MATCH 'python'"
                ).fetchone()
                assert result is not None, "INSERT trigger failed"
                assert result[0] == 'msg3'
                
                # Test UPDATE trigger
                cursor.execute("""
                    UPDATE message SET content = 'JavaScript programming' WHERE id = 'msg3'
                """)
                conn.commit()
                
                result = cursor.execute(
                    "SELECT message_id FROM message_fts WHERE content MATCH 'javascript'"
                ).fetchone()
                assert result is not None, "UPDATE trigger failed"
                assert result[0] == 'msg3'
                
                result = cursor.execute(
                    "SELECT message_id FROM message_fts WHERE content MATCH 'python'"
                ).fetchone()
                assert result is None, "Old content not removed after UPDATE"
                
                # Test DELETE trigger
                cursor.execute("DELETE FROM message WHERE id = 'msg3'")
                conn.commit()
                
                result = cursor.execute(
                    "SELECT message_id FROM message_fts WHERE content MATCH 'javascript'"
                ).fetchone()
                assert result is None, "DELETE trigger failed"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
    
    def test_migration_rollback(self):
        """Test that migrations can be rolled back."""
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            db_path = f.name
        
        try:
            # Create base tables
            with sqlite3.connect(db_path) as conn:
                create_base_tables(conn)
            
            # Apply migrations
            manager = MigrationManager(db_path)
            setup_test_migrations(manager)
            manager.migrate()
            
            # Rollback to version 1
            rolled_back = manager.rollback(target_version=1)
            assert 2 in rolled_back
            
            # Verify FTS table is removed
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='message_fts'"
                ).fetchone()
                assert result is None, "FTS table should be removed after rollback"
                
                # Verify triggers are removed
                triggers = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'message_fts_%'"
                ).fetchall()
                assert len(triggers) == 0, "FTS triggers should be removed after rollback"
            
            # Rollback to version 0
            rolled_back = manager.rollback(target_version=0)
            assert 1 in rolled_back
            
            # Verify indexes are removed
            with sqlite3.connect(db_path) as conn:
                cursor = conn.cursor()
                result = cursor.execute(
                    "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_message_chat_id'"
                ).fetchone()
                assert result is None, "Indexes should be removed after rollback"
        finally:
            if os.path.exists(db_path):
                os.unlink(db_path)
