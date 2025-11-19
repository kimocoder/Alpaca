"""
Temporary file manager for tracking and cleaning up temporary files.

This module provides centralized management of temporary files created by the
application, ensuring they are cleaned up within 1 hour or on application exit.
"""

import os
import time
import atexit
import logging
import threading
from pathlib import Path
from typing import Dict, Optional, Set
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class TempFileManager:
    """
    Manages temporary files with automatic cleanup.
    
    Tracks temporary file creation timestamps and ensures cleanup within
    1 hour or on application exit, whichever comes first.
    """
    
    _instance: Optional['TempFileManager'] = None
    _lock = threading.Lock()
    
    def __init__(self):
        """Initialize the temporary file manager."""
        self._tracked_files: Dict[str, float] = {}  # path -> creation timestamp
        self._tracked_dirs: Dict[str, float] = {}   # path -> creation timestamp
        self._cleanup_lock = threading.Lock()
        self._cleanup_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._max_age_seconds = 3600  # 1 hour
        
        # Register cleanup on exit
        atexit.register(self.cleanup_all)
        
        # Start periodic cleanup thread
        self._start_cleanup_thread()
    
    @classmethod
    def get_instance(cls) -> 'TempFileManager':
        """Get the singleton instance of TempFileManager."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    def track_file(self, file_path: str) -> None:
        """
        Track a temporary file for cleanup.
        
        Args:
            file_path: Path to the temporary file to track
        """
        with self._cleanup_lock:
            abs_path = os.path.abspath(file_path)
            self._tracked_files[abs_path] = time.time()
            logger.debug(f"Tracking temporary file: {abs_path}")
    
    def track_directory(self, dir_path: str) -> None:
        """
        Track a temporary directory for cleanup.
        
        Args:
            dir_path: Path to the temporary directory to track
        """
        with self._cleanup_lock:
            abs_path = os.path.abspath(dir_path)
            self._tracked_dirs[abs_path] = time.time()
            logger.debug(f"Tracking temporary directory: {abs_path}")
    
    def untrack_file(self, file_path: str) -> None:
        """
        Stop tracking a temporary file.
        
        Args:
            file_path: Path to the file to stop tracking
        """
        with self._cleanup_lock:
            abs_path = os.path.abspath(file_path)
            if abs_path in self._tracked_files:
                del self._tracked_files[abs_path]
                logger.debug(f"Stopped tracking file: {abs_path}")
    
    def untrack_directory(self, dir_path: str) -> None:
        """
        Stop tracking a temporary directory.
        
        Args:
            dir_path: Path to the directory to stop tracking
        """
        with self._cleanup_lock:
            abs_path = os.path.abspath(dir_path)
            if abs_path in self._tracked_dirs:
                del self._tracked_dirs[abs_path]
                logger.debug(f"Stopped tracking directory: {abs_path}")
    
    def cleanup_old_files(self) -> int:
        """
        Clean up temporary files older than the maximum age.
        
        Returns:
            Number of files/directories cleaned up
        """
        current_time = time.time()
        cleaned_count = 0
        
        with self._cleanup_lock:
            # Clean up old files
            files_to_remove = []
            for file_path, creation_time in self._tracked_files.items():
                age = current_time - creation_time
                if age >= self._max_age_seconds:
                    try:
                        if os.path.exists(file_path):
                            os.remove(file_path)
                            logger.info(f"Cleaned up old temporary file: {file_path}")
                            cleaned_count += 1
                    except Exception as e:
                        logger.error(f"Failed to clean up file {file_path}: {e}")
                    files_to_remove.append(file_path)
            
            # Remove cleaned files from tracking
            for file_path in files_to_remove:
                del self._tracked_files[file_path]
            
            # Clean up old directories
            dirs_to_remove = []
            for dir_path, creation_time in self._tracked_dirs.items():
                age = current_time - creation_time
                if age >= self._max_age_seconds:
                    try:
                        if os.path.exists(dir_path):
                            import shutil
                            shutil.rmtree(dir_path)
                            logger.info(f"Cleaned up old temporary directory: {dir_path}")
                            cleaned_count += 1
                    except Exception as e:
                        logger.error(f"Failed to clean up directory {dir_path}: {e}")
                    dirs_to_remove.append(dir_path)
            
            # Remove cleaned directories from tracking
            for dir_path in dirs_to_remove:
                del self._tracked_dirs[dir_path]
        
        return cleaned_count
    
    def cleanup_all(self) -> int:
        """
        Clean up all tracked temporary files and directories.
        
        This is called on application exit.
        
        Returns:
            Number of files/directories cleaned up
        """
        cleaned_count = 0
        
        with self._cleanup_lock:
            # Clean up all tracked files
            for file_path in list(self._tracked_files.keys()):
                try:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                        logger.info(f"Cleaned up temporary file on exit: {file_path}")
                        cleaned_count += 1
                except Exception as e:
                    logger.error(f"Failed to clean up file {file_path}: {e}")
            
            self._tracked_files.clear()
            
            # Clean up all tracked directories
            for dir_path in list(self._tracked_dirs.keys()):
                try:
                    if os.path.exists(dir_path):
                        import shutil
                        shutil.rmtree(dir_path)
                        logger.info(f"Cleaned up temporary directory on exit: {dir_path}")
                        cleaned_count += 1
                except Exception as e:
                    logger.error(f"Failed to clean up directory {dir_path}: {e}")
            
            self._tracked_dirs.clear()
        
        logger.info(f"Cleaned up {cleaned_count} temporary files/directories on exit")
        return cleaned_count
    
    def _start_cleanup_thread(self) -> None:
        """Start the periodic cleanup thread."""
        if self._cleanup_thread is None or not self._cleanup_thread.is_alive():
            self._stop_event.clear()
            self._cleanup_thread = threading.Thread(
                target=self._periodic_cleanup,
                daemon=True,
                name="TempFileCleanup"
            )
            self._cleanup_thread.start()
            logger.debug("Started periodic cleanup thread")
    
    def _periodic_cleanup(self) -> None:
        """Periodic cleanup task that runs every hour."""
        while not self._stop_event.is_set():
            # Wait for 1 hour or until stop event
            if self._stop_event.wait(timeout=3600):  # 1 hour
                break
            
            try:
                cleaned = self.cleanup_old_files()
                if cleaned > 0:
                    logger.info(f"Periodic cleanup removed {cleaned} old temporary files/directories")
            except Exception as e:
                logger.error(f"Error during periodic cleanup: {e}")
    
    def stop_cleanup_thread(self) -> None:
        """Stop the periodic cleanup thread."""
        self._stop_event.set()
        if self._cleanup_thread and self._cleanup_thread.is_alive():
            self._cleanup_thread.join(timeout=5)
            logger.debug("Stopped periodic cleanup thread")
    
    def get_tracked_count(self) -> tuple[int, int]:
        """
        Get the count of tracked files and directories.
        
        Returns:
            Tuple of (file_count, directory_count)
        """
        with self._cleanup_lock:
            return len(self._tracked_files), len(self._tracked_dirs)
    
    def get_file_age(self, file_path: str) -> Optional[float]:
        """
        Get the age of a tracked file in seconds.
        
        Args:
            file_path: Path to the file
            
        Returns:
            Age in seconds, or None if not tracked
        """
        with self._cleanup_lock:
            abs_path = os.path.abspath(file_path)
            if abs_path in self._tracked_files:
                return time.time() - self._tracked_files[abs_path]
            return None


# Convenience functions for easy access
def get_manager() -> TempFileManager:
    """Get the global TempFileManager instance."""
    return TempFileManager.get_instance()


def track_file(file_path: str) -> None:
    """Track a temporary file for cleanup."""
    get_manager().track_file(file_path)


def track_directory(dir_path: str) -> None:
    """Track a temporary directory for cleanup."""
    get_manager().track_directory(dir_path)


def untrack_file(file_path: str) -> None:
    """Stop tracking a temporary file."""
    get_manager().untrack_file(file_path)


def untrack_directory(dir_path: str) -> None:
    """Stop tracking a temporary directory."""
    get_manager().untrack_directory(dir_path)


def cleanup_all() -> int:
    """Clean up all tracked temporary files and directories."""
    return get_manager().cleanup_all()
