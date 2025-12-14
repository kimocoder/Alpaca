"""
Tests for statistics recording functionality.
"""

import unittest
import tempfile
import os
import sqlite3
from datetime import datetime
from src.services.statistics import StatisticsService


class TestStatisticsRecording(unittest.TestCase):
    """Test statistics recording in the statistics service."""
    
    def setUp(self):
        """Set up test database."""
        self.temp_db = tempfile.NamedTemporaryFile(delete=False, suffix='.db')
        self.temp_db.close()
        self.db_path = self.temp_db.name
    
    def tearDown(self):
        """Clean up test database."""
        if os.path.exists(self.db_path):
            os.unlink(self.db_path)
    
    def test_record_token_usage(self):
        """Test that token usage is recorded correctly."""
        
        stats_service = StatisticsService(db_path=self.db_path)
        
        # Record token usage
        event_id = stats_service.record_token_usage(
            model="test-model",
            tokens_used=100
        )
        
        self.assertIsNotNone(event_id)
        
        # Verify it was recorded
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT model, tokens_used, event_type 
            FROM statistics 
            WHERE id = ?
        """, (event_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "test-model")
        self.assertEqual(row[1], 100)
        self.assertEqual(row[2], "token_usage")
    
    def test_record_response_time(self):
        """Test that response time is recorded correctly."""
        stats_service = StatisticsService(db_path=self.db_path)
        
        # Record response time
        event_id = stats_service.record_response_time(
            model="test-model",
            response_time_ms=1500
        )
        
        self.assertIsNotNone(event_id)
        
        # Verify it was recorded
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT model, response_time_ms, event_type 
            FROM statistics 
            WHERE id = ?
        """, (event_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "test-model")
        self.assertEqual(row[1], 1500)
        self.assertEqual(row[2], "response_time")
    
    def test_record_model_usage(self):
        """Test that model usage is recorded correctly."""
        stats_service = StatisticsService(db_path=self.db_path)
        
        # Record model usage
        event_id = stats_service.record_model_usage(model="test-model")
        
        self.assertIsNotNone(event_id)
        
        # Verify it was recorded
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("""
            SELECT model, event_type 
            FROM statistics 
            WHERE id = ?
        """, (event_id,))
        row = cursor.fetchone()
        conn.close()
        
        self.assertIsNotNone(row)
        self.assertEqual(row[0], "test-model")
        self.assertEqual(row[1], "model_usage")
    
    def test_multiple_recordings(self):
        """Test that multiple statistics can be recorded."""
        stats_service = StatisticsService(db_path=self.db_path)
        
        # Record multiple events
        stats_service.record_token_usage("model-1", 100)
        stats_service.record_token_usage("model-2", 200)
        stats_service.record_response_time("model-1", 1000)
        stats_service.record_model_usage("model-1")
        
        # Verify all were recorded
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM statistics")
        count = cursor.fetchone()[0]
        conn.close()
        
        self.assertEqual(count, 4)
    
    def test_get_token_usage(self):
        """Test retrieving token usage statistics."""
        stats_service = StatisticsService(db_path=self.db_path)
        
        # Record some token usage
        stats_service.record_token_usage("model-1", 100)
        stats_service.record_token_usage("model-1", 150)
        stats_service.record_token_usage("model-2", 200)
        
        # Get token usage stats
        stats = stats_service.get_token_usage()
        
        self.assertEqual(stats.total_tokens, 450)
        self.assertEqual(stats.by_model["model-1"], 250)
        self.assertEqual(stats.by_model["model-2"], 200)
    
    def test_get_response_times(self):
        """Test retrieving response time statistics."""
        stats_service = StatisticsService(db_path=self.db_path)
        
        # Record some response times
        stats_service.record_response_time("model-1", 1000)
        stats_service.record_response_time("model-1", 2000)
        stats_service.record_response_time("model-1", 1500)
        
        # Get response time stats
        stats = stats_service.get_response_times(model="model-1")
        
        self.assertEqual(stats.total_requests, 3)
        self.assertEqual(stats.min_ms, 1000)
        self.assertEqual(stats.max_ms, 2000)
        self.assertEqual(stats.average_ms, 1500.0)
        self.assertEqual(stats.median_ms, 1500.0)
    
    def test_get_model_usage(self):
        """Test retrieving model usage frequency."""
        stats_service = StatisticsService(db_path=self.db_path)
        
        # Record model usage
        stats_service.record_model_usage("model-1")
        stats_service.record_model_usage("model-1")
        stats_service.record_model_usage("model-2")
        
        # Get model usage stats
        usage = stats_service.get_model_usage()
        
        self.assertEqual(usage["model-1"], 2)
        self.assertEqual(usage["model-2"], 1)


if __name__ == '__main__':
    unittest.main()
