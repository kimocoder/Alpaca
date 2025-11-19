"""
Base repository class for database operations.

This module provides the foundation for all repository classes,
including connection management, error handling, and common operations.
"""
import sqlite3
import logging
from typing import List, Tuple, Optional, Any, Callable, Dict
from contextlib import contextmanager
from threading import Lock
import queue

try:
    from core.error_handler import ErrorHandler, AlpacaError, ErrorCategory
except ImportError:
    from ..core.error_handler import ErrorHandler, AlpacaError, ErrorCategory


class ConnectionPool:
    """Simple connection pool for SQLite database."""
    
    def __init__(self, db_path: str, pool_size: int = 5):
        """
        Initialize connection pool.
        
        Args:
            db_path: Path to SQLite database file
            pool_size: Maximum number of connections in pool
        """
        self.db_path = db_path
        self.pool_size = pool_size
        self._pool: queue.Queue = queue.Queue(maxsize=pool_size)
        self._lock = Lock()
        self._connection_count = 0
        
        # Pre-create connections
        for _ in range(pool_size):
            self._pool.put(self._create_connection())
    
    def _create_connection(self) -> sqlite3.Connection:
        """Create a new database connection."""
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        # Enable foreign keys
        conn.execute("PRAGMA foreign_keys = ON")
        return conn
    
    def get_connection(self, timeout: float = 5.0) -> sqlite3.Connection:
        """
        Get a connection from the pool.
        
        Args:
            timeout: Maximum time to wait for a connection
            
        Returns:
            Database connection
            
        Raises:
            AlpacaError: If no connection available within timeout
        """
        try:
            return self._pool.get(timeout=timeout)
        except queue.Empty:
            raise AlpacaError(
                "No database connection available",
                category=ErrorCategory.DATABASE,
                user_message="Database is busy. Please try again.",
                recoverable=True
            )
    
    def return_connection(self, conn: sqlite3.Connection) -> None:
        """
        Return a connection to the pool.
        
        Args:
            conn: Connection to return
        """
        try:
            self._pool.put_nowait(conn)
        except queue.Full:
            # Pool is full, close the connection
            conn.close()
    
    def close_all(self) -> None:
        """Close all connections in the pool."""
        connections = []
        while not self._pool.empty():
            try:
                conn = self._pool.get_nowait()
                connections.append(conn)
            except queue.Empty:
                break
        
        # Close all connections
        for conn in connections:
            try:
                conn.close()
            except Exception:
                pass


