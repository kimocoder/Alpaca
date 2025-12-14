"""
Export service for exporting chats to various formats.
Provides functionality to export chat conversations to Markdown and JSON formats.
"""

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any


class ExportService:
    """Service for exporting chat conversations to different formats."""
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the export service.
        
        Args:
            db_path: Path to the SQLite database. If None, uses default path.
        """
        self.db_path = db_path
    
    def _get_connection(self) -> sqlite3.Connection:
        """Get a database connection."""
        if self.db_path:
            return sqlite3.connect(self.db_path)
        # Default path would be used in production
        raise ValueError("Database path not configured")
    
    def export_to_markdown(self, chat_id: str) -> str:
        """
        Export a chat to Markdown format.
        
        Args:
            chat_id: The ID of the chat to export
            
        Returns:
            Markdown formatted string of the chat
            
        Raises:
            ValueError: If chat is not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get chat info
        cursor.execute("SELECT name FROM chat WHERE id = ?", (chat_id,))
        chat_row = cursor.fetchone()
        
        if not chat_row:
            conn.close()
            raise ValueError(f"Chat with id '{chat_id}' not found")
        
        chat_name = chat_row[0]
        
        # Get messages
        cursor.execute(
            """
            SELECT id, role, model, date_time, content 
            FROM message 
            WHERE chat_id = ? 
            ORDER BY date_time
            """,
            (chat_id,)
        )
        messages = cursor.fetchall()
        
        conn.close()
        
        # Build markdown
        markdown_lines = [f"# {chat_name}", ""]
        
        for msg_id, role, model, timestamp, content in messages:
            # Add role header
            role_title = role.capitalize()
            markdown_lines.append(f"## {role_title}")
            
            # Add metadata
            metadata_parts = []
            if timestamp:
                metadata_parts.append(f"*{timestamp}*")
            if model:
                metadata_parts.append(f"*Model: {model}*")
            
            if metadata_parts:
                markdown_lines.append(" | ".join(metadata_parts))
            
            # Add content
            markdown_lines.append("")
            markdown_lines.append(content)
            markdown_lines.append("")
        
        return "\n".join(markdown_lines)
    
    def export_to_json(self, chat_id: str, include_metadata: bool = True) -> str:
        """
        Export a chat to JSON format.
        
        Args:
            chat_id: The ID of the chat to export
            include_metadata: Whether to include timestamps and model names
            
        Returns:
            JSON formatted string of the chat
            
        Raises:
            ValueError: If chat is not found
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        # Get chat info
        cursor.execute("SELECT id, name, folder FROM chat WHERE id = ?", (chat_id,))
        chat_row = cursor.fetchone()
        
        if not chat_row:
            conn.close()
            raise ValueError(f"Chat with id '{chat_id}' not found")
        
        chat_data = {
            "id": chat_row[0],
            "name": chat_row[1],
            "folder": chat_row[2]
        }
        
        # Get messages
        cursor.execute(
            """
            SELECT id, role, model, date_time, content 
            FROM message 
            WHERE chat_id = ? 
            ORDER BY date_time
            """,
            (chat_id,)
        )
        message_rows = cursor.fetchall()
        
        messages = []
        for msg_id, role, model, timestamp, content in message_rows:
            message = {
                "id": msg_id,
                "role": role,
                "content": content
            }
            
            if include_metadata:
                message["timestamp"] = timestamp
                if model:
                    message["model"] = model
            
            # Get attachments for this message
            cursor.execute(
                """
                SELECT id, type, name, content 
                FROM attachment 
                WHERE message_id = ?
                """,
                (msg_id,)
            )
            attachment_rows = cursor.fetchall()
            
            if attachment_rows:
                message["attachments"] = [
                    {
                        "id": att_id,
                        "type": att_type,
                        "name": att_name,
                        "content": att_content
                    }
                    for att_id, att_type, att_name, att_content in attachment_rows
                ]
            
            messages.append(message)
        
        conn.close()
        
        # Build result
        result = {
            "chat": chat_data,
            "messages": messages
        }
        
        if include_metadata:
            result["export_metadata"] = {
                "exported_at": datetime.now().isoformat()
            }
        
        return json.dumps(result, indent=2)
    
    def get_chat_list(self) -> List[Dict[str, Any]]:
        """
        Get a list of all available chats.
        
        Returns:
            List of chat dictionaries with id and name
        """
        conn = self._get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name FROM chat WHERE is_template = 0")
        rows = cursor.fetchall()
        
        conn.close()
        
        return [{"id": row[0], "name": row[1]} for row in rows]
