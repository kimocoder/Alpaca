"""
Error handling framework for Alpaca.

This module provides centralized error handling, logging, and user notification
functionality for the Alpaca application.
"""
import logging
import traceback
from typing import Optional, Dict, Any
from enum import Enum
from datetime import datetime


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)


class ErrorCategory(Enum):
    """Categories of errors in Alpaca."""
    NETWORK = "network"
    DATABASE = "database"
    PROCESS = "process"
    FILESYSTEM = "filesystem"
    VALIDATION = "validation"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class AlpacaError(Exception):
    """Base exception for Alpaca errors."""

    def __init__(
        self,
        message: str,
        category: ErrorCategory = ErrorCategory.UNKNOWN,
        user_message: Optional[str] = None,
        recoverable: bool = True,
        context: Optional[Dict[str, Any]] = None
    ):
        self.message = message
        self.category = category
        self.user_message = user_message
        self.recoverable = recoverable
        self.context = context or {}
        self.timestamp = datetime.now()
        super().__init__(message)


class ErrorHandler:
    """Centralized error handling and logging."""

    _logger = logging.getLogger('alpaca.error_handler')
    _error_log: list = []

    @classmethod
    def handle_exception(
        cls,
        exception: Exception,
        context: str,
        user_message: Optional[str] = None,
        show_dialog: bool = True,
        parent_widget: Optional[Any] = None
    ) -> None:
        """
        Handle exceptions with logging and user notification.

        Args:
            exception: The exception that occurred
            context: Context string describing where the error occurred
            user_message: Optional user-friendly message to display
            show_dialog: Whether to show an error dialog to the user
            parent_widget: Parent GTK widget for the error dialog
        """
        # Log the error with full details
        cls.log_error(
            message=f"Error in {context}: {str(exception)}",
            exception=exception,
            context={'context': context}
        )

        # Show user notification if requested
        if show_dialog:
            message = user_message or cls.create_user_message(exception)
            # In a real implementation, this would show a GTK dialog
            cls._logger.info(f"Would show dialog: {message}")

    @classmethod
    def log_error(
        cls,
        message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log error with context and stack trace.

        Args:
            message: Error message to log
            exception: Optional exception object
            context: Optional context dictionary
        """
        timestamp = datetime.now()

        # Build log entry
        log_entry = {
            'timestamp': timestamp.isoformat(),
            'message': message,
            'context': context or {}
        }

        # Add exception details if provided
        if exception:
            log_entry['exception_type'] = type(exception).__name__
            log_entry['exception_message'] = str(exception)
            log_entry['stack_trace'] = traceback.format_exc()

        # Store in error log
        cls._error_log.append(log_entry)

        # Log to standard logger
        if exception:
            cls._logger.error(
                f"{message}\n"
                f"Exception: {type(exception).__name__}: {str(exception)}\n"
                f"Context: {context}\n"
                f"Stack trace:\n{traceback.format_exc()}"
            )
        else:
            cls._logger.error(f"{message}\nContext: {context}")

    @classmethod
    def log_warning(
        cls,
        message: str,
        context: Optional[Dict[str, Any]] = None
    ) -> None:
        """
        Log warning with context.

        Args:
            message: Warning message to log
            context: Optional context dictionary
        """
        timestamp = datetime.now()

        # Build log entry
        log_entry = {
            'timestamp': timestamp.isoformat(),
            'level': 'WARNING',
            'message': message,
            'context': context or {}
        }

        # Store in error log
        cls._error_log.append(log_entry)

        # Log to standard logger
        cls._logger.warning(f"{message}\nContext: {context}")

    @classmethod
    def create_user_message(cls, exception: Exception) -> str:
        """
        Convert technical exception to user-friendly message.

        Args:
            exception: The exception to convert

        Returns:
            User-friendly error message
        """
        if isinstance(exception, AlpacaError):
            # If user_message is provided, use it
            if exception.user_message:
                return exception.user_message
            
            # Otherwise, generate a user-friendly message based on category
            category_messages = {
                ErrorCategory.NETWORK: 'Unable to connect to the service. Please check your network connection and try again.',
                ErrorCategory.DATABASE: 'A database error occurred. Please try again or contact support if the problem persists.',
                ErrorCategory.PROCESS: 'A process error occurred. Please restart the application and try again.',
                ErrorCategory.FILESYSTEM: 'A file system error occurred. Please check file permissions and available disk space.',
                ErrorCategory.VALIDATION: 'Invalid input provided. Please check your data and try again.',
                ErrorCategory.RESOURCE: 'A resource error occurred. Please check system resources and try again.',
                ErrorCategory.UNKNOWN: 'An unexpected error occurred. Please try again or contact support if the problem persists.'
            }
            
            return category_messages.get(
                exception.category,
                'An unexpected error occurred. Please try again or contact support if the problem persists.'
            )

        # Map common exception types to user-friendly messages
        exception_type = type(exception).__name__

        user_messages = {
            'ConnectionError': 'Unable to connect to the service. Please check your network connection and try again.',
            'TimeoutError': 'The operation took too long to complete. Please try again.',
            'FileNotFoundError': 'The requested file could not be found. Please verify the file path.',
            'PermissionError': 'Permission denied. Please check file permissions and ensure you have the necessary access rights.',
            'ValueError': 'Invalid input provided. Please check your data and try again.',
            'KeyError': 'Required information is missing. Please ensure all required fields are provided.',
            'sqlite3.OperationalError': 'Database operation failed. Please try again or contact support if the problem persists.',
        }

        return user_messages.get(
            exception_type,
            'An unexpected error occurred. Please try again or contact support if the problem persists.'
        )

    @classmethod
    def get_error_log(cls) -> list:
        """Get the complete error log."""
        return cls._error_log.copy()

    @classmethod
    def clear_error_log(cls) -> None:
        """Clear the error log (useful for testing)."""
        cls._error_log.clear()
