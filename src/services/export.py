"""
Export service for Alpaca application.
Provides functionality to export chats in various formats (Markdown, JSON).
"""

import json
import os
import sqlite3
from datetime import datetime
from typing import Optional, List, Dict, Any


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


class ExportService:
    """
    Service for exporting chats in various formats.
    
    Supports exporting to:
    - Markdown format with preserved code blocks
    - JSON format with full metadata
    """
    
    def __init__(self, db_path: Optional[str] = None):
        """
        Initialize the export service with database connection.
        
        Args:
            db_path: Optional custom database path (mainly for testing)
        """
        if db_path:
            self.db_path = db_path
        else:
            self.db_path = os.path.join(_get_data_dir(), "alpaca.db")
    
    def export_to_markdown(self, chat_id: str) -> str:
        """
        Export chat to Markdown format with preserved code blocks.
        
        Args:
            chat_id: The unique identifier of the chat to export
        
        Returns:
            Markdown-formatted string of the chat conversation
        
        Raises:
            ValueError: If chat_id is not found in database
            sqlite3.Error: If database operation fails
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get chat information
            chat_row = cursor.execute(
                "SELECT id, name FROM chat WHERE id=?",
                (chat_id,)
            ).fetchone()
            
            if not chat_row:
                conn.close()
                raise ValueError(f"Chat with id '{chat_id}' not found")
            
            chat_name = chat_row[1]
            
            # Get all messages for this chat
            messages = cursor.execute(
                "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC",
                (chat_id,)
            ).fetchall()
            
            conn.close()
            
            # Build markdown content
            markdown_lines = []
            markdown_lines.append(f"# {chat_name}")
            markdown_lines.append("")
            
            for message in messages:
                message_id, role, model, date_time_str, content = message
                
                # Format the message header
                if role == "user":
                    markdown_lines.append(f"## User")
                elif role == "assistant":
                    if model:
                        markdown_lines.append(f"## Assistant ({model})")
                    else:
                        markdown_lines.append(f"## Assistant")
                elif role == "system":
                    markdown_lines.append(f"## System")
                
                # Add timestamp
                markdown_lines.append(f"*{date_time_str}*")
                markdown_lines.append("")
                
                # Add content - preserve code blocks and formatting
                markdown_lines.append(content)
                markdown_lines.append("")
                markdown_lines.append("---")
                markdown_lines.append("")
            
            return "\n".join(markdown_lines)
            
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error during export: {e}")
    
    def export_to_json(self, chat_id: str, include_metadata: bool = True) -> str:
        """
        Export chat to JSON format with optional metadata.
        
        Args:
            chat_id: The unique identifier of the chat to export
            include_metadata: Whether to include timestamps and model names (default: True)
        
        Returns:
            JSON-formatted string of the chat conversation
        
        Raises:
            ValueError: If chat_id is not found in database
            sqlite3.Error: If database operation fails
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Get chat information
            chat_row = cursor.execute(
                "SELECT id, name, folder, is_template FROM chat WHERE id=?",
                (chat_id,)
            ).fetchone()
            
            if not chat_row:
                conn.close()
                raise ValueError(f"Chat with id '{chat_id}' not found")
            
            chat_data = {
                "id": chat_row[0],
                "name": chat_row[1],
                "folder": chat_row[2],
                "is_template": bool(chat_row[3])
            }
            
            # Get all messages for this chat
            messages = cursor.execute(
                "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC",
                (chat_id,)
            ).fetchall()
            
            # Build messages list
            messages_data = []
            for message in messages:
                message_id, role, model, date_time_str, content = message
                
                message_dict = {
                    "id": message_id,
                    "role": role,
                    "content": content
                }
                
                # Add metadata if requested
                if include_metadata:
                    message_dict["model"] = model
                    message_dict["timestamp"] = date_time_str
                
                # Get attachments for this message
                attachments = cursor.execute(
                    "SELECT id, type, name, content FROM attachment WHERE message_id=?",
                    (message_id,)
                ).fetchall()
                
                if attachments:
                    message_dict["attachments"] = [
                        {
                            "id": att[0],
                            "type": att[1],
                            "name": att[2],
                            "content": att[3]
                        }
                        for att in attachments
                    ]
                
                messages_data.append(message_dict)
            
            conn.close()
            
            # Build final export structure
            export_data = {
                "chat": chat_data,
                "messages": messages_data
            }
            
            if include_metadata:
                export_data["export_metadata"] = {
                    "exported_at": datetime.now().strftime("%Y/%m/%d %H:%M:%S"),
                    "version": "1.0"
                }
            
            return json.dumps(export_data, indent=2, ensure_ascii=False)
            
        except sqlite3.Error as e:
            raise sqlite3.Error(f"Database error during export: {e}")
    
    def get_chat_list(self) -> List[Dict[str, Any]]:
        """
        Get a list of all available chats for export selection.
        
        Returns:
            List of dictionaries containing chat id and name
        """
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            chats = cursor.execute(
                "SELECT id, name FROM chat ORDER BY name ASC"
            ).fetchall()
            
            conn.close()
            
            return [{"id": chat[0], "name": chat[1]} for chat in chats]
            
        except sqlite3.Error as e:
            print(f"Database error getting chat list: {e}")
            return []
