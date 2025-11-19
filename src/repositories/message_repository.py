"""
Message repository for database operations related to messages.

This module provides database access methods for message entities,
including CRUD operations and specialized queries.
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime

from .base_repository import BaseRepository


class MessageRepository(BaseRepository):
    """Repository for message-related database operations."""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize message repository.
        
        Args:
            db_path: Optional database path (uses default if None)
        """
        super().__init__(db_path)
        self._ensure_search_index()
    
    def _ensure_search_index(self) -> None:
        """
        Ensure full-text search index exists on message content.
        
        This creates an index on the content column to speed up LIKE queries.
        """
        try:
            # Check if index already exists
            results = self.execute_query(
                "SELECT name FROM sqlite_master WHERE type='index' AND name='idx_message_content'",
                context="_ensure_search_index_check"
            )
            
            if not results:
                # Create index on content column for faster searching
                self.execute_update(
                    "CREATE INDEX IF NOT EXISTS idx_message_content ON message(content)",
                    context="_ensure_search_index_create"
                )
                
                # Also create index on chat_id for faster filtered searches
                self.execute_update(
                    "CREATE INDEX IF NOT EXISTS idx_message_chat_id ON message(chat_id)",
                    context="_ensure_search_index_chat_id"
                )
                
                # Create index on date_time for faster ordering
                self.execute_update(
                    "CREATE INDEX IF NOT EXISTS idx_message_date_time ON message(date_time)",
                    context="_ensure_search_index_date_time"
                )
        except Exception:
            # If index creation fails, continue anyway (index might already exist)
            pass
    
    def get_by_id(self, message_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a message by its ID.
        
        Args:
            message_id: The message ID to retrieve
            
        Returns:
            Message dictionary or None if not found
        """
        results = self.execute_query(
            "SELECT id, chat_id, role, model, date_time, content FROM message WHERE id = ?",
            (message_id,),
            context="get_message_by_id"
        )
        
        if results:
            row = results[0]
            return {
                'id': row['id'],
                'chat_id': row['chat_id'],
                'role': row['role'],
                'model': row['model'],
                'date_time': row['date_time'],
                'content': row['content']
            }
        return None
    
    def get_by_chat(
        self,
        chat_id: str,
        limit: Optional[int] = None,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Get all messages for a specific chat with pagination.
        
        Args:
            chat_id: The chat ID
            limit: Maximum number of messages to return (None for all)
            offset: Number of messages to skip
            
        Returns:
            List of message dictionaries
        """
        if limit is None:
            query = """
                SELECT id, chat_id, role, model, date_time, content 
                FROM message 
                WHERE chat_id = ? 
                ORDER BY date_time ASC
            """
            params = (chat_id,)
        else:
            query = """
                SELECT id, chat_id, role, model, date_time, content 
                FROM message 
                WHERE chat_id = ? 
                ORDER BY date_time ASC 
                LIMIT ? OFFSET ?
            """
            params = (chat_id, limit, offset)
        
        results = self.execute_query(query, params, context="get_messages_by_chat")
        
        messages = []
        for row in results:
            messages.append({
                'id': row['id'],
                'chat_id': row['chat_id'],
                'role': row['role'],
                'model': row['model'],
                'date_time': row['date_time'],
                'content': row['content']
            })
        return messages
    
    def count_by_chat(self, chat_id: str) -> int:
        """
        Count messages in a chat.
        
        Args:
            chat_id: The chat ID
            
        Returns:
            Number of messages
        """
        results = self.execute_query(
            "SELECT COUNT(*) as count FROM message WHERE chat_id = ?",
            (chat_id,),
            context="count_messages_by_chat"
        )
        return results[0]['count'] if results else 0
    
    def create(self, message: Dict[str, Any]) -> str:
        """
        Create a new message.
        
        Args:
            message: Message dictionary with required fields
            
        Returns:
            The message ID
        """
        message_id = message['id']
        chat_id = message['chat_id']
        role = message['role']
        model = message.get('model', '')
        date_time = message.get('date_time', datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
        content = message.get('content', '')
        
        self.execute_update(
            """
            INSERT INTO message (id, chat_id, role, model, date_time, content) 
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (message_id, chat_id, role, model, date_time, content),
            context="create_message"
        )
        
        return message_id
    
    def update(self, message_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing message.
        
        Args:
            message_id: The message ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if message was updated, False if not found
        """
        # Build dynamic update query
        set_clauses = []
        params = []
        
        if 'content' in updates:
            set_clauses.append("content = ?")
            params.append(updates['content'])
        
        if 'model' in updates:
            set_clauses.append("model = ?")
            params.append(updates['model'])
        
        if 'role' in updates:
            set_clauses.append("role = ?")
            params.append(updates['role'])
        
        if 'date_time' in updates:
            set_clauses.append("date_time = ?")
            params.append(updates['date_time'])
        
        if not set_clauses:
            return False
        
        params.append(message_id)
        query = f"UPDATE message SET {', '.join(set_clauses)} WHERE id = ?"
        
        affected = self.execute_update(query, tuple(params), context="update_message")
        return affected > 0
    
    def delete(self, message_id: str) -> bool:
        """
        Delete a message.
        
        Args:
            message_id: The message ID to delete
            
        Returns:
            True if message was deleted, False if not found
        """
        affected = self.execute_update(
            "DELETE FROM message WHERE id = ?",
            (message_id,),
            context="delete_message"
        )
        return affected > 0
    
    def delete_by_chat(self, chat_id: str) -> int:
        """
        Delete all messages in a chat.
        
        Args:
            chat_id: The chat ID
            
        Returns:
            Number of messages deleted
        """
        return self.execute_update(
            "DELETE FROM message WHERE chat_id = ?",
            (chat_id,),
            context="delete_messages_by_chat"
        )
    
    def search(
        self,
        search_term: str,
        chat_id: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Search messages by content using indexed search.
        
        Args:
            search_term: The term to search for
            chat_id: Optional chat ID to limit search
            limit: Maximum number of results
            
        Returns:
            List of matching message dictionaries ordered by date (most recent first)
        """
        # Return empty list for empty search terms
        if not search_term or not search_term.strip():
            return []
        
        # Escape special SQL LIKE characters to prevent SQL injection
        # and ensure literal matching of special characters
        # First escape the backslash itself, then escape % and _
        escaped_term = search_term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        
        if chat_id:
            query = """
                SELECT id, chat_id, role, model, date_time, content 
                FROM message 
                WHERE chat_id = ? AND content LIKE ? ESCAPE '\\'
                ORDER BY date_time DESC 
                LIMIT ?
            """
            params = (chat_id, f"%{escaped_term}%", limit)
        else:
            query = """
                SELECT id, chat_id, role, model, date_time, content 
                FROM message 
                WHERE content LIKE ? ESCAPE '\\'
                ORDER BY date_time DESC 
                LIMIT ?
            """
            params = (f"%{escaped_term}%", limit)
        
        results = self.execute_query(query, params, context="search_messages")
        
        messages = []
        for row in results:
            messages.append({
                'id': row['id'],
                'chat_id': row['chat_id'],
                'role': row['role'],
                'model': row['model'],
                'date_time': row['date_time'],
                'content': row['content']
            })
        return messages
    
    def get_attachments(self, message_id: str) -> List[Dict[str, Any]]:
        """
        Get all attachments for a message.
        
        Args:
            message_id: The message ID
            
        Returns:
            List of attachment dictionaries
        """
        results = self.execute_query(
            "SELECT id, type, name, content FROM attachment WHERE message_id = ?",
            (message_id,),
            context="get_message_attachments"
        )
        
        attachments = []
        for row in results:
            attachments.append({
                'id': row['id'],
                'type': row['type'],
                'name': row['name'],
                'content': row['content']
            })
        return attachments
    
    def create_attachment(
        self,
        attachment_id: str,
        message_id: str,
        file_type: str,
        file_name: str,
        file_content: str
    ) -> str:
        """
        Create a new attachment for a message.
        
        Args:
            attachment_id: The attachment ID
            message_id: The message ID
            file_type: Type of the file
            file_name: Name of the file
            file_content: Content of the file
            
        Returns:
            The attachment ID
        """
        self.execute_update(
            """
            INSERT INTO attachment (id, message_id, type, name, content) 
            VALUES (?, ?, ?, ?, ?)
            """,
            (attachment_id, message_id, file_type, file_name, file_content),
            context="create_attachment"
        )
        return attachment_id
    
    def delete_attachment(self, attachment_id: str) -> bool:
        """
        Delete an attachment.
        
        Args:
            attachment_id: The attachment ID to delete
            
        Returns:
            True if attachment was deleted, False if not found
        """
        affected = self.execute_update(
            "DELETE FROM attachment WHERE id = ?",
            (attachment_id,),
            context="delete_attachment"
        )
        return affected > 0
    
    def delete_attachments_by_message(self, message_id: str) -> int:
        """
        Delete all attachments for a message.
        
        Args:
            message_id: The message ID
            
        Returns:
            Number of attachments deleted
        """
        return self.execute_update(
            "DELETE FROM attachment WHERE message_id = ?",
            (message_id,),
            context="delete_attachments_by_message"
        )
