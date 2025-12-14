# -*- coding: utf-8 -*-
"""
Integration tests for model information caching with instance classes.

Note: These tests verify the caching logic without requiring full GTK initialization.
"""

import unittest
from src.services.model_cache import get_cache, make_cache_key


class TestModelCacheIntegration(unittest.TestCase):
    """Integration tests for model caching."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Clear cache before each test
        cache = get_cache()
        cache.clear()
    
    def test_cache_key_uniqueness_per_instance(self):
        """Test that different instances have separate cache entries."""
        cache = get_cache()
        
        # Set cache for two different instances with same model name
        key1 = make_cache_key('instance1', 'llama3:latest')
        key2 = make_cache_key('instance2', 'llama3:latest')
        
        cache.set(key1, {'instance': 'first'})
        cache.set(key2, {'instance': 'second'})
        
        # Verify they're stored separately
        result1 = cache.get(key1)
        result2 = cache.get(key2)
        
        self.assertEqual(result1['instance'], 'first')
        self.assertEqual(result2['instance'], 'second')
    
    def test_cache_workflow_simulation(self):
        """Test a typical cache workflow: set, get, invalidate."""
        cache = get_cache()
        instance_id = 'test-instance'
        model_name = 'llama3:latest'
        cache_key = make_cache_key(instance_id, model_name)
        
        # Simulate first API call - cache miss
        cached = cache.get(cache_key)
        self.assertIsNone(cached)
        
        # Simulate storing API response
        model_info = {
            'name': model_name,
            'size': '4.7GB',
            'details': {'family': 'llama'}
        }
        cache.set(cache_key, model_info)
        
        # Simulate second call - cache hit
        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertEqual(cached, model_info)
        
        # Simulate model deletion - invalidate cache
        cache.invalidate(cache_key)
        cached = cache.get(cache_key)
        self.assertIsNone(cached)
    
    def test_multiple_models_same_instance(self):
        """Test caching multiple models for the same instance."""
        cache = get_cache()
        instance_id = 'test-instance'
        
        models = ['llama3:latest', 'mistral:latest', 'gemma:latest']
        
        # Cache multiple models
        for model in models:
            cache_key = make_cache_key(instance_id, model)
            cache.set(cache_key, {'name': model})
        
        # Verify all are cached
        for model in models:
            cache_key = make_cache_key(instance_id, model)
            cached = cache.get(cache_key)
            self.assertIsNotNone(cached)
            self.assertEqual(cached['name'], model)
        
        # Invalidate one model
        cache.invalidate(make_cache_key(instance_id, 'mistral:latest'))
        
        # Verify only that one is gone
        self.assertIsNone(cache.get(make_cache_key(instance_id, 'mistral:latest')))
        self.assertIsNotNone(cache.get(make_cache_key(instance_id, 'llama3:latest')))
        self.assertIsNotNone(cache.get(make_cache_key(instance_id, 'gemma:latest')))


if __name__ == '__main__':
    unittest.main()
