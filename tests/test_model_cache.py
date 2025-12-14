# -*- coding: utf-8 -*-
"""
Unit tests for model information caching service.
"""

import unittest
import time
import threading
from src.services.model_cache import ModelInfoCache, get_cache, make_cache_key


class TestModelInfoCache(unittest.TestCase):
    """Test cases for ModelInfoCache class."""
    
    def setUp(self):
        """Set up test fixtures."""
        self.cache = ModelInfoCache(ttl_seconds=2)  # Short TTL for testing
        self.test_model_info = {
            'name': 'test-model',
            'size': '7B',
            'capabilities': ['completion']
        }
    
    def tearDown(self):
        """Clean up after tests."""
        self.cache.clear()
    
    def test_cache_miss_returns_none(self):
        """Test that cache returns None for non-existent keys."""
        result = self.cache.get('nonexistent:model')
        self.assertIsNone(result)
    
    def test_cache_hit_returns_data(self):
        """Test that cache returns stored data for valid keys."""
        cache_key = 'instance1:model1'
        self.cache.set(cache_key, self.test_model_info)
        
        result = self.cache.get(cache_key)
        self.assertIsNotNone(result)
        self.assertEqual(result, self.test_model_info)
    
    def test_cache_expiration(self):
        """Test that cache entries expire after TTL."""
        cache_key = 'instance1:model1'
        self.cache.set(cache_key, self.test_model_info)
        
        # Verify data is available immediately
        result = self.cache.get(cache_key)
        self.assertIsNotNone(result)
        
        # Wait for expiration
        time.sleep(2.5)
        
        # Verify data has expired
        result = self.cache.get(cache_key)
        self.assertIsNone(result)
    
    def test_cache_invalidation(self):
        """Test manual cache invalidation."""
        cache_key = 'instance1:model1'
        self.cache.set(cache_key, self.test_model_info)
        
        # Verify data is cached
        self.assertIsNotNone(self.cache.get(cache_key))
        
        # Invalidate
        result = self.cache.invalidate(cache_key)
        self.assertTrue(result)
        
        # Verify data is gone
        self.assertIsNone(self.cache.get(cache_key))
    
    def test_invalidate_nonexistent_key(self):
        """Test invalidating a key that doesn't exist."""
        result = self.cache.invalidate('nonexistent:model')
        self.assertFalse(result)
    
    def test_cache_clear(self):
        """Test clearing all cache entries."""
        self.cache.set('instance1:model1', self.test_model_info)
        self.cache.set('instance2:model2', self.test_model_info)
        
        self.cache.clear()
        
        self.assertIsNone(self.cache.get('instance1:model1'))
        self.assertIsNone(self.cache.get('instance2:model2'))
    
    def test_cleanup_expired(self):
        """Test cleanup of expired entries."""
        # Add entries with different timestamps
        self.cache.set('instance1:model1', self.test_model_info)
        time.sleep(1)
        self.cache.set('instance2:model2', self.test_model_info)
        
        # Wait for first entry to expire
        time.sleep(1.5)
        
        # Cleanup should remove first entry
        removed = self.cache.cleanup_expired()
        self.assertEqual(removed, 1)
        
        # Verify first is gone, second remains
        self.assertIsNone(self.cache.get('instance1:model1'))
        self.assertIsNotNone(self.cache.get('instance2:model2'))
    
    def test_get_stats(self):
        """Test cache statistics."""
        self.cache.set('instance1:model1', self.test_model_info)
        self.cache.set('instance2:model2', self.test_model_info)
        
        stats = self.cache.get_stats()
        
        self.assertEqual(stats['total_entries'], 2)
        self.assertEqual(stats['valid_entries'], 2)
        self.assertEqual(stats['expired_entries'], 0)
        self.assertEqual(stats['ttl_seconds'], 2)
    
    def test_thread_safety(self):
        """Test that cache operations are thread-safe."""
        cache_key = 'instance1:model1'
        num_threads = 10
        operations_per_thread = 100
        
        def worker():
            for i in range(operations_per_thread):
                self.cache.set(cache_key, {'iteration': i})
                result = self.cache.get(cache_key)
                self.assertIsNotNone(result)
        
        threads = [threading.Thread(target=worker) for _ in range(num_threads)]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verify cache is still consistent
        result = self.cache.get(cache_key)
        self.assertIsNotNone(result)
        self.assertIn('iteration', result)


class TestCacheHelpers(unittest.TestCase):
    """Test cases for cache helper functions."""
    
    def test_make_cache_key(self):
        """Test cache key generation."""
        key = make_cache_key('instance123', 'llama3:latest')
        self.assertEqual(key, 'instance123:llama3:latest')
    
    def test_get_cache_singleton(self):
        """Test that get_cache returns the same instance."""
        cache1 = get_cache()
        cache2 = get_cache()
        self.assertIs(cache1, cache2)


if __name__ == '__main__':
    unittest.main()
