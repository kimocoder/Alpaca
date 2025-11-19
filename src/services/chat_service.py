"""
Chat service for business logic related to chats.

This module provides business logic for chat operations,
including validation, orchestration, and export functionality.
"""
import json
import uuid
from typing import Optional, List, Dict, Any, Callable
from datetime import datetime

try:
    from repositories.chat_repository import ChatRepository
    from repositories.message_repository import MessageRepository
    from core.error_handler import ErrorHandler, AlpacaError, ErrorCategory
except ImportError:
    from ..repositories.chat_repository import ChatRepository
    from ..repositories.message_repository import MessageRepository
    from ..core.error_handler import ErrorHandler, AlpacaError, ErrorCategory


class ChatService:
    """Business logic for chat operations."""
    
    def __init__(
        self,
        chat_repo: Optional[ChatRepository] = None,
        message_repo: Optional[MessageRepository] = None
    ):
        """
        Initialize chat service.
        
        Args:
            chat_repo: Chat repository instance (creates new if None)
            message_repo: Message repository instance (creates new if None)
        """
        self.chat_repo = chat_repo or ChatRepository()
        self.message_repo = message_repo or MessageRepository()
    
    def create_chat(
        self,
        name: str,
        folder_id: Optional[str] = None,
        is_template: bool = False
    ) -> str:
        """
        Create a new chat with validation.
        
        Args:
            name: Chat name
            folder_id: Optional folder ID
            is_template: Whether this is a template chat
            
        Returns:
            The created chat ID
            
        Raises:
            AlpacaError: If validation fails or creation fails
        """
        # Validate name
        if not name or not name.strip():
            raise AlpacaError(
                "Chat name cannot be empty",
                category=ErrorCategory.VALIDATION,
                user_message="Please provide a name for the chat.",
                recoverable=True
            )
        
        name = name.strip()
        
        # Check for duplicate names
        existing_names = self.chat_repo.get_all_chat_names()
        if name in existing_names:
            # Generate unique name
            base_name = name
            counter = 1
            while name in existing_names:
                name = f"{base_name} ({counter})"
                counter += 1
        
        # Create chat
        chat_id = str(uuid.uuid4())
        chat_data = {
            'id': chat_id,
            'name': name,
            'folder': folder_id,
            'is_template': is_template
        }
        
        try:
            self.chat_repo.create(chat_data)
            return chat_id
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to create chat",
                exception=e,
                context={'name': name, 'folder_id': folder_id}
            )
            raise AlpacaError(
                "Failed to create chat",
                category=ErrorCategory.DATABASE,
                user_message="Could not create the chat. Please try again.",
                recoverable=True
            ) from e
    
    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a chat by ID.
        
        Args:
            chat_id: The chat ID
            
        Returns:
            Chat dictionary or None if not found
        """
        try:
            return self.chat_repo.get_by_id(chat_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve chat",
                exception=e,
                context={'chat_id': chat_id}
            )
            return None
    
    def get_chats_in_folder(
        self,
        folder_id: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """
        Get all chats in a folder.
        
        Args:
            folder_id: The folder ID (None for root)
            
        Returns:
            List of chat dictionaries
        """
        try:
            return self.chat_repo.get_by_folder(folder_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve chats",
                exception=e,
                context={'folder_id': folder_id}
            )
            return []
    
    def get_templates(self) -> List[Dict[str, Any]]:
        """
        Get all chat templates.
        
        Returns:
            List of template chat dictionaries
        """
        try:
            return self.chat_repo.get_templates()
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to retrieve templates",
                exception=e
            )
            return []
    
    def update_chat(
        self,
        chat_id: str,
        name: Optional[str] = None,
        folder_id: Optional[str] = None,
        is_template: Optional[bool] = None
    ) -> bool:
        """
        Update a chat.
        
        Args:
            chat_id: The chat ID
            name: New name (optional)
            folder_id: New folder ID (optional)
            is_template: New template status (optional)
            
        Returns:
            True if updated successfully
            
        Raises:
            AlpacaError: If validation fails
        """
        updates = {}
        
        if name is not None:
            if not name.strip():
                raise AlpacaError(
                    "Chat name cannot be empty",
                    category=ErrorCategory.VALIDATION,
                    user_message="Please provide a name for the chat.",
                    recoverable=True
                )
            updates['name'] = name.strip()
        
        if folder_id is not None:
            updates['folder'] = folder_id
        
        if is_template is not None:
            updates['is_template'] = is_template
        
        if not updates:
            return False
        
        try:
            return self.chat_repo.update(chat_id, updates)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to update chat",
                exception=e,
                context={'chat_id': chat_id, 'updates': updates}
            )
            raise AlpacaError(
                "Failed to update chat",
                category=ErrorCategory.DATABASE,
                user_message="Could not update the chat. Please try again.",
                recoverable=True
            ) from e
    
    def delete_chat(self, chat_id: str) -> bool:
        """
        Delete a chat and all its messages.
        
        Args:
            chat_id: The chat ID
            
        Returns:
            True if deleted successfully
        """
        try:
            # Delete messages first
            self.message_repo.delete_by_chat(chat_id)
            # Delete chat
            return self.chat_repo.delete(chat_id)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to delete chat",
                exception=e,
                context={'chat_id': chat_id}
            )
            raise AlpacaError(
                "Failed to delete chat",
                category=ErrorCategory.DATABASE,
                user_message="Could not delete the chat. Please try again.",
                recoverable=True
            ) from e
    
    def load_chat_messages(
        self,
        chat_id: str,
        limit: int = 50,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Load messages for a chat with pagination.
        
        Args:
            chat_id: The chat ID
            limit: Maximum number of messages to load
            offset: Number of messages to skip
            
        Returns:
            List of message dictionaries
        """
        try:
            return self.message_repo.get_by_chat(chat_id, limit, offset)
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to load chat messages",
                exception=e,
                context={'chat_id': chat_id, 'limit': limit, 'offset': offset}
            )
            return []
    
    def get_message_count(self, chat_id: str) -> int:
        """
        Get the total number of messages in a chat.
        
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
    
    def export_chat(
        self,
        chat_id: str,
        format: str,
        output_path: str,
        progress_callback: Optional[Callable[[int], None]] = None
    ) -> str:
        """
        Export a chat to a file.
        
        Args:
            chat_id: The chat ID to export
            format: Export format ('json', 'md', 'db')
            output_path: Path to save the exported file
            progress_callback: Optional callback for progress updates (0-100)
            
        Returns:
            Path to the exported file
            
        Raises:
            AlpacaError: If export fails
        """
        try:
            # Get chat data
            chat = self.chat_repo.get_by_id(chat_id)
            if not chat:
                raise AlpacaError(
                    f"Chat {chat_id} not found",
                    category=ErrorCategory.VALIDATION,
                    user_message="The chat you're trying to export doesn't exist.",
                    recoverable=False
                )
            
            if progress_callback:
                progress_callback(10)
            
            # Get all messages
            messages = self.message_repo.get_by_chat(chat_id, limit=None)
            
            if progress_callback:
                progress_callback(50)
            
            # Export based on format
            if format == 'json':
                self._export_json(chat, messages, output_path)
            elif format == 'md':
                self._export_markdown(chat, messages, output_path)
            elif format == 'db':
                self._export_database(chat, messages, output_path)
            else:
                raise AlpacaError(
                    f"Unsupported export format: {format}",
                    category=ErrorCategory.VALIDATION,
                    user_message=f"Export format '{format}' is not supported.",
                    recoverable=True
                )
            
            if progress_callback:
                progress_callback(100)
            
            return output_path
            
        except AlpacaError:
            raise
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to export chat",
                exception=e,
                context={'chat_id': chat_id, 'format': format}
            )
            raise AlpacaError(
                "Failed to export chat",
                category=ErrorCategory.FILESYSTEM,
                user_message="Could not export the chat. Please check file permissions.",
                recoverable=True
            ) from e
    
    def _export_json(
        self,
        chat: Dict[str, Any],
        messages: List[Dict[str, Any]],
        output_path: str
    ) -> None:
        """Export chat to JSON format."""
        export_data = {
            'chat': chat,
            'messages': messages,
            'exported_at': datetime.now().isoformat()
        }
        
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False)
    
    def _export_markdown(
        self,
        chat: Dict[str, Any],
        messages: List[Dict[str, Any]],
        output_path: str
    ) -> None:
        """Export chat to Markdown format."""
        with open(output_path, 'w', encoding='utf-8') as f:
            f.write(f"# {chat['name']}\n\n")
            f.write(f"Exported: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
            
            for msg in messages:
                role = msg['role'].capitalize()
                model = msg.get('model', '')
                timestamp = msg.get('date_time', '')
                content = msg.get('content', '')
                
                f.write(f"## {role}")
                if model:
                    f.write(f" ({model})")
                f.write(f"\n*{timestamp}*\n\n")
                f.write(f"{content}\n\n")
                f.write("---\n\n")
    
    def _export_database(
        self,
        chat: Dict[str, Any],
        messages: List[Dict[str, Any]],
        output_path: str
    ) -> None:
        """Export chat to SQLite database format."""
        import sqlite3
        
        # Create new database
        conn = sqlite3.connect(output_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute("""
            CREATE TABLE chat (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT,
                is_template INTEGER DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE message (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT,
                date_time TEXT,
                content TEXT,
                FOREIGN KEY (chat_id) REFERENCES chat(id)
            )
        """)
        
        # Insert chat
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)",
            (chat['id'], chat['name'], chat.get('folder'), int(chat.get('is_template', False)))
        )
        
        # Insert messages
        for msg in messages:
            cursor.execute(
                """
                INSERT INTO message (id, chat_id, role, model, date_time, content)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    msg['id'],
                    msg['chat_id'],
                    msg['role'],
                    msg.get('model', ''),
                    msg.get('date_time', ''),
                    msg.get('content', '')
                )
            )
        
        conn.commit()
        conn.close()
    
    def duplicate_chat(self, chat_id: str, new_name: Optional[str] = None) -> str:
        """
        Duplicate a chat with all its messages.
        
        Args:
            chat_id: The chat ID to duplicate
            new_name: Optional new name (defaults to "Copy of <original>")
            
        Returns:
            The new chat ID
            
        Raises:
            AlpacaError: If duplication fails
        """
        try:
            # Get original chat
            original_chat = self.chat_repo.get_by_id(chat_id)
            if not original_chat:
                raise AlpacaError(
                    f"Chat {chat_id} not found",
                    category=ErrorCategory.VALIDATION,
                    user_message="The chat you're trying to duplicate doesn't exist.",
                    recoverable=False
                )
            
            # Create new chat
            if new_name is None:
                new_name = f"Copy of {original_chat['name']}"
            
            new_chat_id = self.create_chat(
                name=new_name,
                folder_id=original_chat.get('folder'),
                is_template=original_chat.get('is_template', False)
            )
            
            # Copy messages
            messages = self.message_repo.get_by_chat(chat_id, limit=None)
            for msg in messages:
                new_msg = msg.copy()
                new_msg['id'] = str(uuid.uuid4())
                new_msg['chat_id'] = new_chat_id
                self.message_repo.create(new_msg)
            
            return new_chat_id
            
        except AlpacaError:
            raise
        except Exception as e:
            ErrorHandler.log_error(
                message="Failed to duplicate chat",
                exception=e,
                context={'chat_id': chat_id}
            )
            raise AlpacaError(
                "Failed to duplicate chat",
                category=ErrorCategory.DATABASE,
                user_message="Could not duplicate the chat. Please try again.",
                recoverable=True
            ) from e
