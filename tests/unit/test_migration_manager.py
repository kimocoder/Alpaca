"""
Unit tests for the migration manager.
"""
import os
import tempfile
import sqlite3
import pytest

from src.repositories.migration_manager import Migration, MigrationManager


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)
    yield path
    if os.path.exists(path):
        os.unlink(path)


def test_migration_manager_initialization(temp_db):
    """Test that migration manager initializes correctly."""
    manager = MigrationManager(temp_db)
    
    # Check that migration table was created
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        result = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='schema_migrations'"
        ).fetchone()
        assert result is not None


def test_migration_registration(temp_db):
    """Test that migrations can be registered."""
    manager = MigrationManager(temp_db)
    
    def up(cursor):
        cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    
    migration = Migration(1, "Create test table", up)
    manager.register_migration(migration)
    
    assert len(manager.migrations) == 1
    assert manager.migrations[0].version == 1


def test_migration_registration_order(temp_db):
    """Test that migrations must be registered in order."""
    manager = MigrationManager(temp_db)
    
    def up(cursor):
        pass
    
    migration1 = Migration(1, "First", up)
    migration2 = Migration(3, "Third", up)
    migration3 = Migration(2, "Second", up)
    
    manager.register_migration(migration1)
    manager.register_migration(migration2)
    
    # This should fail because version 2 < 3
    # Import AlpacaError for the test
    from src.core.error_handler import AlpacaError
    with pytest.raises(AlpacaError):
        manager.register_migration(migration3)


def test_get_current_version(temp_db):
    """Test getting the current database version."""
    manager = MigrationManager(temp_db)
    
    # Initially should be 0
    assert manager.get_current_version() == 0
    
    # Apply a migration
    def up(cursor):
        cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    
    migration = Migration(1, "Create test table", up)
    manager.register_migration(migration)
    manager.migrate()
    
    # Now should be 1
    assert manager.get_current_version() == 1


def test_get_pending_migrations(temp_db):
    """Test getting pending migrations."""
    manager = MigrationManager(temp_db)
    
    def up(cursor):
        pass
    
    migration1 = Migration(1, "First", up)
    migration2 = Migration(2, "Second", up)
    
    manager.register_migration(migration1)
    manager.register_migration(migration2)
    
    # Both should be pending
    pending = manager.get_pending_migrations()
    assert len(pending) == 2
    
    # Apply first migration
    manager.migrate(target_version=1)
    
    # Only second should be pending
    pending = manager.get_pending_migrations()
    assert len(pending) == 1
    assert pending[0].version == 2


def test_migrate_applies_migrations(temp_db):
    """Test that migrate applies migrations correctly."""
    manager = MigrationManager(temp_db)
    
    def up1(cursor):
        cursor.execute("CREATE TABLE test1 (id INTEGER PRIMARY KEY)")
    
    def up2(cursor):
        cursor.execute("CREATE TABLE test2 (id INTEGER PRIMARY KEY)")
    
    migration1 = Migration(1, "Create test1 table", up1)
    migration2 = Migration(2, "Create test2 table", up2)
    
    manager.register_migration(migration1)
    manager.register_migration(migration2)
    
    applied = manager.migrate()
    
    assert len(applied) == 2
    assert applied == [1, 2]
    
    # Check that tables were created
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'test%'"
        ).fetchall()
        assert len(tables) == 2


def test_migrate_to_target_version(temp_db):
    """Test migrating to a specific version."""
    manager = MigrationManager(temp_db)
    
    def up(cursor):
        pass
    
    migration1 = Migration(1, "First", up)
    migration2 = Migration(2, "Second", up)
    migration3 = Migration(3, "Third", up)
    
    manager.register_migration(migration1)
    manager.register_migration(migration2)
    manager.register_migration(migration3)
    
    # Migrate only to version 2
    applied = manager.migrate(target_version=2)
    
    assert len(applied) == 2
    assert manager.get_current_version() == 2


def test_rollback_migration(temp_db):
    """Test rolling back migrations."""
    manager = MigrationManager(temp_db)
    
    def up(cursor):
        cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    
    def down(cursor):
        cursor.execute("DROP TABLE test")
    
    migration = Migration(1, "Create test table", up, down)
    manager.register_migration(migration)
    
    # Apply migration
    manager.migrate()
    assert manager.get_current_version() == 1
    
    # Rollback
    rolled_back = manager.rollback(target_version=0)
    assert len(rolled_back) == 1
    assert manager.get_current_version() == 0
    
    # Check that table was dropped
    with sqlite3.connect(temp_db) as conn:
        cursor = conn.cursor()
        tables = cursor.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='test'"
        ).fetchall()
        assert len(tables) == 0


def test_rollback_without_down_function(temp_db):
    """Test that rollback fails if migration has no down function."""
    manager = MigrationManager(temp_db)
    
    def up(cursor):
        cursor.execute("CREATE TABLE test (id INTEGER PRIMARY KEY)")
    
    migration = Migration(1, "Create test table", up)  # No down function
    manager.register_migration(migration)
    
    # Apply migration
    manager.migrate()
    
    # Rollback should fail
    from src.core.error_handler import AlpacaError
    with pytest.raises(AlpacaError, match="does not support rollback"):
        manager.rollback(target_version=0)


def test_migration_failure_rollback(temp_db):
    """Test that failed migrations are rolled back."""
    manager = MigrationManager(temp_db)
    
    def up1(cursor):
        cursor.execute("CREATE TABLE test1 (id INTEGER PRIMARY KEY)")
    
    def up2(cursor):
        # This will fail
        cursor.execute("INVALID SQL")
    
    migration1 = Migration(1, "Create test1 table", up1)
    migration2 = Migration(2, "Invalid migration", up2)
    
    manager.register_migration(migration1)
    manager.register_migration(migration2)
    
    # First migration should succeed
    manager.migrate(target_version=1)
    assert manager.get_current_version() == 1
    
    # Second migration should fail
    from src.core.error_handler import AlpacaError
    with pytest.raises(AlpacaError):
        manager.migrate()
    
    # Version should still be 1
    assert manager.get_current_version() == 1


def test_get_applied_migrations(temp_db):
    """Test getting applied migrations."""
    manager = MigrationManager(temp_db)
    
    def up(cursor):
        pass
    
    migration1 = Migration(1, "First", up)
    migration2 = Migration(2, "Second", up)
    
    manager.register_migration(migration1)
    manager.register_migration(migration2)
    
    # Apply migrations
    manager.migrate()
    
    # Get applied migrations
    applied = manager.get_applied_migrations()
    assert len(applied) == 2
    assert applied[0][0] == 1  # version
    assert applied[0][1] == "First"  # description
    assert applied[1][0] == 2
    assert applied[1][1] == "Second"
