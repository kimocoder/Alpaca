"""
Chat repository for database operations related to chats.

This module provides database access methods for chat entities,
including CRUD operations and specialized queries.
"""
from typing import Optional, List, Dict, Any
from datetime import datetime

from .base_repository import BaseRepository


class ChatRepository(BaseRepository):
    """Repository for chat-related database operations."""
    
    def get_by_id(self, chat_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a chat by its ID.
        
        Args:
            chat_id: The chat ID to retrieve
            
        Returns:
            Chat dictionary or None if not found
        """
        results = self.execute_query(
            "SELECT id, name, folder, is_template FROM chat WHERE id = ?",
            (chat_id,),
            context="get_chat_by_id"
        )
        
        if results:
            row = results[0]
            return {
                'id': row['id'],
                'name': row['name'],
                'folder': row['folder'],
                'is_template': bool(row['is_template'])
            }
        return None
    
    def get_by_folder(self, folder_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Get all chats in a specific folder.
        
        Args:
            folder_id: The folder ID (None for root folder)
            
        Returns:
            List of chat dictionaries
        """
        if folder_id is None:
            results = self.execute_query(
                """
                SELECT chat.id, chat.name, chat.is_template, 
                       MAX(message.date_time) AS latest_message_time 
                FROM chat 
                LEFT JOIN message ON chat.id = message.chat_id 
                WHERE chat.folder IS NULL 
                GROUP BY chat.id 
                ORDER BY latest_message_time DESC
                """,
                context="get_chats_by_folder_root"
            )
        else:
            results = self.execute_query(
                """
                SELECT chat.id, chat.name, chat.is_template, 
                       MAX(message.date_time) AS latest_message_time 
                FROM chat 
                LEFT JOIN message ON chat.id = message.chat_id 
                WHERE chat.folder = ? 
                GROUP BY chat.id 
                ORDER BY latest_message_time DESC
                """,
                (folder_id,),
                context="get_chats_by_folder"
            )
        
        chats = []
        for row in results:
            chats.append({
                'id': row['id'],
                'name': row['name'],
                'is_template': bool(row['is_template']),
                'latest_message_time': row['latest_message_time']
            })
        return chats
    
    def get_templates(self) -> List[Dict[str, Any]]:
        """
        Get all chat templates.
        
        Returns:
            List of template chat dictionaries
        """
        results = self.execute_query(
            """
            SELECT chat.id, chat.name, MAX(message.date_time) AS latest_message_time 
            FROM chat 
            LEFT JOIN message ON chat.id = message.chat_id 
            WHERE chat.is_template = 1 
            GROUP BY chat.id 
            ORDER BY latest_message_time DESC
            """,
            context="get_templates"
        )
        
        templates = []
        for row in results:
            templates.append({
                'id': row['id'],
                'name': row['name'],
                'latest_message_time': row['latest_message_time']
            })
        return templates
    
    def create(self, chat: Dict[str, Any]) -> str:
        """
        Create a new chat.
        
        Args:
            chat: Chat dictionary with 'id', 'name', 'folder', 'is_template'
            
        Returns:
            The chat ID
        """
        chat_id = chat['id']
        name = chat['name']
        folder = chat.get('folder')
        is_template = int(chat.get('is_template', False))
        
        if folder is None:
            self.execute_update(
                "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, ?)",
                (chat_id, name, is_template),
                context="create_chat"
            )
        else:
            self.execute_update(
                "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, ?)",
                (chat_id, name, folder, is_template),
                context="create_chat"
            )
        
        return chat_id
    
    def update(self, chat_id: str, updates: Dict[str, Any]) -> bool:
        """
        Update an existing chat.
        
        Args:
            chat_id: The chat ID to update
            updates: Dictionary of fields to update
            
        Returns:
            True if chat was updated, False if not found
        """
        # Build dynamic update query
        set_clauses = []
        params = []
        
        if 'name' in updates:
            set_clauses.append("name = ?")
            params.append(updates['name'])
        
        if 'folder' in updates:
            if updates['folder'] is None:
                set_clauses.append("folder = NULL")
            else:
                set_clauses.append("folder = ?")
                params.append(updates['folder'])
        
        if 'is_template' in updates:
            set_clauses.append("is_template = ?")
            params.append(int(updates['is_template']))
        
        if not set_clauses:
            return False
        
        params.append(chat_id)
        query = f"UPDATE chat SET {', '.join(set_clauses)} WHERE id = ?"
        
        affected = self.execute_update(query, tuple(params), context="update_chat")
        return affected > 0
    
    def delete(self, chat_id: str) -> bool:
        """
        Delete a chat and all related data.
        
        Args:
            chat_id: The chat ID to delete
            
        Returns:
            True if chat was deleted, False if not found
        """
        # Note: Foreign key constraints should handle cascade deletion
        # of messages and attachments if properly configured
        affected = self.execute_update(
            "DELETE FROM chat WHERE id = ?",
            (chat_id,),
            context="delete_chat"
        )
        return affected > 0
    
    def exists(self, chat_id: str) -> bool:
        """
        Check if a chat exists.
        
        Args:
            chat_id: The chat ID to check
            
        Returns:
            True if chat exists, False otherwise
        """
        results = self.execute_query(
            "SELECT 1 FROM chat WHERE id = ? LIMIT 1",
            (chat_id,),
            context="check_chat_exists"
        )
        return len(results) > 0
    
    def get_all_chat_names(self) -> List[str]:
        """
        Get all chat names (useful for duplicate checking).
        
        Returns:
            List of chat names
        """
        results = self.execute_query(
            "SELECT name FROM chat",
            context="get_all_chat_names"
        )
        return [row['name'] for row in results]
