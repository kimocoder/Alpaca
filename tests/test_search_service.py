"""
Unit tests for the SearchService class.
Tests basic search functionality and preview generation.
"""

import unittest
import tempfile
import os
import sqlite3
from datetime import datetime
import sys

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

from services.search import SearchService, SearchResult


class TestSearchService(unittest.TestCase):
    """Test cases for SearchService functionality."""
    
    def setUp(self):
        """Set up a temporary database for testing."""
        # Create a temporary database
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        # Create the database schema
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create tables
        cursor.execute("""
            CREATE TABLE chat (
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT,
                is_template INTEGER NOT NULL DEFAULT 0
            )
        """)
        
        cursor.execute("""
            CREATE TABLE message (
                id TEXT NOT NULL PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT,
                date_time DATETIME NOT NULL,
                content TEXT NOT NULL
            )
        """)
        
        # Insert test data
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("chat1", "Test Chat 1")
        )
        cursor.execute(
            "INSERT INTO chat (id, name, folder, is_template) VALUES (?, ?, NULL, 0)",
            ("chat2", "Test Chat 2")
        )
        
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg1", "chat1", "user", "llama2", "2024/01/15 10:30:00", "Hello, how are you today?")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg2", "chat1", "assistant", "llama2", "2024/01/15 10:30:15", "I'm doing well, thank you for asking!")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg3", "chat2", "user", "llama2", "2024/01/16 14:20:00", "What is Python programming?")
        )
        cursor.execute(
            "INSERT INTO message (id, chat_id, role, model, date_time, content) VALUES (?, ?, ?, ?, ?, ?)",
            ("msg4", "chat2", "assistant", "llama2", "2024/01/16 14:20:30", "Python is a high-level programming language known for its simplicity.")
        )
        
        conn.commit()
        conn.close()
        
        # Create search service with custom db path
        self.search_service = SearchService(db_path=self.db_path)
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_search_finds_matching_messages(self):
        """Test that search finds messages containing the query."""
        results = self.search_service.search_all_chats("Python")
        
        self.assertEqual(len(results), 2)  # Should find 2 messages with "Python"
        self.assertIsInstance(results[0], SearchResult)
        self.assertIn("Python", results[0].message_preview)
    
    def test_search_returns_empty_for_no_matches(self):
        """Test that search returns empty list when no matches found."""
        results = self.search_service.search_all_chats("nonexistent query")
        
        self.assertEqual(len(results), 0)
    
    def test_search_with_empty_query(self):
        """Test that search handles empty query gracefully."""
        results = self.search_service.search_all_chats("")
        
        self.assertEqual(len(results), 0)
    
    def test_search_result_contains_required_fields(self):
        """Test that search results contain all required fields."""
        results = self.search_service.search_all_chats("Hello")
        
        self.assertGreater(len(results), 0)
        result = results[0]
        
        self.assertIsNotNone(result.chat_id)
        self.assertIsNotNone(result.chat_name)
        self.assertIsNotNone(result.message_id)
        self.assertIsNotNone(result.message_preview)
        self.assertIsInstance(result.timestamp, datetime)
        self.assertIsInstance(result.relevance_score, float)
        self.assertGreaterEqual(result.relevance_score, 0.0)
        self.assertLessEqual(result.relevance_score, 1.0)
    
    def test_search_with_date_from_filtering(self):
        """Test that date_from filtering works correctly."""
        date_from = datetime(2024, 1, 16, 0, 0, 0)
        results = self.search_service.search_all_chats("Python", date_from=date_from)
        
        # Should only find messages from Jan 16 onwards
        self.assertEqual(len(results), 2)
        for result in results:
            self.assertGreaterEqual(result.timestamp, date_from)
    
    def test_search_with_date_to_filtering(self):
        """Test that date_to filtering works correctly."""
        date_to = datetime(2024, 1, 15, 23, 59, 59)
        results = self.search_service.search_all_chats("how", date_to=date_to)
        
        # Should only find messages up to Jan 15
        self.assertEqual(len(results), 1)
        for result in results:
            self.assertLessEqual(result.timestamp, date_to)
    
    def test_search_with_date_range_filtering(self):
        """Test that date range filtering (both date_from and date_to) works correctly."""
        date_from = datetime(2024, 1, 15, 0, 0, 0)
        date_to = datetime(2024, 1, 15, 23, 59, 59)
        results = self.search_service.search_all_chats("you", date_from=date_from, date_to=date_to)
        
        # Should only find messages within Jan 15
        self.assertGreater(len(results), 0)
        for result in results:
            self.assertGreaterEqual(result.timestamp, date_from)
            self.assertLessEqual(result.timestamp, date_to)
    
    def test_search_with_no_results_in_date_range(self):
        """Test that search returns empty list when no messages match date range."""
        date_from = datetime(2024, 1, 20, 0, 0, 0)
        date_to = datetime(2024, 1, 25, 0, 0, 0)
        results = self.search_service.search_all_chats("Python", date_from=date_from, date_to=date_to)
        
        # Should find no messages in this date range
        self.assertEqual(len(results), 0)
    
    def test_preview_generation_with_message_id(self):
        """Test preview generation using message_id."""
        preview = self.search_service.get_search_result_preview(
            message_id="msg1",
            query="Hello",
            context_chars=50
        )
        
        self.assertIn("Hello", preview)
        self.assertIsInstance(preview, str)
    
    def test_preview_generation_with_content(self):
        """Test preview generation using message content directly."""
        content = "This is a test message with some important information in the middle."
        preview = self.search_service.get_search_result_preview(
            message_content=content,
            query="important",
            context_chars=20
        )
        
        self.assertIn("important", preview)
        self.assertLess(len(preview), len(content))
    
    def test_relevance_score_calculation(self):
        """Test that relevance scores are calculated."""
        results = self.search_service.search_all_chats("Python")
        
        for result in results:
            self.assertGreater(result.relevance_score, 0.0)
            self.assertLessEqual(result.relevance_score, 1.0)


if __name__ == '__main__':
    unittest.main()
