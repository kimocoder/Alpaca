"""
Unit tests for model pinning functionality.
Tests pin/unpin operations, pin order sorting, and database persistence.
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


class ModelPinningSQL:
    """SQL operations for model pinning."""
    
    @staticmethod
    def pin_model(db_path, model_name: str, instance_id: str) -> str:
        """Pin a model and return the pin ID."""
        pin_id = generate_uuid()
        with SQLiteConnection(db_path) as c:
            # Check if already pinned
            existing = c.cursor.execute(
                "SELECT id FROM model_pin WHERE model_name=? AND instance_id=?",
                (model_name, instance_id)
            ).fetchone()
            
            if existing:
                return existing[0]
            
            # Get the next pin order
            max_order = c.cursor.execute(
                "SELECT MAX(pin_order) FROM model_pin WHERE instance_id=?",
                (instance_id,)
            ).fetchone()[0]
            
            next_order = (max_order or 0) + 1
            
            c.cursor.execute(
                "INSERT INTO model_pin (id, model_name, instance_id, pin_order) VALUES (?, ?, ?, ?)",
                (pin_id, model_name, instance_id, next_order)
            )
        return pin_id
    
    @staticmethod
    def unpin_model(db_path, model_name: str, instance_id: str) -> bool:
        """Unpin a model."""
        with SQLiteConnection(db_path) as c:
            result = c.cursor.execute(
                "SELECT id, pin_order FROM model_pin WHERE model_name=? AND instance_id=?",
                (model_name, instance_id)
            ).fetchone()
            
            if not result:
                return False
            
            pin_order = result[1]
            
            c.cursor.execute(
                "DELETE FROM model_pin WHERE model_name=? AND instance_id=?",
                (model_name, instance_id)
            )
            
            # Reorder remaining pins
            c.cursor.execute(
                "UPDATE model_pin SET pin_order = pin_order - 1 WHERE instance_id=? AND pin_order > ?",
                (instance_id, pin_order)
            )
        return True
    
    @staticmethod
    def is_model_pinned(db_path, model_name: str, instance_id: str) -> bool:
        """Check if a model is pinned."""
        with SQLiteConnection(db_path) as c:
            result = c.cursor.execute(
                "SELECT id FROM model_pin WHERE model_name=? AND instance_id=?",
                (model_name, instance_id)
            ).fetchone()
        return result is not None
    
    @staticmethod
    def get_pinned_models(db_path, instance_id: str) -> list:
        """Get all pinned models for an instance, ordered by pin order."""
        with SQLiteConnection(db_path) as c:
            pins = c.cursor.execute(
                "SELECT id, model_name, pin_order FROM model_pin WHERE instance_id=? ORDER BY pin_order",
                (instance_id,)
            ).fetchall()
        return pins
    
    @staticmethod
    def update_model_pin_order(db_path, model_name: str, instance_id: str, new_order: int) -> bool:
        """Update the pin order of a model."""
        with SQLiteConnection(db_path) as c:
            result = c.cursor.execute(
                "SELECT id, pin_order FROM model_pin WHERE model_name=? AND instance_id=?",
                (model_name, instance_id)
            ).fetchone()
            
            if not result:
                return False
            
            old_order = result[1]
            
            if old_order == new_order:
                return True
            
            # Shift other pins
            if new_order < old_order:
                c.cursor.execute(
                    "UPDATE model_pin SET pin_order = pin_order + 1 WHERE instance_id=? AND pin_order >= ? AND pin_order < ?",
                    (instance_id, new_order, old_order)
                )
            else:
                c.cursor.execute(
                    "UPDATE model_pin SET pin_order = pin_order - 1 WHERE instance_id=? AND pin_order > ? AND pin_order <= ?",
                    (instance_id, old_order, new_order)
                )
            
            # Update the target pin
            c.cursor.execute(
                "UPDATE model_pin SET pin_order=? WHERE model_name=? AND instance_id=?",
                (new_order, model_name, instance_id)
            )
        return True


class TestModelPinning(unittest.TestCase):
    """Test cases for model pinning functionality."""
    
    def setUp(self):
        """Set up a temporary database for testing."""
        # Create a temporary database
        self.temp_db = tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
        self.SQL = ModelPinningSQL
        
        # Initialize database with required tables
        with SQLiteConnection(self.db_path) as c:
            c.cursor.execute("""
                CREATE TABLE IF NOT EXISTS model_pin (
                    id TEXT NOT NULL PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    instance_id TEXT NOT NULL,
                    pin_order INTEGER NOT NULL
                )
            """)
            
            c.cursor.execute("""
                CREATE TABLE IF NOT EXISTS instance (
                    id TEXT NOT NULL PRIMARY KEY,
                    pinned INTEGER NOT NULL,
                    type TEXT NOT NULL,
                    properties TEXT NOT NULL
                )
            """)
            
            # Insert test instance
            c.cursor.execute(
                "INSERT INTO instance (id, pinned, type, properties) VALUES (?, ?, ?, ?)",
                ("test_instance", 0, "ollama", "{}")
            )
    
    def tearDown(self):
        """Clean up temporary database."""
        if os.path.exists(self.db_path):
            os.remove(self.db_path)
    
    def test_pin_model_creates_pin(self):
        """Test that pinning a model creates a pin record."""
        pin_id = self.SQL.pin_model(self.db_path, "llama2:latest", "test_instance")
        
        self.assertIsNotNone(pin_id)
        self.assertTrue(self.SQL.is_model_pinned(self.db_path, "llama2:latest", "test_instance"))
    
    def test_unpin_model_removes_pin(self):
        """Test that unpinning a model removes the pin record."""
        self.SQL.pin_model(self.db_path, "llama2:latest", "test_instance")
        result = self.SQL.unpin_model(self.db_path, "llama2:latest", "test_instance")
        
        self.assertTrue(result)
        self.assertFalse(self.SQL.is_model_pinned(self.db_path, "llama2:latest", "test_instance"))
    
    def test_pin_order_increments(self):
        """Test that pin order increments for each new pin."""
        self.SQL.pin_model(self.db_path, "model1:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model2:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model3:latest", "test_instance")
        
        pins = self.SQL.get_pinned_models(self.db_path, "test_instance")
        
        self.assertEqual(len(pins), 3)
        # Check that pin orders are sequential
        orders = [pin[2] for pin in pins]
        self.assertEqual(orders, [1, 2, 3])
    
    def test_unpin_reorders_remaining_pins(self):
        """Test that unpinning a model reorders remaining pins."""
        self.SQL.pin_model(self.db_path, "model1:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model2:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model3:latest", "test_instance")
        
        # Unpin the middle model
        self.SQL.unpin_model(self.db_path, "model2:latest", "test_instance")
        
        pins = self.SQL.get_pinned_models(self.db_path, "test_instance")
        
        self.assertEqual(len(pins), 2)
        # Check that remaining pins are reordered
        orders = [pin[2] for pin in pins]
        self.assertEqual(orders, [1, 2])
    
    def test_get_pinned_models_returns_ordered_list(self):
        """Test that get_pinned_models returns models in pin order."""
        self.SQL.pin_model(self.db_path, "model3:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model1:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model2:latest", "test_instance")
        
        pins = self.SQL.get_pinned_models(self.db_path, "test_instance")
        
        # Should be ordered by pin_order
        model_names = [pin[1] for pin in pins]
        self.assertEqual(model_names, ["model3:latest", "model1:latest", "model2:latest"])
    
    def test_pin_already_pinned_model_returns_existing_id(self):
        """Test that pinning an already pinned model returns existing pin ID."""
        pin_id1 = self.SQL.pin_model(self.db_path, "llama2:latest", "test_instance")
        pin_id2 = self.SQL.pin_model(self.db_path, "llama2:latest", "test_instance")
        
        self.assertEqual(pin_id1, pin_id2)
        
        # Should still only have one pin
        pins = self.SQL.get_pinned_models(self.db_path, "test_instance")
        self.assertEqual(len(pins), 1)
    
    def test_unpin_nonexistent_model_returns_false(self):
        """Test that unpinning a non-pinned model returns False."""
        result = self.SQL.unpin_model(self.db_path, "nonexistent:model", "test_instance")
        
        self.assertFalse(result)
    
    def test_is_model_pinned_returns_correct_status(self):
        """Test that is_model_pinned correctly identifies pin status."""
        self.assertFalse(self.SQL.is_model_pinned(self.db_path, "llama2:latest", "test_instance"))
        
        self.SQL.pin_model(self.db_path, "llama2:latest", "test_instance")
        self.assertTrue(self.SQL.is_model_pinned(self.db_path, "llama2:latest", "test_instance"))
        
        self.SQL.unpin_model(self.db_path, "llama2:latest", "test_instance")
        self.assertFalse(self.SQL.is_model_pinned(self.db_path, "llama2:latest", "test_instance"))
    
    def test_pins_are_instance_specific(self):
        """Test that pins are specific to each instance."""
        # Create another instance
        with SQLiteConnection(self.db_path) as c:
            c.cursor.execute(
                "INSERT INTO instance (id, pinned, type, properties) VALUES (?, ?, ?, ?)",
                ("test_instance2", 0, "ollama", "{}")
            )
        
        self.SQL.pin_model(self.db_path, "llama2:latest", "test_instance")
        
        self.assertTrue(self.SQL.is_model_pinned(self.db_path, "llama2:latest", "test_instance"))
        self.assertFalse(self.SQL.is_model_pinned(self.db_path, "llama2:latest", "test_instance2"))
    
    def test_update_model_pin_order(self):
        """Test that updating pin order works correctly."""
        self.SQL.pin_model(self.db_path, "model1:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model2:latest", "test_instance")
        self.SQL.pin_model(self.db_path, "model3:latest", "test_instance")
        
        # Move model3 to position 1
        result = self.SQL.update_model_pin_order(self.db_path, "model3:latest", "test_instance", 1)
        
        self.assertTrue(result)
        
        pins = self.SQL.get_pinned_models(self.db_path, "test_instance")
        model_names = [pin[1] for pin in pins]
        
        # model3 should now be first
        self.assertEqual(model_names[0], "model3:latest")
    
    def test_empty_instance_has_no_pins(self):
        """Test that a new instance has no pinned models."""
        pins = self.SQL.get_pinned_models(self.db_path, "test_instance")
        
        self.assertEqual(len(pins), 0)


if __name__ == '__main__':
    unittest.main()
