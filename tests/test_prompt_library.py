"""
Unit tests for prompt library functionality.
Tests prompt CRUD operations and persistence.
"""

import unittest
import tempfile
import os
import sqlite3
import datetime
import uuid


def generate_uuid() -> str:
    """Generate a unique ID."""
    return f"{datetime.datetime.today().strftime('%Y%m%d%H%M%S%f')}{uuid.uuid4().hex}"


class SQLiteConnection:
    """Context manager for SQLite connections."""
    
    def __init__(self, db_path):
        self.sql_path = db_path
        self.sqlite_con = None
        self.cursor = None
    
    def __enter__(self):
        self.sqlite_con = sqlite3.connect(self.sql_path)
        self.cursor = self.sqlite_con.cursor()
        return self
    
    def __exit__(self, exception_type, exception_val, traceback):
        if self.sqlite_con.in_transaction:
            self.sqlite_con.commit()
        self.sqlite_con.close()


class PromptOperations:
    """Prompt library database operations."""
    
    @staticmethod
    def save_prompt(db_path, name: str, content: str, category: str = None) -> str:
        """Save a prompt to the library and return its ID."""
        prompt_id = generate_uuid()
        with SQLiteConnection(db_path) as c:
            c.cursor.execute(
                "INSERT INTO prompt (id, name, content, category, created_at) VALUES (?, ?, ?, ?, ?)",
                (prompt_id, name, content, category, datetime.datetime.now().strftime("%Y/%m/%d %H:%M:%S"))
            )
        return prompt_id
    
    @staticmethod
    def get_prompts(db_path, category: str = None) -> list:
        """Get prompts, optionally filtered by category."""
        with SQLiteConnection(db_path) as c:
            if category is None:
                prompts = c.cursor.execute(
                    "SELECT id, name, content, category, created_at FROM prompt ORDER BY created_at DESC"
                ).fetchall()
            else:
                prompts = c.cursor.execute(
                    "SELECT id, name, content, category, created_at FROM prompt WHERE category=? ORDER BY created_at DESC",
                    (category,)
                ).fetchall()
        return prompts
    
    @staticmethod
    def get_prompt_by_id(db_path, prompt_id: str) -> dict:
        """Get a specific prompt by ID."""
        with SQLiteConnection(db_path) as c:
            row = c.cursor.execute(
                "SELECT id, name, content, category, created_at FROM prompt WHERE id=?",
                (prompt_id,)
            ).fetchone()
            if row:
                return {
                    'id': row[0],
                    'name': row[1],
                    'content': row[2],
                    'category': row[3],
                    'created_at': row[4]
                }
        return None
    
    @staticmethod
    def update_prompt(db_path, prompt_id: str, name: str = None, content: str = None, category: str = None) -> bool:
        """Update an existing prompt."""
        with SQLiteConnection(db_path) as c:
            existing = c.cursor.execute(
                "SELECT id FROM prompt WHERE id=?", (prompt_id,)
            ).fetchone()
            
            if not existing:
                return False
            
            if name is not None:
                c.cursor.execute(
                    "UPDATE prompt SET name=? WHERE id=?",
                    (name, prompt_id)
                )
            if content is not None:
                c.cursor.execute(
                    "UPDATE prompt SET content=? WHERE id=?",
                    (content, prompt_id)
                )
            if category is not None:
                c.cursor.execute(
                    "UPDATE prompt SET category=? WHERE id=?",
                    (category, prompt_id)
                )
        return True
    
    @staticmethod
    def delete_prompt(db_path, prompt_id: str) -> bool:
        """Delete a prompt by ID."""
        with SQLiteConnection(db_path) as c:
            result = c.cursor.execute(
                "SELECT id FROM prompt WHERE id=?", (prompt_id,)
            ).fetchone()
            
            if not result:
                return False
            
            c.cursor.execute(
                "DELETE FROM prompt WHERE id=?", (prompt_id,)
            )
        return True
    
    @staticmethod
    def get_prompt_categories(db_path) -> list:
        """Get all unique prompt categories."""
        with SQLiteConnection(db_path) as c:
            categories = c.cursor.execute(
                "SELECT DISTINCT category FROM prompt WHERE category IS NOT NULL ORDER BY category"
            ).fetchall()
        return [cat[0] for cat in categories]


