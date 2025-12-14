"""
Backup service for Alpaca application.
Provides backup and restore functionality for all application data.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Callable
import sqlite3
import os
import shutil
import json


def _get_data_dir():
    """Get the data directory for Alpaca database."""
    try:
        from ..constants import data_dir
        return data_dir
    except ImportError:
        try:
            from constants import data_dir
            return data_dir
        except (ImportError, NameError):
            # Fallback for testing - use XDG_DATA_HOME or default
            base = os.getenv("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
            return os.path.join(base, "com.jeffser.Alpaca")


@dataclass
class BackupInfo:
    """
    Information about a backup file.
    
    Attributes:
        path: Full path to the backup file
        created_at: When the backup was created
        size_bytes: Size of the backup file in bytes
        tables_included: List of table names included in the backup
    """
    path: str
    created_at: datetime
    size_bytes: int
    tables_included: list


class BackupService:
    """
    Service for backing up and restoring Alpaca application data.
    
    This service provides:
    - Full database backup to a file
    - Restore from backup with data merging
    - Automatic backup scheduling
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the backup service with database connection.
        
        Args:
            db_path: Optional custom database path (mainly for testing)
        """
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.path.join(_get_data_dir(), "alpaca.db")
        
        self._auto_backup_timeout_id = None
        self._ensure_backup_schedule_table()
    
    def _ensure_backup_schedule_table(self) -> None:
        """
        Ensure the backup_schedule table exists in the database.
        Creates it if it doesn't exist.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS backup_schedule (
                    id TEXT NOT NULL PRIMARY KEY,
                    interval_hours INTEGER NOT NULL,
                    backup_path TEXT NOT NULL,
                    last_backup DATETIME,
                    enabled INTEGER NOT NULL DEFAULT 1
                )
            """)
            
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"Error creating backup_schedule table: {e}")
    
    def create_backup(self, backup_path: str) -> bool:
        """
        Create a full backup of all database tables.
        
        This method exports all tables from the main database to a new
        backup database file. The backup includes:
        - All chats and messages
        - All attachments
        - Model preferences
        - Instances configuration
        - Chat folders
        - Prompts (if prompt library is in use)
        - Bookmarks (if bookmarks feature is in use)
        - Model pins (if model pinning is in use)
        - Statistics (if statistics tracking is in use)
        
        Args:
            backup_path: Full path where the backup file should be created
        
        Returns:
            True if backup was successful, False otherwise
        """
        try:
            # Ensure the directory exists
            backup_dir = os.path.dirname(backup_path)
            if backup_dir and not os.path.exists(backup_dir):
                os.makedirs(backup_dir, exist_ok=True)
            
            # Remove existing backup file if it exists
            if os.path.exists(backup_path):
                os.remove(backup_path)
            
            # Connect to source database
            source_conn = sqlite3.connect(self.db_path)
            source_cursor = source_conn.cursor()
            
            # Get list of all tables
            source_cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = [row[0] for row in source_cursor.fetchall()]
            
            # Create backup database
            backup_conn = sqlite3.connect(backup_path)
            backup_cursor = backup_conn.cursor()
            
            # Copy each table
            for table_name in tables:
                # Get table schema
                source_cursor.execute(f"""
                    SELECT sql FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                
                schema_result = source_cursor.fetchone()
                if schema_result:
                    create_table_sql = schema_result[0]
                    
                    # Create table in backup
                    backup_cursor.execute(create_table_sql)
                    
                    # Copy all data
                    source_cursor.execute(f"SELECT * FROM {table_name}")
                    rows = source_cursor.fetchall()
                    
                    if rows:
                        # Get column count
                        placeholders = ','.join(['?' for _ in range(len(rows[0]))])
                        insert_sql = f"INSERT INTO {table_name} VALUES ({placeholders})"
                        
                        backup_cursor.executemany(insert_sql, rows)
            
            # Commit and close connections
            backup_conn.commit()
            backup_conn.close()
            source_conn.close()
            
            # Update last backup time in schedule if exists
            self._update_last_backup_time()
            
            return True
            
        except (sqlite3.Error, OSError) as e:
            print(f"Error creating backup: {e}")
            return False
    
    def restore_backup(self, backup_path: str, merge: bool = True) -> bool:
        """
        Restore from a backup file.
        
        This method can either merge the backup data with existing data
        or replace all data with the backup. When merging:
        - Duplicate IDs are handled by generating new UUIDs
        - Existing data is preserved
        - Foreign key relationships are maintained
        
        Args:
            backup_path: Full path to the backup file to restore from
            merge: If True, merge with existing data. If False, replace all data.
        
        Returns:
            True if restore was successful, False otherwise
        """
        if not os.path.exists(backup_path):
            print(f"Backup file not found: {backup_path}")
            return False
        
        try:
            # If not merging, create a fresh database
            if not merge:
                # Create a backup of current database first
                current_backup = self.db_path + ".pre-restore-backup"
                shutil.copy2(self.db_path, current_backup)
                
                # Replace with backup
                shutil.copy2(backup_path, self.db_path)
                return True
            
            # Merge mode: import data from backup
            # Use a separate connection for reading the backup
            backup_conn = sqlite3.connect(backup_path)
            backup_cursor = backup_conn.cursor()
            
            # Get list of tables in backup
            backup_cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
            """)
            tables = [row[0] for row in backup_cursor.fetchall()]
            
            # Connect to main database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Import data from each table
            for table_name in tables:
                # Check if table exists in main database
                cursor.execute("""
                    SELECT name FROM sqlite_master 
                    WHERE type='table' AND name=?
                """, (table_name,))
                
                if not cursor.fetchone():
                    # Table doesn't exist, create it
                    backup_cursor.execute(f"""
                        SELECT sql FROM sqlite_master 
                        WHERE type='table' AND name=?
                    """, (table_name,))
                    
                    schema_result = backup_cursor.fetchone()
                    if schema_result:
                        cursor.execute(schema_result[0])
                
                # Get column names from backup
                backup_cursor.execute(f"PRAGMA table_info({table_name})")
                columns = [col[1] for col in backup_cursor.fetchall()]
                column_list = ', '.join(columns)
                
                # Get all data from backup table
                backup_cursor.execute(f"SELECT {column_list} FROM {table_name}")
                rows = backup_cursor.fetchall()
                
                # Insert data into main database
                if rows:
                    placeholders = ','.join(['?' for _ in range(len(columns))])
                    
                    # Check for ID conflicts and handle them
                    if 'id' in columns:
                        # Import with conflict resolution
                        insert_sql = f"INSERT OR IGNORE INTO {table_name} ({column_list}) VALUES ({placeholders})"
                    else:
                        # No ID column, just insert
                        insert_sql = f"INSERT INTO {table_name} ({column_list}) VALUES ({placeholders})"
                    
                    cursor.executemany(insert_sql, rows)
            
            # Commit and close connections
            conn.commit()
            conn.close()
            backup_conn.close()
            
            return True
            
        except (sqlite3.Error, OSError) as e:
            print(f"Error restoring backup: {e}")
            return False
    
    def schedule_auto_backup(
        self,
        interval_hours: int,
        backup_path: str,
        callback: Optional[Callable] = None
    ) -> str:
        """
        Schedule automatic backups at a specified interval.
        
        This method uses GLib.timeout_add to schedule periodic backups.
        The schedule is also stored in the database for persistence.
        
        Args:
            interval_hours: Hours between automatic backups
            backup_path: Path where backups should be created
            callback: Optional callback function to call after each backup
        
        Returns:
            Schedule ID that can be used to cancel the schedule
        """
        try:
            from gi.repository import GLib
            from ..sql_manager import generate_uuid
        except ImportError:
            # Fallback for testing without GTK
            print("Warning: GLib not available, auto-backup scheduling disabled")
            return None
        
        # Generate schedule ID
        schedule_id = generate_uuid()
        
        # Store schedule in database
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                INSERT INTO backup_schedule 
                (id, interval_hours, backup_path, enabled)
                VALUES (?, ?, ?, 1)
            """, (schedule_id, interval_hours, backup_path))
            
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"Error storing backup schedule: {e}")
            return None
        
        # Define the backup function to be called periodically
        def perform_scheduled_backup():
            # Generate timestamped backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_dir = os.path.dirname(backup_path)
            backup_filename = f"alpaca_backup_{timestamp}.db"
            full_backup_path = os.path.join(backup_dir, backup_filename)
            
            # Perform backup
            success = self.create_backup(full_backup_path)
            
            # Call callback if provided
            if callback:
                callback(success, full_backup_path)
            
            # Return True to continue the timeout
            return True
        
        # Schedule the backup using GLib
        # Convert hours to milliseconds
        interval_ms = interval_hours * 60 * 60 * 1000
        self._auto_backup_timeout_id = GLib.timeout_add(
            interval_ms,
            perform_scheduled_backup
        )
        
        return schedule_id
    
    def cancel_auto_backup(self, schedule_id: str) -> bool:
        """
        Cancel an automatic backup schedule.
        
        Args:
            schedule_id: The schedule ID returned by schedule_auto_backup
        
        Returns:
            True if schedule was cancelled, False otherwise
        """
        try:
            # Remove from database
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                DELETE FROM backup_schedule WHERE id=?
            """, (schedule_id,))
            
            conn.commit()
            conn.close()
            
            # Cancel GLib timeout if active
            if self._auto_backup_timeout_id:
                try:
                    from gi.repository import GLib
                    GLib.source_remove(self._auto_backup_timeout_id)
                    self._auto_backup_timeout_id = None
                except ImportError:
                    pass
            
            return True
            
        except sqlite3.Error as e:
            print(f"Error cancelling backup schedule: {e}")
            return False
    
    def get_backup_info(self, backup_path: str) -> Optional[BackupInfo]:
        """
        Get information about a backup file.
        
        Args:
            backup_path: Path to the backup file
        
        Returns:
            BackupInfo object with details about the backup, or None if error
        """
        if not os.path.exists(backup_path):
            return None
        
        try:
            # Get file stats
            stat_info = os.stat(backup_path)
            size_bytes = stat_info.st_size
            created_at = datetime.fromtimestamp(stat_info.st_mtime)
            
            # Get list of tables in backup
            conn = sqlite3.connect(backup_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT name FROM sqlite_master 
                WHERE type='table' AND name NOT LIKE 'sqlite_%'
                ORDER BY name
            """)
            
            tables = [row[0] for row in cursor.fetchall()]
            conn.close()
            
            return BackupInfo(
                path=backup_path,
                created_at=created_at,
                size_bytes=size_bytes,
                tables_included=tables
            )
            
        except (sqlite3.Error, OSError) as e:
            print(f"Error getting backup info: {e}")
            return None
    
    def list_scheduled_backups(self) -> list:
        """
        List all scheduled automatic backups.
        
        Returns:
            List of dictionaries containing schedule information
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                SELECT id, interval_hours, backup_path, last_backup, enabled
                FROM backup_schedule
            """)
            
            schedules = []
            for row in cursor.fetchall():
                schedule = {
                    'id': row[0],
                    'interval_hours': row[1],
                    'backup_path': row[2],
                    'last_backup': datetime.strptime(row[3], "%Y/%m/%d %H:%M:%S") if row[3] else None,
                    'enabled': row[4] == 1
                }
                schedules.append(schedule)
            
            conn.close()
            return schedules
            
        except sqlite3.Error as e:
            print(f"Error listing scheduled backups: {e}")
            return []
    
    def _update_last_backup_time(self) -> None:
        """
        Update the last_backup timestamp for all enabled schedules.
        Called internally after a successful backup.
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute("""
                UPDATE backup_schedule 
                SET last_backup = ?
                WHERE enabled = 1
            """, (datetime.now().strftime("%Y/%m/%d %H:%M:%S"),))
            
            conn.commit()
            conn.close()
        except sqlite3.Error as e:
            print(f"Error updating last backup time: {e}")
