"""
Database migration manager for Alpaca.

This module provides a simple migration system to manage database schema changes
over time in a controlled and versioned manner.
"""
import sqlite3
import os
from typing import List, Callable, Tuple

# Import data_dir - handle both direct and relative imports
try:
    from ..constants import data_dir
    from ..core.error_handler import AlpacaError, ErrorCategory
except (ImportError, NameError):
    # Fallback for testing or when GTK is not initialized
    try:
        from src.constants import data_dir
        from src.core.error_handler import AlpacaError, ErrorCategory
    except (ImportError, NameError):
        # Use default data directory
        data_dir = os.path.expanduser("~/.var/app/com.jeffser.Alpaca/data")
        from core.error_handler import AlpacaError, ErrorCategory


class Migration:
    """Represents a single database migration."""
    
    def __init__(self, version: int, description: str, up: Callable, down: Callable = None):
        """
        Initialize a migration.
        
        Args:
            version: Migration version number (must be unique and sequential)
            description: Human-readable description of the migration
            up: Function to apply the migration (takes cursor as argument)
            down: Optional function to rollback the migration (takes cursor as argument)
        """
        self.version = version
        self.description = description
        self.up = up
        self.down = down


class MigrationManager:
    """Manages database migrations."""
    
    def __init__(self, db_path: str = None):
        """
        Initialize the migration manager.
        
        Args:
            db_path: Path to the database file (defaults to alpaca.db in data_dir)
        """
        self.db_path = db_path or os.path.join(data_dir, "alpaca.db")
        self.migrations: List[Migration] = []
        self._ensure_migration_table()
    
    def _ensure_migration_table(self):
        """Ensure the migration tracking table exists."""
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    description TEXT NOT NULL,
                    applied_at DATETIME DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
    
    def register_migration(self, migration: Migration):
        """
        Register a migration.
        
        Args:
            migration: The migration to register
        """
        # Ensure migrations are registered in order
        if self.migrations and migration.version <= self.migrations[-1].version:
            raise AlpacaError(
                f"Migration version {migration.version} must be greater than "
                f"the last registered version {self.migrations[-1].version}",
                category=ErrorCategory.DATABASE,
                user_message="Database migration configuration error. Please contact support.",
                recoverable=False
            )
        self.migrations.append(migration)
    
    def get_current_version(self) -> int:
        """
        Get the current database schema version.
        
        Returns:
            The current version number, or 0 if no migrations have been applied
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            result = cursor.execute(
                "SELECT MAX(version) FROM schema_migrations"
            ).fetchone()
            return result[0] if result[0] is not None else 0
    
    def get_pending_migrations(self) -> List[Migration]:
        """
        Get all migrations that haven't been applied yet.
        
        Returns:
            List of pending migrations
        """
        current_version = self.get_current_version()
        return [m for m in self.migrations if m.version > current_version]
    
    def get_applied_migrations(self) -> List[Tuple[int, str, str]]:
        """
        Get all applied migrations.
        
        Returns:
            List of tuples (version, description, applied_at)
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            return cursor.execute(
                "SELECT version, description, applied_at FROM schema_migrations ORDER BY version"
            ).fetchall()
    
    def migrate(self, target_version: int = None) -> List[int]:
        """
        Apply pending migrations up to the target version.
        
        Args:
            target_version: Version to migrate to (None means latest)
            
        Returns:
            List of applied migration versions
        """
        current_version = self.get_current_version()
        pending = self.get_pending_migrations()
        
        if target_version is not None:
            pending = [m for m in pending if m.version <= target_version]
        
        applied = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for migration in pending:
                try:
                    # Apply the migration
                    migration.up(cursor)
                    
                    # Record the migration
                    cursor.execute(
                        "INSERT INTO schema_migrations (version, description) VALUES (?, ?)",
                        (migration.version, migration.description)
                    )
                    
                    conn.commit()
                    applied.append(migration.version)
                    
                    print(f"Applied migration {migration.version}: {migration.description}")
                    
                except Exception as e:
                    conn.rollback()
                    raise AlpacaError(
                        f"Failed to apply migration {migration.version}: {migration.description}",
                        category=ErrorCategory.DATABASE,
                        user_message="Database upgrade failed. Please restart the application or contact support if the problem persists.",
                        recoverable=False
                    ) from e
        
        return applied
    
    def rollback(self, target_version: int = None) -> List[int]:
        """
        Rollback migrations to the target version.
        
        Args:
            target_version: Version to rollback to (None means rollback one version)
            
        Returns:
            List of rolled back migration versions
        """
        current_version = self.get_current_version()
        
        if target_version is None:
            target_version = current_version - 1
        
        if target_version >= current_version:
            return []
        
        # Get migrations to rollback (in reverse order)
        to_rollback = [
            m for m in reversed(self.migrations)
            if target_version < m.version <= current_version
        ]
        
        rolled_back = []
        
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.cursor()
            
            for migration in to_rollback:
                if migration.down is None:
                    raise AlpacaError(
                        f"Migration {migration.version} does not support rollback",
                        category=ErrorCategory.DATABASE,
                        user_message="Cannot rollback database changes. Please contact support.",
                        recoverable=False
                    )
                
                try:
                    # Rollback the migration
                    migration.down(cursor)
                    
                    # Remove the migration record
                    cursor.execute(
                        "DELETE FROM schema_migrations WHERE version = ?",
                        (migration.version,)
                    )
                    
                    conn.commit()
                    rolled_back.append(migration.version)
                    
                    print(f"Rolled back migration {migration.version}: {migration.description}")
                    
                except Exception as e:
                    conn.rollback()
                    raise AlpacaError(
                        f"Failed to rollback migration {migration.version}: {migration.description}",
                        category=ErrorCategory.DATABASE,
                        user_message="Database rollback failed. Please contact support.",
                        recoverable=False
                    ) from e
        
        return rolled_back
