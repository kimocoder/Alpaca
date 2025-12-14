"""
This file manages the SQLite saving system backing Alpaca; it's responsible
for storing chats, instances, preferences and more.
"""

# sql_manager.py

from typing import Union
import sqlite3
import uuid
import datetime
import os
import shutil
import json
import sys

from . import widgets as Widgets
from .constants import data_dir
from gi.repository import Gio, GLib

def format_datetime(dt:datetime.datetime) -> str:
    """
    Format a datetime object into a human-readable string.
    
    Formats the datetime based on how recent it is:
    - Today: shows only time
    - This year: shows month, day, and time
    - Other years: shows full date and time
    
    Respects the ALPACA_USE_24H environment variable for 12/24 hour format.
    
    Args:
        dt: The datetime object to format
        
    Returns:
        A formatted datetime string
    """
    date = GLib.DateTime.new(
        GLib.DateTime.new_now_local().get_timezone(),
        dt.year,
        dt.month,
        dt.day,
        dt.hour,
        dt.minute,
        dt.second
    )
    current_date = GLib.DateTime.new_now_local()
    if date.format("%Y/%m/%d") == current_date.format("%Y/%m/%d"):
        if os.getenv('ALPACA_USE_24H', '0') == '1':
            return date.format("%H:%M")
        else:
            return date.format("%I:%M %p")
    if date.format("%Y") == current_date.format("%Y"):
        if os.getenv('ALPACA_USE_24H', '0') == '1':
            return date.format("%b %d, %H:%M")
        else:
            return date.format("%b %d, %H:%M")
    if os.getenv('ALPACA_USE_24H', '0') == '1':
        return date.format("%b %d %Y, %H:%M")
    else:
        return date.format("%b %d %Y, %H:%M")

def nanoseconds_to_timestamp(ns:int) -> str or None:
    """
    Convert nanoseconds to a human-readable timestamp string.
    
    Args:
        ns: Time duration in nanoseconds
        
    Returns:
        Formatted timestamp string (HH:MM:SS, MM:SS, or "X seconds"), or None if ns is falsy
    """
    if ns:
        total_seconds = ns / 1_000_000_000

        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)

        if hours > 0:
            return f'{hours:02}:{minutes:02}:{seconds:02}'
        elif minutes > 0:
            return f'{minutes:02}:{seconds:02}'
        else:
            return _('{} seconds').format(seconds)

def dict_to_metadata_string(data:dict) -> str:
    """
    Convert model response metadata dictionary to a formatted Markdown table string.
    
    Includes metrics like total duration, load duration, token counts, and evaluation rates.
    
    Args:
        data: Dictionary containing model response metadata
        
    Returns:
        Markdown-formatted table string with metrics and values
    """
    metadata_parameters = {
        _('Total Duration'): nanoseconds_to_timestamp(data.get('total_duration')),
        _('Load Duration'): nanoseconds_to_timestamp(data.get('load_duration'))
    }
    if data.get('prompt_eval_count') and data.get('prompt_eval_duration'):
        metadata_parameters[_('Prompt Eval Count')] =  _('{} tokens').format(data.get('prompt_eval_count'))
        metadata_parameters[_('Prompt Eval Duration')] = nanoseconds_to_timestamp(data.get('prompt_eval_duration'))
        prompt_eval_rate = data.get('prompt_eval_count') / (data.get('prompt_eval_duration') / (10**9))
        metadata_parameters[_('Prompt Eval Rate')] = _('{} tokens/s').format(round(prompt_eval_rate, 2))
    if data.get('eval_count') and data.get('eval_duration'):
        metadata_parameters[_('Eval Count')] = _('{} tokens').format(data.get('eval_count'))
        metadata_parameters[_('Eval Duration')] = nanoseconds_to_timestamp(data.get('eval_duration'))
        eval_rate = data.get('eval_count') / (data.get('eval_duration') / (10**9))
        metadata_parameters[_('Eval Rate')] = _('{} tokens/s').format(round(eval_rate, 2))
    metadata_result = ['| {} | {} |'.format(_('Metric'), _('Value')), '| ---- | ---- |']
    metadata_result += ['| {} | {} |'.format(k, vl) for k, vl in metadata_parameters.items() if vl]
    return '\n'.join(metadata_result)

def generate_uuid() -> str:
    """
    Generate a unique identifier combining timestamp and UUID.
    
    Returns:
        A unique string identifier in format: YYYYMMDDHHMMSSμμμμμμ + UUID hex
    """
    return f"{datetime.datetime.today().strftime('%Y%m%d%H%M%S%f')}{uuid.uuid4().hex}"