class TestPromptLibrary(unittest.TestCase):
    """Test cases for prompt library functionality."""
    
    def setUp(self):
        """Set up a temporary database for testing."""
        # Create a temporary database
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        
        # Create test data
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Create prompt table
        cursor.execute("""
            CREATE TABLE prompt (
                id TEXT NOT NULL PRIMARY KEY,
                name TEXT NOT NULL,
                content TEXT NOT NULL,
                category TEXT,
                created_at DATETIME NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_save_prompt_without_category(self):
        """Test saving a prompt without a category."""
        prompt_id = PromptOperations.save_prompt(
            self.db_path,
            "Test Prompt",
            "This is a test prompt content"
        )
        self.assertIsNotNone(prompt_id)
        
        # Verify it was saved
        prompt = PromptOperations.get_prompt_by_id(self.db_path, prompt_id)
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt['name'], "Test Prompt")
        self.assertEqual(prompt['content'], "This is a test prompt content")
        self.assertIsNone(prompt['category'])
    
    def test_save_prompt_with_category(self):
        """Test saving a prompt with a category."""
        prompt_id = PromptOperations.save_prompt(
            self.db_path,
            "Coding Prompt",
            "Write a Python function that...",
            "Programming"
        )
        self.assertIsNotNone(prompt_id)
        
        # Verify it was saved with category
        prompt = PromptOperations.get_prompt_by_id(self.db_path, prompt_id)
        self.assertIsNotNone(prompt)
        self.assertEqual(prompt['name'], "Coding Prompt")
        self.assertEqual(prompt['content'], "Write a Python function that...")
        self.assertEqual(prompt['category'], "Programming")
    
    def test_get_all_prompts(self):
        """Test retrieving all prompts."""
        # Save multiple prompts
        PromptOperations.save_prompt(self.db_path, "Prompt 1", "Content 1")
        PromptOperations.save_prompt(self.db_path, "Prompt 2", "Content 2", "Category A")
        PromptOperations.save_prompt(self.db_path, "Prompt 3", "Content 3", "Category B")
        
        prompts = PromptOperations.get_prompts(self.db_path)
        self.assertEqual(len(prompts), 3)
    
    def test_get_prompts_by_category(self):
        """Test retrieving prompts filtered by category."""
        # Save prompts with different categories
        PromptOperations.save_prompt(self.db_path, "Prompt 1", "Content 1", "Programming")
        PromptOperations.save_prompt(self.db_path, "Prompt 2", "Content 2", "Writing")
        PromptOperations.save_prompt(self.db_path, "Prompt 3", "Content 3", "Programming")
        
        programming_prompts = PromptOperations.get_prompts(self.db_path, "Programming")
        self.assertEqual(len(programming_prompts), 2)
        
        writing_prompts = PromptOperations.get_prompts(self.db_path, "Writing")
        self.assertEqual(len(writing_prompts), 1)
    
    def test_update_prompt_name(self):
        """Test updating a prompt's name."""
        prompt_id = PromptOperations.save_prompt(
            self.db_path,
            "Original Name",
            "Content"
        )
        
        result = PromptOperations.update_prompt(self.db_path, prompt_id, name="Updated Name")
        self.assertTrue(result)
        
        prompt = PromptOperations.get_prompt_by_id(self.db_path, prompt_id)
        self.assertEqual(prompt['name'], "Updated Name")
        self.assertEqual(prompt['content'], "Content")
    
    def test_update_prompt_content(self):
        """Test updating a prompt's content."""
        prompt_id = PromptOperations.save_prompt(
            self.db_path,
            "Name",
            "Original Content"
        )
        
        result = PromptOperations.update_prompt(self.db_path, prompt_id, content="Updated Content")
        self.assertTrue(result)
        
        prompt = PromptOperations.get_prompt_by_id(self.db_path, prompt_id)
        self.assertEqual(prompt['name'], "Name")
        self.assertEqual(prompt['content'], "Updated Content")
    
    def test_update_prompt_category(self):
        """Test updating a prompt's category."""
        prompt_id = PromptOperations.save_prompt(
            self.db_path,
            "Name",
            "Content",
            "Old Category"
        )
        
        result = PromptOperations.update_prompt(self.db_path, prompt_id, category="New Category")
        self.assertTrue(result)
        
        prompt = PromptOperations.get_prompt_by_id(self.db_path, prompt_id)
        self.assertEqual(prompt['category'], "New Category")
    
    def test_update_nonexistent_prompt(self):
        """Test updating a prompt that doesn't exist."""
        result = PromptOperations.update_prompt(self.db_path, "nonexistent_id", name="New Name")
        self.assertFalse(result)
    
    def test_delete_prompt(self):
        """Test deleting a prompt."""
        prompt_id = PromptOperations.save_prompt(
            self.db_path,
            "To Delete",
            "Content"
        )
        
        # Verify it exists
        prompt = PromptOperations.get_prompt_by_id(self.db_path, prompt_id)
        self.assertIsNotNone(prompt)
        
        # Delete it
        result = PromptOperations.delete_prompt(self.db_path, prompt_id)
        self.assertTrue(result)
        
        # Verify it's gone
        prompt = PromptOperations.get_prompt_by_id(self.db_path, prompt_id)
        self.assertIsNone(prompt)
    
    def test_delete_nonexistent_prompt(self):
        """Test deleting a prompt that doesn't exist."""
        result = PromptOperations.delete_prompt(self.db_path, "nonexistent_id")
        self.assertFalse(result)
    
    def test_get_prompt_categories(self):
        """Test retrieving all unique categories."""
        # Save prompts with various categories
        PromptOperations.save_prompt(self.db_path, "P1", "C1", "Programming")
        PromptOperations.save_prompt(self.db_path, "P2", "C2", "Writing")
        PromptOperations.save_prompt(self.db_path, "P3", "C3", "Programming")
        PromptOperations.save_prompt(self.db_path, "P4", "C4", None)
        PromptOperations.save_prompt(self.db_path, "P5", "C5", "Design")
        
        categories = PromptOperations.get_prompt_categories(self.db_path)
        self.assertEqual(len(categories), 3)
        self.assertIn("Programming", categories)
        self.assertIn("Writing", categories)
        self.assertIn("Design", categories)
    
    def test_prompt_persistence(self):
        """Test that prompts persist across database connections."""
        prompt_id = PromptOperations.save_prompt(
            self.db_path,
            "Persistent Prompt",
            "This should persist"
        )
        
        # Close and reopen connection
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        result = cursor.execute(
            "SELECT id, name, content FROM prompt WHERE id=?", (prompt_id,)
        ).fetchone()
        conn.close()
        
        self.assertIsNotNone(result)
        self.assertEqual(result[1], "Persistent Prompt")
        self.assertEqual(result[2], "This should persist")
    
    def test_prompt_ordering(self):
        """Test that prompts are ordered by creation date (newest first)."""
        import time
        
        # Save prompts with delays to ensure different timestamps
        id1 = PromptOperations.save_prompt(self.db_path, "First", "Content 1")
        time.sleep(1.1)  # Sleep for more than 1 second to ensure different timestamps
        id2 = PromptOperations.save_prompt(self.db_path, "Second", "Content 2")
        time.sleep(1.1)
        id3 = PromptOperations.save_prompt(self.db_path, "Third", "Content 3")
        
        prompts = PromptOperations.get_prompts(self.db_path)
        
        # Should be in reverse order (newest first)
        # Check by name since IDs are generated with microsecond precision
        self.assertEqual(prompts[0][1], "Third")
        self.assertEqual(prompts[1][1], "Second")
        self.assertEqual(prompts[2][1], "First")


if __name__ == '__main__':
    unittest.main()