class BaseRepository:
    """Base class for all repositories with common database operations."""
    
    _logger = logging.getLogger('alpaca.repository')
    _pools: Dict[str, ConnectionPool] = {}
    _pool_lock = Lock()
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize repository.
        
        Args:
            db_path: Path to SQLite database file (defaults to alpaca.db in data_dir)
        """
        if db_path is None:
            # Import here to avoid circular dependency
            try:
                from constants import data_dir
            except ImportError:
                from ..constants import data_dir
            import os
            db_path = os.path.join(data_dir, "alpaca.db")
        
        self.db_path = db_path
        self._ensure_pool(db_path)
    
    @classmethod
    def _ensure_pool(cls, db_path: str) -> None:
        """Ensure connection pool is initialized for the given database path."""
        if db_path not in cls._pools:
            with cls._pool_lock:
                if db_path not in cls._pools:
                    cls._pools[db_path] = ConnectionPool(db_path, pool_size=5)
    
    @property
    def _pool(self) -> ConnectionPool:
        """Get the connection pool for this repository's database."""
        return self._pools[self.db_path]
    
    @classmethod
    def close_all_pools(cls) -> None:
        """Close all connection pools. Useful for cleanup in tests."""
        with cls._pool_lock:
            for pool in cls._pools.values():
                pool.close_all()
            cls._pools.clear()
    
    @contextmanager
    def _get_connection(self):
        """
        Context manager for getting a database connection.
        
        Yields:
            Database connection
        """
        conn = None
        try:
            conn = self._pool.get_connection()
            yield conn
            if conn.in_transaction:
                conn.commit()
        except Exception as e:
            if conn and conn.in_transaction:
                conn.rollback()
            raise
        finally:
            if conn:
                self._pool.return_connection(conn)
    
    def execute_query(
        self,
        query: str,
        params: Tuple = (),
        context: str = "database query"
    ) -> List[sqlite3.Row]:
        """
        Execute a SELECT query with error handling.
        
        Args:
            query: SQL query string
            params: Query parameters
            context: Context description for error logging
            
        Returns:
            List of result rows
            
        Raises:
            AlpacaError: If query execution fails
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                results = cursor.fetchall()
                self._logger.debug(
                    f"Query executed: {query[:100]}... "
                    f"(params: {params}, results: {len(results)} rows)"
                )
                return results
        except sqlite3.Error as e:
            error_msg = f"Database query failed in {context}"
            ErrorHandler.log_error(
                message=error_msg,
                exception=e,
                context={'query': query, 'params': params}
            )
            raise AlpacaError(
                message=error_msg,
                category=ErrorCategory.DATABASE,
                user_message="Failed to retrieve data from database. Please try again.",
                recoverable=True,
                context={'query': query, 'error': str(e)}
            ) from e
    
    def execute_update(
        self,
        query: str,
        params: Tuple = (),
        context: str = "database update"
    ) -> int:
        """
        Execute an INSERT, UPDATE, or DELETE query with error handling.
        
        Args:
            query: SQL query string
            params: Query parameters
            context: Context description for error logging
            
        Returns:
            Number of affected rows
            
        Raises:
            AlpacaError: If query execution fails
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(query, params)
                affected_rows = cursor.rowcount
                self._logger.debug(
                    f"Update executed: {query[:100]}... "
                    f"(params: {params}, affected: {affected_rows} rows)"
                )
                return affected_rows
        except sqlite3.Error as e:
            error_msg = f"Database update failed in {context}"
            ErrorHandler.log_error(
                message=error_msg,
                exception=e,
                context={'query': query, 'params': params}
            )
            raise AlpacaError(
                message=error_msg,
                category=ErrorCategory.DATABASE,
                user_message="Failed to save data to database. Please try again.",
                recoverable=True,
                context={'query': query, 'error': str(e)}
            ) from e
    
    def execute_many(
        self,
        query: str,
        params_list: List[Tuple],
        context: str = "batch database update"
    ) -> int:
        """
        Execute a batch INSERT or UPDATE with error handling.
        
        Args:
            query: SQL query string
            params_list: List of parameter tuples
            context: Context description for error logging
            
        Returns:
            Number of affected rows
            
        Raises:
            AlpacaError: If query execution fails
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.executemany(query, params_list)
                affected_rows = cursor.rowcount
                self._logger.debug(
                    f"Batch update executed: {query[:100]}... "
                    f"(batches: {len(params_list)}, affected: {affected_rows} rows)"
                )
                return affected_rows
        except sqlite3.Error as e:
            error_msg = f"Batch database update failed in {context}"
            ErrorHandler.log_error(
                message=error_msg,
                exception=e,
                context={'query': query, 'batch_size': len(params_list)}
            )
            raise AlpacaError(
                message=error_msg,
                category=ErrorCategory.DATABASE,
                user_message="Failed to save multiple records to database. Please try again.",
                recoverable=True,
                context={'query': query, 'error': str(e)}
            ) from e
    
    @classmethod
    def close_pool(cls, db_path: Optional[str] = None) -> None:
        """
        Close the connection pool (useful for cleanup).
        
        Args:
            db_path: Specific database path to close, or None to close all
        """
        if db_path:
            if db_path in cls._pools:
                cls._pools[db_path].close_all()
                del cls._pools[db_path]
        else:
            # Close all pools
            for pool in cls._pools.values():
                pool.close_all()
            cls._pools.clear()