def generate_numbered_name(name: str, compare_list: "list[str]") -> str:
    """
    Generates a numbered name from two parameters, the name and a list to
    compare it to. If the name of the chat already exists in our compare list,
    we number it to make it distinctive of the original.
    """

    if name in compare_list:
        for i in range(1, len(compare_list) + 1):
            if "." in name:
                if (
                    f"{'.'.join(name.split('.')[:-1])} {i}.{name.split('.')[-1]}"
                    not in compare_list
                ):
                    name = f"{'.'.join(name.split('.')[:-1])} {i}.{name.split('.')[-1]}"
                    break
            else:
                if f"{name} {i}" not in compare_list:
                    name = f"{name} {i}"
                    break
    return name

def prettify_model_name(name:str, separated:bool=False) -> str or tuple:
    """
    Convert a model name to a human-readable format.
    
    Handles model names with tags (e.g., "llama2:13b") and formats them nicely.
    Omits common tags like "latest" and "custom" from display.
    
    Args:
        name: The model name to prettify
        separated: If True, return tuple of (model_name, tag); if False, return formatted string
        
    Returns:
        Either a formatted string or tuple of (model_name, tag) depending on separated parameter
    """
    if name:
        if ':' in name:
            name = name.split(':')
            if separated:
                return name[0].replace('-', ' ').title(), name[1].replace('-', ' ').title()
            elif name[1].lower() in ('latest', 'custom'):
                return name[0].replace('-', ' ').title()
            else:
                return '{} ({})'.format(name[0].replace('-', ' ').title(), name[1].replace('-', ' ').title())
        else:
            if separated:
                return name.replace('-', ' ').title(), None
            else:
                return name.replace('-', ' ').title()

class SQLiteConnection:
    """
    This class manages the context for SQLite database connections.
    """

    sql_path: str = os.path.join(data_dir, "alpaca.db")
    sqlite_con: "Union[sqlite3.Connection, None]" = None
    cursor: "Union[sqlite3.Cursor, None]" = None

    def __enter__(self):
        """
        What happens when the context is entered - in this case, establish a
        connection to the database.
        """

        self.sqlite_con = sqlite3.connect(self.sql_path)
        self.cursor = self.sqlite_con.cursor()

        return self

    def __exit__(self, exception_type, exception_val, traceback) -> None:
        """
        What to do once the context is exited again: commit and close the
        connection.
        """

        if self.sqlite_con.in_transaction:
            self.sqlite_con.commit()

        self.sqlite_con.close()


