"""
Message service for business logic related to messages.

This module provides business logic for message operations,
including validation, attachment handling, and search functionality.
"""
import uuid
from typing import Optional, List, Dict, Any
from datetime import datetime

try:
    from repositories.message_repository import MessageRepository
    from core.error_handler import ErrorHandler, AlpacaError, ErrorCategory
except ImportError:
    from ..repositories.message_repository import MessageRepository
    from ..core.error_handler import ErrorHandler, AlpacaError, ErrorCategory


class MessageService:
    """Business logic for message operations."""
    
    def __init__(self, message_repo: Optional[MessageRepository] = None):
        """
        Initialize message service.
        
        Args:
            message_repo: Message repository instance (creates new if None)
        """
        self.message_repo = message_repo or MessageRepository()
    
    def create_message(
        self,
        chat_id: str,
        role: str,
        content: str,
        model: Optional[str] = None,
        date_time: Optional[str] = None
    ) -> str:
        """
        Create a new message with validation.
        
        Args:
            chat_id: The chat ID
            role: Message role ('user', 'assistant', 'system')
            content: Message content
            model: Optional model name
            date_time: Optional timestamp (defaults to now)
            
        Returns:
            The created message ID
            
        Raises:
            AlpacaError: If validation fails or creation fails
        """
        # Validate role
        valid_roles = ['user', 'assistant', 'system']
        if role not in valid_roles:
            raise AlpacaError(
                f"Invalid role: {role}",
                category=ErrorCategory.VALIDATION,
                user_message=f"Message role must be one of: {', '.join(valid_roles)}",
                recoverable=True
            )
        
        # Validate content
        if content is None:
            content = ""
        
        # Generate timestamp if not provided
        if date_time is None:
            date_time = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        
        # Create message
        message_id = str(uuid.uuid4())
        message_data = {
            'id': message_id,
            'chat_id': chat_id,
            'role': role,
            'model': model or '',
            'date_time': date_time,
            'content': content
        }
        
        try:
            self.message_repo.create(message_data)
            return message_id
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to create message",
                exception=e,
                context={'chat_id': chat_id, 'role': role}
            )
            raise AlpacaError(
                "Failed to create message",
                category=ErrorCategory.DATABASE,
                user_message="Could not save the message. Please try again.",
                recoverable=True
            ) from e
    
    def get_message(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a message by ID.
        
        Args:
            message_id: The message ID
            
        Returns:
            Message dictionary or None if not found
        """
        try:
            return self.message_repo.get_by_id(message_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve message",
                exception=e,
                context={'message_id': message_id}
            )
            return None
    
    def get_messages_for_chat(
        self,
        chat_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get messages for a chat with pagination.
        
        Args:
            chat_id: The chat ID
            limit: Maximum number of messages (None for all)
            offset: Number of messages to skip
            
        Returns:
            List of message dictionaries
        """
        try:
            return self.message_repo.get_by_chat(chat_id, limit, offset)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve messages",
                exception=e,
                context={'chat_id': chat_id}
            )
            return []
    
    def update_message(
        self,
        message_id: str,
        content: Optional[str] = None,
        model: Optional[str] = None
    ) -> bool:
        """
        Update a message.
        
        Args:
            message_id: The message ID
            content: New content (optional)
            model: New model (optional)
            
        Returns:
            True if updated successfully
        """
        updates = {}
        
        if content is not None:
            updates['content'] = content
        
        if model is not None:
            updates['model'] = model
        
        if not updates:
            return False
        
        try:
            return self.message_repo.update(message_id, updates)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to update message",
                exception=e,
                context={'message_id': message_id, 'updates': updates}
            )
            raise AlpacaError(
                "Failed to update message",
                category=ErrorCategory.DATABASE,
                user_message="Could not update the message. Please try again.",
                recoverable=True
            ) from e
    
    def delete_message(self, message_id: str) -> bool:
        """
        Delete a message and its attachments.
        
        Args:
            message_id: The message ID
            
        Returns:
            True if deleted successfully
        """
        try:
            # Delete attachments first
            self.message_repo.delete_attachments_by_message(message_id)
            # Delete message
            return self.message_repo.delete(message_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to delete message",
                exception=e,
                context={'message_id': message_id}
            )
            raise AlpacaError(
                "Failed to delete message",
                category=ErrorCategory.DATABASE,
                user_message="Could not delete the message. Please try again.",
                recoverable=True
            ) from e
    
    def search_messages(
        self,
        search_term: str,
        chat_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search messages by content with performance monitoring.
        
        Args:
            search_term: The term to search for
            chat_id: Optional chat ID to limit search
            limit: Maximum number of results
            
        Returns:
            List of matching message dictionaries
        """
        if not search_term or not search_term.strip():
            return []
        
        import time
        start_time = time.time()
        
        try:
            results = self.message_repo.search(search_term.strip(), chat_id, limit)
            
            # Log performance metrics
            search_time_ms = (time.time() - start_time) * 1000
            if search_time_ms > 100:
                ErrorHandler.log_warning(
                    message=f"Slow search detected: {search_time_ms:.2f}ms",
                    context={
                        'search_term': search_term,
                        'chat_id': chat_id,
                        'result_count': len(results),
                        'search_time_ms': search_time_ms
                    }
                )
            
            return results
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to search messages",
                exception=e,
                context={'search_term': search_term, 'chat_id': chat_id}
            )
            return []
    
    def add_attachment(
        self,
        message_id: str,
        file_type: str,
        file_name: str,
        file_content: str
    ) -> str:
        """
        Add an attachment to a message.
        
        Args:
            message_id: The message ID
            file_type: Type of the file
            file_name: Name of the file
            file_content: Content of the file (base64 encoded for binary)
            
        Returns:
            The attachment ID
            
        Raises:
            AlpacaError: If attachment creation fails
        """
        # Validate inputs
        if not file_name or not file_name.strip():
            raise AlpacaError(
                "File name cannot be empty",
                category=ErrorCategory.VALIDATION,
                user_message="Please provide a file name.",
                recoverable=True
            )
        
        attachment_id = str(uuid.uuid4())
        
        try:
            self.message_repo.create_attachment(
                attachment_id,
                message_id,
                file_type,
                file_name.strip(),
                file_content
            )
            return attachment_id
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to add attachment",
                exception=e,
                context={'message_id': message_id, 'file_name': file_name}
            )
            raise AlpacaError(
                "Failed to add attachment",
                category=ErrorCategory.DATABASE,
                user_message="Could not save the attachment. Please try again.",
                recoverable=True
            ) from e
    
    def get_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """
        Get all attachments for a message.
        
        Args:
            message_id: The message ID
            
        Returns:
            List of attachment dictionaries
        """
        try:
            return self.message_repo.get_attachments(message_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve attachments",
                exception=e,
                context={'message_id': message_id}
            )
            return []
    
    def delete_attachment(self, attachment_id: str) -> bool:
        """
        Delete an attachment.
        
        Args:
            attachment_id: The attachment ID
            
        Returns:
            True if deleted successfully
        """
        try:
            return self.message_repo.delete_attachment(attachment_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to delete attachment",
                exception=e,
                context={'attachment_id': attachment_id}
            )
            raise AlpacaError(
                "Failed to delete attachment",
                category=ErrorCategory.DATABASE,
                user_message="Could not delete the attachment. Please try again.",
                recoverable=True
            ) from e
    
    def count_messages(self, chat_id: str) -> int:
        """
        Count messages in a chat.
        
        Args:
            chat_id: The chat ID
            
        Returns:
            Number of messages
        """
        try:
            return self.message_repo.count_by_chat(chat_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to count messages",
                exception=e,
                context={'chat_id': chat_id}
            )
            return 0
    
    def get_latest_message(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Get the most recent message in a chat.
        
        Args:
            chat_id: The chat ID
            
        Returns:
            Latest message dictionary or None if no messages
        """
        try:
            messages = self.message_repo.get_by_chat(chat_id, limit=1, offset=0)
            # Get the last message (most recent)
            if messages:
                # Since messages are ordered by date_time ASC, we need to get all and take the last
                all_messages = self.message_repo.get_by_chat(chat_id, limit=None)
                return all_messages[-1] if all_messages else None
            return None
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to get latest message",
                exception=e,
                context={'chat_id': chat_id}
            )
            return None
