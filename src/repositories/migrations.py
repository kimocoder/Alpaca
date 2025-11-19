"""
Database migrations for Alpaca.

This module contains all database migrations. Each migration should be registered
with the MigrationManager in the order they should be applied.

Example migration:
    def up_add_user_table(cursor):
        cursor.execute('''
            CREATE TABLE user (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT UNIQUE
            )
        ''')
    
    def down_add_user_table(cursor):
        cursor.execute('DROP TABLE user')
    
    migration = Migration(
        version=1,
        description="Add user table",
        up=up_add_user_table,
        down=down_add_user_table
    )
"""
from .migration_manager import Migration, MigrationManager


def get_migrations() -> MigrationManager:
    """
    Get the migration manager with all migrations registered.
    
    Returns:
        MigrationManager with all migrations registered
    """
    manager = MigrationManager()
    
    # Example migration - add indexes for performance
    # This is migration version 1
    def up_add_performance_indexes(cursor):
        """Add indexes for better query performance."""
        # Check if indexes already exist before creating
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
        # Check if FTS table already exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='message_fts'")
        if not cursor.fetchone():
            # Create FTS5 virtual table for full-text search
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
    
    return manager


def apply_migrations():
    """
    Apply all pending migrations.
    
    This function should be called during application startup to ensure
    the database schema is up to date.
    """
    manager = get_migrations()
    pending = manager.get_pending_migrations()
    
    if pending:
        print(f"Applying {len(pending)} pending migration(s)...")
        applied = manager.migrate()
        print(f"Successfully applied {len(applied)} migration(s)")
    else:
        print("Database schema is up to date")