class Instance:
    """
    An instance class for the SQLite database used by Alpaca - it can be used
    to interface with the database in a modular and extensible way.
    """

    def initialize():
        """
        Initialize the SQLite database with required tables and perform migrations.
        
        Creates all necessary tables if they don't exist, handles schema migrations
        from older versions, and migrates legacy data structures to current format.
        """
        if os.path.exists(os.path.join(data_dir, "chats_test.db")) and not os.path.exists(os.path.join(data_dir, "alpaca.db")):
            shutil.move(os.path.join(data_dir, "chats_test.db"), os.path.join(data_dir, "alpaca.db"))

        with SQLiteConnection() as c:
            tables = {
                "chat": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "name": "TEXT NOT NULL",
                    "folder": "TEXT",
                    "is_template": "INTEGER NOT NULL DEFAULT 0"
                },
                "message": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "chat_id": "TEXT NOT NULL",
                    "role": "TEXT NOT NULL",
                    "model": "TEXT",
                    "date_time": "DATETIME NOT NULL",
                    "content": "TEXT NOT NULL",
                },
                "attachment": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "message_id": "TEXT NOT NULL",
                    "type": "TEXT NOT NULL",
                    "name": "TEXT NOT NULL",
                    "content": "TEXT NOT NULL",
                },
                "model_preferences": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "picture": "TEXT",
                    "voice": "TEXT"
                },
                "instance": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "pinned": "INTEGER NOT NULL",
                    "type": "TEXT NOT NULL",
                    "properties": "TEXT NOT NULL" #JSON
                },
                "tool_parameters": {
                    "name": "TEXT NOT NULL PRIMARY KEY",
                    "variables": "TEXT NOT NULL",
                    "activated": "INTEGER NOT NULL"
                },
                "online_instance_model_list": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "list": "TEXT NOT NULL" #JSON
                },
                "chat_folder": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "name": "TEXT NOT NULL",
                    "color": "TEXT",
                    "parent": "TEXT"
                },
                "prompt": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "name": "TEXT NOT NULL",
                    "content": "TEXT NOT NULL",
                    "category": "TEXT",
                    "created_at": "DATETIME NOT NULL"
                },
                "bookmark": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "message_id": "TEXT NOT NULL",
                    "created_at": "DATETIME NOT NULL"
                },
                "model_pin": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "model_name": "TEXT NOT NULL",
                    "instance_id": "TEXT NOT NULL",
                    "pin_order": "INTEGER NOT NULL"
                },
                "statistics": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "event_type": "TEXT NOT NULL",
                    "model": "TEXT",
                    "tokens_used": "INTEGER",
                    "response_time_ms": "INTEGER",
                    "timestamp": "DATETIME NOT NULL"
                },
                "backup_schedule": {
                    "id": "TEXT NOT NULL PRIMARY KEY",
                    "interval_hours": "INTEGER NOT NULL",
                    "backup_path": "TEXT NOT NULL",
                    "last_backup": "DATETIME",
                    "enabled": "INTEGER NOT NULL DEFAULT 1"
                }
            }

            for table_name, columns in tables.items():
                columns_def = ", ".join([f"{col_name} {col_def}" for col_name, col_def in columns.items()])
                c.cursor.execute(f"CREATE TABLE IF NOT EXISTS {table_name} ({columns_def})")

            c.cursor.execute("PRAGMA table_info(chat)")
            columns = [col[1] for col in c.cursor.fetchall()]
            if 'folder' not in columns:
                c.cursor.execute("ALTER TABLE chat ADD COLUMN folder TEXT")
            if 'is_template' not in columns:
                c.cursor.execute("ALTER TABLE chat ADD COLUMN is_template INTEGER NOT NULL DEFAULT 0") # Treated as boolean 0/1
            if 'type' in columns: # Rebuild chat table (remove type)
                c.cursor.execute("ALTER TABLE chat RENAME to chat_old")
                columns_def = ", ".join([f"{col_name} {col_def}" for col_name, col_def in tables.get('chat').items()])
                c.cursor.execute(f"CREATE TABLE IF NOT EXISTS chat ({columns_def})")
                c.cursor.execute(f"INSERT INTO chat (id, name) SELECT id, name FROM chat_old")
                c.cursor.execute(f"DROP TABLE chat_old")
            # Remove stuff from previous versions (cleaning)
            try:
                model_pictures = c.cursor.execute("SELECT id, picture FROM model")
                for p in model_pictures:
                    c.cursor.execute("INSERT INTO model_preferences (id, picture) VALUES (?, ?)", (p[0], p[1]))
                c.cursor.execute("DROP TABLE model")
            except Exception:
                pass

            # Move preferences to GLib
            if c.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' and name='preferences';").fetchall() != []:
                settings = Gio.Settings(schema_id="com.jeffser.Alpaca")
                settings_keys = {
                    'skip_welcome_page': 'skip-welcome',
                    'selected_instance': 'selected-instance',
                    'last_notice_seen': 'last-notice-seen',
                    'selected_chat': 'default-chat',
                    'zoom': 'zoom',
                    'run_on_background': 'hide-on-close',
                    'powersaver_warning': 'powersaver-warning',
                    'mic_auto_send': 'stt-auto-send',
                }
                old_preferences = Instance.get_preferences()
                for old_key, new_key in settings_keys.items():
                    old_value = old_preferences.get(old_key)
                    if old_value:
                        if isinstance(old_value, bool):
                            settings.set_boolean(new_key, old_value)
                        elif isinstance(old_value, int):
                            settings.set_int(new_key, old_value)
                        elif isinstance(old_value, str):
                            settings.set_string(new_key, old_value)
                c.cursor.execute("DROP TABLE preferences")

            # Move Instances to new table
            if c.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' and name='instances';").fetchall() != []:
                for old_ins in Instance.get_instances_DEPRECATED():
                    properties = {
                        'name': old_ins.get('name'),
                        'temperature': old_ins.get('temperature'),
                        'default_model': old_ins.get('default_model'),
                        'title_model': old_ins.get('title_model')
                    }
                    if old_ins.get('max_tokens', -1) != -1:
                        properties['max_tokens'] = old_ins.get('max_tokens')
                    if old_ins.get('type') in ('openai:generic', 'ollama:managed', 'ollama') and old_ins.get('url'):
                        properties['url'] = old_ins.get('url')
                    if old_ins.get('type') != 'ollama:managed':
                        properties['api'] = old_ins.get('api')
                    if old_ins.get('type') not in ('venice', 'deepseek', 'gemini') and old_ins.get('seed'):
                        properties['seed'] = old_ins.get('seed')
                    if old_ins.get('type') == 'ollama:managed':
                        properties['overrides'] = old_ins.get('overrides')
                        properties['model_directory'] = old_ins.get('model_directory')

                    c.cursor.execute("INSERT INTO instance (id, pinned, type, properties) VALUES (?, ?, ?, ?)", (old_ins.get('id'), old_ins.get('pinned'), old_ins.get('type'), json.dumps(properties)))
                c.cursor.execute("DROP TABLE instances")

            # Remove tool_parameters table
            if c.cursor.execute("SELECT name FROM sqlite_master WHERE type='table' and name='tool_parameters';").fetchall() != []:
                c.cursor.execute("DROP TABLE tool_parameters")


    ###########
    ## CHATS ##
    ###########

    def get_chats_by_folder(folder_id:str=None) -> list:
        """
        Retrieve all chats in a specific folder, ordered by most recent message.
        
        Args:
            folder_id: The folder ID to filter by, or None for root-level chats
            
        Returns:
            List of tuples containing (chat_id, chat_name, is_template, latest_message_time)
        """
        with SQLiteConnection() as c:
            if folder_id is None:
                chats = c.cursor.execute(
                    "SELECT chat.id, chat.name, chat.is_template, MAX(message.date_time) AS \
                    latest_message_time FROM chat LEFT JOIN message ON chat.id = message.chat_id \
                    WHERE chat.folder IS NULL \
                    GROUP BY chat.id ORDER BY latest_message_time DESC"
                ).fetchall()
            else:
                chats = c.cursor.execute(
                    "SELECT chat.id, chat.name, chat.is_template, MAX(message.date_time) AS \
                    latest_message_time FROM chat LEFT JOIN message ON chat.id = message.chat_id \
                    WHERE chat.folder=? \
                    GROUP BY chat.id ORDER BY latest_message_time DESC",
                    (folder_id,)
                ).fetchall()

        return chats

    def get_templates() -> list:
        """
        Retrieve all chat templates, ordered by most recent message.
        
        Returns:
            List of tuples containing (chat_id, chat_name, latest_message_time)
        """
        with SQLiteConnection() as c:
            templates = c.cursor.execute(
                "SELECT chat.id, chat.name, MAX(message.date_time) AS \
                latest_message_time FROM chat LEFT JOIN message ON chat.id = message.chat_id \
                WHERE chat.is_template = 1 \
                GROUP BY chat.id ORDER BY latest_message_time DESC"
            ).fetchall()
        return templates

    def get_messages(chat) -> list:
        """
        Retrieve all messages for a specific chat.
        
        Args:
            chat: The chat object containing chat_id
            
        Returns:
            List of tuples containing (id, role, model, date_time, content)
        """
        with SQLiteConnection() as c:
            messages = c.cursor.execute(
                "SELECT id, role, model, date_time, content FROM message WHERE chat_id=?",
                (chat.chat_id,),
            ).fetchall()

        return messages

    def get_messages_paginated(chat, limit: int = 50, offset: int = 0) -> list:
        """
        Get messages for a chat with pagination support.
        
        Args:
            chat: The chat object
            limit: Maximum number of messages to return
            offset: Number of messages to skip from the start
            
        Returns:
            List of message tuples (id, role, model, date_time, content)
        """
        with SQLiteConnection() as c:
            messages = c.cursor.execute(
                "SELECT id, role, model, date_time, content FROM message WHERE chat_id=? ORDER BY date_time ASC LIMIT ? OFFSET ?",
                (chat.chat_id, limit, offset),
            ).fetchall()

        return messages

    def get_message_count(chat) -> int:
        """
        Get the total number of messages in a chat.
        
        Args:
            chat: The chat object
            
        Returns:
            Total number of messages
        """
        with SQLiteConnection() as c:
            count = c.cursor.execute(
                "SELECT COUNT(*) FROM message WHERE chat_id=?",
                (chat.chat_id,),
            ).fetchone()[0]

        return count

    def get_attachments(message) -> list:
        """
        Retrieve all attachments for a specific message.
        
        Args:
            message: The message object containing message_id
            
        Returns:
            List of tuples containing (id, type, name, content)
        """
        with SQLiteConnection() as c:
            attachments = c.cursor.execute(
                "SELECT id, type, name, content FROM attachment WHERE message_id=?",
                (message.message_id,),
            ).fetchall()

        return attachments

    def export_db(chat, export_sql_path: str) -> None:
        """
        Export a chat and all its messages and attachments to a separate database file.
        
        Args:
            chat: The chat object to export
            export_sql_path: Path where the exported database should be saved
        """
        with SQLiteConnection() as c:
            c.cursor.execute("ATTACH DATABASE ? AS export", (export_sql_path,))
            c.cursor.execute(
                "CREATE TABLE export.chat AS SELECT * FROM chat WHERE id=?",
                (chat.chat_id,),
            )
            c.cursor.execute(
                "CREATE TABLE export.message AS SELECT * FROM message WHERE chat_id=?",
                (chat.chat_id,),
            )
            c.cursor.execute(
                "CREATE TABLE export.attachment AS SELECT a.* FROM attachment as a JOIN message m ON a.message_id = m.id WHERE m.chat_id=?",
                (chat.chat_id,),
            )

    def insert_or_update_chat(chat) -> None:
        """
        Insert a new chat or update an existing one in the database.
        
        Args:
            chat: The chat object to save (must have chat_id, get_name(), folder_id, is_template)
        """
        with SQLiteConnection() as c:
            if c.cursor.execute(
                "SELECT id FROM chat WHERE id=?", (chat.chat_id,)
            ).fetchone():
                if chat.folder_id is None:
                    c.cursor.execute(
                        "UPDATE chat SET name=?, folder=NULL, is_template=? WHERE id=?",
                        (chat.get_name(), chat.is_template, chat.chat_id),
                    )
                else:
                    c.cursor.execute(
                        "UPDATE chat SET name=?, folder=?, is_template=? WHERE id=?",
                        (chat.get_name(), chat.folder_id, chat.is_template, chat.chat_id),
                    )
            else:
                if chat.folder_id is None:
                    c.cursor.execute(
                        "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
                        (chat.chat_id, chat.get_name()),
                    )
                else:
                    c.cursor.execute(
                        "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, ?, 0)",
                        (chat.chat_id, chat.get_name(), chat.folder_id),
                    )

    def delete_chat(chat) -> None:
        """
        Delete a chat and all its associated messages and attachments.
        
        Args:
            chat: The chat object to delete (must have chat_id)
        """
        with SQLiteConnection() as c:
            c.cursor.execute("DELETE FROM chat WHERE id=?", (chat.chat_id,))

            for message in c.cursor.execute(
                "SELECT id FROM message WHERE chat_id=?", (chat.chat_id,)
            ).fetchall():
                c.cursor.execute(
                    "DELETE FROM attachment WHERE message_id=?", (message[0],)
                )

            c.cursor.execute(
                "DELETE FROM message WHERE chat_id=?", (chat.chat_id,)
            )

    def factory_reset() -> None:
        """
        Delete all chats, folders, messages, and attachments from the database.
        
        This is a destructive operation that cannot be undone.
        """
        with SQLiteConnection() as c:
            c.cursor.execute("DELETE FROM chat_folder")
            c.cursor.execute("DELETE FROM chat")
            c.cursor.execute("DELETE FROM message")
            c.cursor.execute("DELETE FROM attachment")

    def duplicate_chat(old_chat_id:str, new_chat) -> None:
        """
        Create a duplicate of an existing chat with all its messages and attachments.
        
        Args:
            old_chat_id: The ID of the chat to duplicate
            new_chat: The new chat object to create (must have chat_id)
        """
        with SQLiteConnection() as c:
            Instance.insert_or_update_chat(new_chat)

            for message in c.cursor.execute(
                "SELECT id, role, model, date_time, content FROM message WHERE chat_id=?",
                (old_chat_id,),
            ).fetchall():
                new_message_id = generate_uuid()

                c.cursor.execute(
                    "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        new_message_id,
                        new_chat.chat_id,
                        message[1],
                        message[2],
                        message[3],
                        message[4],
                    ),
                )

                for attachment in c.cursor.execute(
                    "SELECT type, name, content FROM attachment WHERE message_id=?",
                    (message[0],),
                ).fetchall():
                    c.cursor.execute(
                        "INSERT INTO attachment (id, message_id, type, name, content) VALUES (?, ?, ?, ?, ?)",
                        (
                            generate_uuid(),
                            new_message_id,
                            attachment[0],
                            attachment[1],
                            attachment[2],
                        ),
                    )

    def import_chat(import_sql_path: str, chat_names: list, folder_id :str=None) -> list:
        with SQLiteConnection() as c:
            c.cursor.execute("ATTACH DATABASE ? AS import", (import_sql_path,))
            _chat_widgets = []

            # Check repeated chat.name
            for repeated_chat in c.cursor.execute(
                "SELECT import.chat.id, import.chat.name FROM import.chat JOIN chat dbchat ON import.chat.name = dbchat.name"
            ).fetchall():
                new_name = generate_numbered_name(repeated_chat[1], chat_names)

                c.cursor.execute(
                    "UPDATE import.chat SET name=? WHERE id=?",
                    (new_name, repeated_chat[0]),
                )

            # Check repeated chat.id
            for repeated_chat in c.cursor.execute(
                "SELECT import.chat.id FROM import.chat JOIN chat dbchat ON import.chat.id = dbchat.id"
            ).fetchall():
                new_id = generate_uuid()

                c.cursor.execute(
                    "UPDATE import.chat SET id=? WHERE id=?",
                    (new_id, repeated_chat[0]),
                )
                c.cursor.execute(
                    "UPDATE import.message SET chat_id=? WHERE chat_id=?",
                    (new_id, repeated_chat[0]),
                )

            # Check repeated message.id
            for repeated_message in c.cursor.execute(
                "SELECT import.message.id FROM import.message JOIN message dbmessage ON import.message.id = dbmessage.id"
            ).fetchall():
                new_id = generate_uuid()

                c.cursor.execute(
                    "UPDATE import.attachment SET message_id=? WHERE message_id=?",
                    (new_id, repeated_message[0]),
                )
                c.cursor.execute(
                    "UPDATE import.message SET id=? WHERE id=?",
                    (new_id, repeated_message[0]),
                )

            # Check repeated attachment.id
            for repeated_attachment in c.cursor.execute(
                "SELECT import.attachment.id FROM import.attachment JOIN attachment dbattachment ON import.attachment.id = dbattachment.id"
            ).fetchall():
                new_id = generate_uuid()

                c.cursor.execute(
                    "UPDATE import.attachment SET id=? WHERE id=?",
                    (new_id, repeated_attachment[0]),
                )

            # Import
            for chat in c.cursor.execute("SELECT * FROM import.chat").fetchall():
                c.cursor.execute("INSERT INTO chat (id, name, folder) VALUES (?, ?, ?)", (chat[0], chat[1], folder_id))

            c.cursor.execute(
                "INSERT INTO message SELECT * FROM import.message"
            )
            c.cursor.execute(
                "INSERT INTO attachment SELECT * FROM import.attachment"
            )

            new_chats = c.cursor.execute(
                "SELECT * FROM import.chat"
            ).fetchall()

        return new_chats

    ##############
    ## MESSAGES ##
    ##############

    def insert_or_update_message(message, force_chat_id: str = None) -> None:
        message_author = ["user", "assistant", "system"][message.mode]
        chat_element = message.get_ancestor(Widgets.chat.Chat)

        with SQLiteConnection() as c:
            if c.cursor.execute(
                "SELECT id FROM message WHERE id=?", (message.message_id,)
            ).fetchone():
                c.cursor.execute(
                    "UPDATE message SET chat_id=?, role=?, model=?, date_time=?, content=? WHERE id=?",
                    (
                        (
                            force_chat_id
                            if force_chat_id
                            else chat_element.chat_id
                        ),
                        message_author,
                        message.get_model() or "",
                        message.dt.strftime("%Y/%m/%d %H:%M:%S"),
                        message.get_content() or "",
                        message.message_id,
                    ),
                )
            else:
                c.cursor.execute(
                    "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        message.message_id,
                        (
                            force_chat_id
                            if force_chat_id
                            else chat_element.chat_id
                        ),
                        message_author,
                        message.get_model() or "",
                        message.dt.strftime("%Y/%m/%d %H:%M:%S"),
                        message.get_content() or "",
                    ),
                )

    def delete_message(message) -> None:
        with SQLiteConnection() as c:
            c.cursor.execute(
                "DELETE FROM message WHERE id=?", (message.message_id,)
            )
            c.cursor.execute(
                "DELETE FROM attachment WHERE message_id=?",
                (message.message_id,),
            )

    def insert_or_update_attachment(message, attachment) -> None:
        with SQLiteConnection() as c:
            if c.cursor.execute(
                "SELECT id FROM attachment WHERE id=?", (attachment.get_name(),)
            ).fetchone():
                c.cursor.execute(
                    "UPDATE attachment SET message_id=?, type=?, name=?, content=? WHERE id=?",
                    (
                        message.message_id,
                        attachment.file_type,
                        attachment.file_name,
                        attachment.file_content,
                        attachment.get_name()
                    )
                )
            else:
                c.cursor.execute(
                    "INSERT INTO attachment (id, message_id, type, name, content) VALUES (?, ?, ?, ?, ?)",
                    (
                        generate_uuid(),
                        message.message_id,
                        attachment.file_type,
                        attachment.file_name,
                        attachment.file_content,
                    ),
                )

    def delete_attachment(attachment) -> None:
        with SQLiteConnection() as c:
            c.cursor.execute(
                "DELETE FROM attachment WHERE id=?", (attachment.get_name(),)
            )

    ##############################
    ## PREFERENCES (DEPRECATED) ##
    ##############################

    def get_preferences() -> dict:
        with SQLiteConnection() as c:
            result = c.cursor.execute(
                "SELECT id, value, type FROM preferences"
            ).fetchall()

        preferences = {}
        type_map = {
            "<class 'int'>": int,
            "<class 'float'>": float,
            "<class 'bool'>": lambda x: x == "1",
        }

        for row in result:
            value = row[1]

            if row[2] in type_map:
                value = type_map[row[2]](value)

            preferences[row[0]] = value

        return preferences

    ###########
    ## MODEL ##
    ###########

    def insert_or_update_model_picture(model_id: str, picture_content: str) -> None:
        with SQLiteConnection() as c:
            if c.cursor.execute(
                "SELECT id FROM model WHERE id=?", (model_id,)
            ).fetchone():
                c.cursor.execute(
                    "UPDATE model SET picture=? WHERE id=?",
                    (picture_content, model_id),
                )

            else:
                c.cursor.execute(
                    "INSERT INTO model (id, picture) VALUES (?, ?)",
                    (model_id, picture_content),
                )

    def remove_model_preferences(model_id: str) -> None:
        with SQLiteConnection() as c:
            c.cursor.execute("DELETE FROM model_preferences WHERE id=?", (model_id,))

    def insert_or_update_model_picture(model_id: str, picture_content: str or None) -> None:
        with SQLiteConnection() as c:
            if c.cursor.execute("SELECT id FROM model_preferences WHERE id=?", (model_id,)).fetchone():
                c.cursor.execute("UPDATE model_preferences SET picture=? WHERE id=?", (picture_content, model_id))
            else:
                c.cursor.execute("INSERT INTO model_preferences (id, picture) VALUES (?, ?)", (model_id, picture_content))

    def insert_or_update_model_voice(model_id: str, voice_name: str or None) -> None:
        with SQLiteConnection() as c:
            if c.cursor.execute("SELECT id FROM model_preferences WHERE id=?", (model_id,)).fetchone():
                c.cursor.execute("UPDATE model_preferences SET voice=? WHERE id=?", (voice_name, model_id))
            else:
                c.cursor.execute("INSERT INTO model_preferences (id, voice) VALUES (?, ?)", (model_id, voice_name))

    def get_model_preferences(model_id: str) -> dict:
        with SQLiteConnection() as c:
            row = c.cursor.execute("SELECT picture, voice FROM model_preferences WHERE id=?", (model_id,)).fetchone()
            if row:
                return {
                    'picture': row[0],
                    'voice': row[1]
                }
            else:
                return {
                    'picture': None,
                    'voice': None
                }


    ###############
    ## Instances ##
    ###############

    def get_instances_DEPRECATED() -> list:
        columns = [
            "id",
            "name",
            "type",
            "url",
            "max_tokens",
            "api",
            "temperature",
            "seed",
            "overrides",
            "model_directory",
            "default_model",
            "title_model",
            "pinned",
        ]

        with SQLiteConnection() as c:
            result = c.cursor.execute(
                "SELECT {} FROM instances".format(", ".join(columns))
            ).fetchall()

        instances = []

        for row in result:
            instances.append({})

            for i, column in enumerate(columns):
                value = row[i]

                if column == "overrides":
                    try:
                        value = json.loads(value)
                    except Exception:
                        value = {}
                elif column == "pinned":
                    value = value == 1

                instances[-1][column] = value

        return instances

    def get_instances() -> list:
        with SQLiteConnection() as c:
            result = c.cursor.execute("SELECT * FROM instance").fetchall()
            instances = []
            for row in result:
                instances.append({
                    'id': row[0],
                    'pinned': row[1] == 1,
                    'type': row[2],
                    'properties': json.loads(row[3])
                })
            return instances
        return []

    def insert_or_update_instance(instance_id:str, pinned:bool, instance_type:str, properties:dict):
        with SQLiteConnection() as c:
            if c.cursor.execute(
                "SELECT id FROM instance WHERE id=?", (instance_id,)
            ).fetchone():
                c.cursor.execute(
                    f"UPDATE instance SET properties=? WHERE id=?",
                    (json.dumps(properties), instance_id)
                )
            else:
                c.cursor.execute(
                    f"INSERT INTO instance (id, pinned, type, properties) VALUES (?, ?, ?, ?)",
                    (instance_id, 1 if pinned else 0, instance_type, json.dumps(properties))
                )

    def delete_instance(instance_id: str):
        with SQLiteConnection() as c:
            c.cursor.execute(
                "DELETE FROM instance WHERE id=?", (instance_id,)
            )

    ################################
    ## ONLINE INSTANCE MODEL LIST ##
    ################################

    def get_online_instance_model_list(instance_id:str) -> list:
        with SQLiteConnection() as c:
            result = c.cursor.execute(
                "SELECT list FROM online_instance_model_list WHERE id=?",
                (instance_id,)
            ).fetchone()

            if result:
                return json.loads(result[0])
        return []

    def append_online_instance_model_list(instance_id:str, model_name:str) -> None:
        with SQLiteConnection() as c:
            result = c.cursor.execute(
                "SELECT list FROM online_instance_model_list WHERE id=?",
                (instance_id,)
            ).fetchone()

            if result:
                model_list = json.loads(result[0])
                model_list.append(model_name)
                c.cursor.execute(
                    f"UPDATE online_instance_model_list SET list=? WHERE id=?",
                    (json.dumps(model_list), instance_id)
                )
            else:
                c.cursor.execute(
                    "INSERT INTO online_instance_model_list (id, list) VALUES (?, ?)",
                    (instance_id, json.dumps([model_name]))
                )

    def remove_online_instance_model_list(instance_id:str, model_name:str) -> None:
        with SQLiteConnection() as c:
            result = c.cursor.execute(
                "SELECT list FROM online_instance_model_list WHERE id=?",
                (instance_id,)
            ).fetchone()

            if result:
                model_list = json.loads(result[0])
                if model_name in model_list:
                    model_list.remove(model_name)
                c.cursor.execute(
                    f"UPDATE online_instance_model_list SET list=? WHERE id=?",
                    (json.dumps(model_list), instance_id)
                )

    ##################
    ## CHAT FOLDERS ##
    ##################

    def get_chat_folders(parent_id:str=None):
        with SQLiteConnection() as c:
            if parent_id is None:
                folders = c.cursor.execute(
                    "SELECT id, name, color, parent FROM chat_folder WHERE parent IS NULL"
                ).fetchall()
            else:
                folders = c.cursor.execute(
                    "SELECT id, name, color, parent FROM chat_folder WHERE parent=?",
                    (parent_id,)
                ).fetchall()

        return folders

    def move_folder_to_folder(folder_id:str, parent_id:str):
        with SQLiteConnection() as c:
            if parent_id is None:
                c.cursor.execute(
                    "UPDATE chat_folder SET parent=NULL WHERE id=?",
                    (folder_id,)
                )
            else:
                c.cursor.execute(
                    "UPDATE chat_folder SET parent=? WHERE id=?",
                    (parent_id, folder_id)
                )

    def insert_or_update_folder(folder_id:str, folder_name:str, folder_color:str, parent:str):
        if folder_id is None:
            return # Can't modify root
        with SQLiteConnection() as c:
            if c.cursor.execute(
                "SELECT id FROM chat_folder WHERE id=?", (folder_id,)
            ).fetchone():
                c.cursor.execute(
                    f"UPDATE chat_folder SET name=?, color=?, parent=? WHERE id=?",
                    (folder_name, folder_color, parent, folder_id)
                )
            else:
                c.cursor.execute(
                    f"INSERT INTO chat_folder (id, name, color, parent) VALUES (?, ?, ?, ?)",
                    (folder_id, folder_name, folder_color, parent)
                )

    def remove_folder(folder_id:str):
        if folder_id is None:
            return # Can't modify root
        result = []
        with SQLiteConnection() as c:
            c.cursor.execute(
                "DELETE FROM chat_folder WHERE id=?", (folder_id,)
            )
            result = c.cursor.execute(
                "SELECT id FROM chat WHERE folder=?", (folder_id,)
            ).fetchall()

        for row in result:
            class tempchat:
                chat_id=None
            tempchat.chat_id=row[0]
            Instance.delete_chat(tempchat)

        result = []
        with SQLiteConnection() as c:
            result = c.cursor.execute(
                "SELECT id FROM chat_folder WHERE parent=?", (folder_id,)
            ).fetchall()

        for row in result:
            Instance.remove_folder(row[0])

    # Prompt Library Methods
    
    def save_prompt(name: str, content: str, category: str = None) -> str:
        """
        Save a prompt to the library.
        
        Args:
            name: The name of the prompt
            content: The prompt content/text
            category: Optional category for organization
            
        Returns:
            The ID of the saved prompt
        """
        prompt_id = str(uuid.uuid4())
        created_at = datetime.datetime.now()
        
        with SQLiteConnection() as c:
            c.cursor.execute(
                "INSERT INTO prompt (id, name, content, category, created_at) VALUES (?, ?, ?, ?, ?)",
                (prompt_id, name, content, category, created_at)
            )
        
        return prompt_id
    
    def get_prompts(category: str = None):
        """
        Get prompts from the library, optionally filtered by category.
        
        Args:
            category: Optional category to filter by. If None, returns all prompts.
            
        Returns:
            List of prompt dictionaries with id, name, content, category, created_at
        """
        with SQLiteConnection() as c:
            if category:
                result = c.cursor.execute(
                    "SELECT id, name, content, category, created_at FROM prompt WHERE category=? ORDER BY created_at DESC",
                    (category,)
                ).fetchall()
            else:
                result = c.cursor.execute(
                    "SELECT id, name, content, category, created_at FROM prompt ORDER BY created_at DESC"
                ).fetchall()
        
        prompts = []
        for row in result:
            prompts.append({
                'id': row[0],
                'name': row[1],
                'content': row[2],
                'category': row[3],
                'created_at': row[4]
            })
        
        return prompts
    
    def get_prompt_categories():
        """
        Get all unique categories from the prompt library.
        
        Returns:
            List of category names (excluding None)
        """
        with SQLiteConnection() as c:
            result = c.cursor.execute(
                "SELECT DISTINCT category FROM prompt WHERE category IS NOT NULL ORDER BY category"
            ).fetchall()
        
        return [row[0] for row in result]
    
    def delete_prompt(prompt_id: str) -> bool:
        """
        Delete a prompt from the library.
        
        Args:
            prompt_id: The ID of the prompt to delete
            
        Returns:
            True if deleted successfully, False otherwise
        """
        with SQLiteConnection() as c:
            c.cursor.execute("DELETE FROM prompt WHERE id=?", (prompt_id,))
            return c.cursor.rowcount > 0
    
    def update_prompt(prompt_id: str, name: str = None, content: str = None, category: str = None) -> bool:
        """
        Update a prompt in the library.
        
        Args:
            prompt_id: The ID of the prompt to update
            name: New name (optional)
            content: New content (optional)
            category: New category (optional)
            
        Returns:
            True if updated successfully, False otherwise
        """
        updates = []
        params = []
        
        if name is not None:
            updates.append("name=?")
            params.append(name)
        if content is not None:
            updates.append("content=?")
            params.append(content)
        if category is not None:
            updates.append("category=?")
            params.append(category)
        
        if not updates:
            return False
        
        params.append(prompt_id)
        query = f"UPDATE prompt SET {', '.join(updates)} WHERE id=?"
        
        with SQLiteConnection() as c:
            c.cursor.execute(query, tuple(params))
            return c.cursor.rowcount > 0
