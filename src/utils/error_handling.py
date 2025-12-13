# error_handling.py
"""
Error handling utilities for Alpaca application.
Provides decorators and utilities for consistent error handling across the application.
"""

import functools
import logging
from typing import Optional, Callable, Any

logger = logging.getLogger(__name__)


class NetworkError(Exception):
    """Exception raised for network-related errors."""
    pass


class DatabaseError(Exception):
    """Exception raised for database operation errors."""
    pass


class ModelError(Exception):
    """Exception raised for model-related errors."""
    pass


def safe_operation(func: Callable) -> Callable:
    """
    Decorator for consistent error handling across model operations.
    
    Catches common exceptions and displays user-friendly error messages
    while logging detailed error information for debugging.
    
    Args:
        func: The function to wrap with error handling
        
    Returns:
        Wrapped function with error handling
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # Import here to avoid circular imports
            from ..widgets import dialog
            
            # Get the instance object (self) if available
            instance = args[0] if args else None
            parent = None
            
            # Try to get the parent widget for displaying dialogs
            if hasattr(instance, 'row') and instance.row:
                try:
                    parent = instance.row.get_root()
                except:
                    pass
            
            # Categorize and handle different error types
            error_message = str(e)
            
            # Network-related errors
            if any(keyword in error_message.lower() for keyword in [
                'connection', 'timeout', 'network', 'unreachable', 
                'refused', 'resolve', 'dns'
            ]):
                logger.error(f"Network error in {func.__name__}: {e}")
                dialog.simple_error(
                    parent=parent,
                    title=_('Connection Error'),
                    body=_('Unable to connect to the AI service. Please check your network connection and instance settings.'),
                    error_log=str(e)
                )
                
            # Authentication/API key errors
            elif any(keyword in error_message.lower() for keyword in [
                'unauthorized', 'authentication', 'api key', 'invalid key',
                'forbidden', '401', '403'
            ]):
                logger.error(f"Authentication error in {func.__name__}: {e}")
                dialog.simple_error(
                    parent=parent,
                    title=_('Authentication Error'),
                    body=_('Authentication failed. Please check your API key or credentials in the instance settings.'),
                    error_log=str(e)
                )
                
            # Model not found errors
            elif any(keyword in error_message.lower() for keyword in [
                'model not found', 'model does not exist', '404'
            ]):
                logger.error(f"Model error in {func.__name__}: {e}")
                dialog.simple_error(
                    parent=parent,
                    title=_('Model Error'),
                    body=_('The requested model was not found. Please ensure the model is available on your instance.'),
                    error_log=str(e)
                )
                
            # Rate limiting errors
            elif any(keyword in error_message.lower() for keyword in [
                'rate limit', 'too many requests', '429'
            ]):
                logger.error(f"Rate limit error in {func.__name__}: {e}")
                dialog.simple_error(
                    parent=parent,
                    title=_('Rate Limit Exceeded'),
                    body=_('Too many requests. Please wait a moment before trying again.'),
                    error_log=str(e)
                )
                
            # Database errors
            elif any(keyword in error_message.lower() for keyword in [
                'database', 'sqlite', 'sql'
            ]):
                logger.error(f"Database error in {func.__name__}: {e}")
                dialog.simple_error(
                    parent=parent,
                    title=_('Database Error'),
                    body=_('A database error occurred. Your data may not have been saved correctly.'),
                    error_log=str(e)
                )
                
            # Generic errors
            else:
                logger.error(f"Unexpected error in {func.__name__}: {e}")
                dialog.simple_error(
                    parent=parent,
                    title=_('Error'),
                    body=_('An unexpected error occurred. Please try again or check the logs for more details.'),
                    error_log=str(e)
                )
            
            # Unselect instance row if available
            if hasattr(instance, 'row') and instance.row:
                try:
                    parent_list = instance.row.get_parent()
                    if parent_list and hasattr(parent_list, 'unselect_all'):
                        parent_list.unselect_all()
                except:
                    pass
            
            return None
            
    return wrapper


def safe_operation_silent(func: Callable) -> Callable:
    """
    Decorator for error handling that logs errors but doesn't show user dialogs.
    
    Useful for background operations where user notification is not needed.
    
    Args:
        func: The function to wrap with error handling
        
    Returns:
        Wrapped function with silent error handling
    """
    @functools.wraps(func)
    def wrapper(*args, **kwargs) -> Any:
        try:
            return func(*args, **kwargs)
        except Exception as e:
            logger.error(f"Error in {func.__name__}: {e}")
            return None
            
    return wrapper
