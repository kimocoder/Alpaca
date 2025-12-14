# -*- coding: utf-8 -*-
"""
Model Information Caching Service

This module provides a caching layer for model information to reduce API calls
and improve performance when fetching model details.
"""

import time
import threading
from typing import Dict, Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class ModelInfoCache:
    """
    Thread-safe cache for model information with TTL (Time To Live) support.
    
    This cache stores model information retrieved from various AI providers
    and automatically expires entries after a configurable time period.
    """
    
    # Default TTL: 5 minutes (300 seconds)
    DEFAULT_TTL_SECONDS = 300
    
    def __init__(self, ttl_seconds: int = DEFAULT_TTL_SECONDS):
        """
        Initialize the model info cache.
        
        Args:
            ttl_seconds: Time to live for cache entries in seconds (default: 300)
        """
        self._cache: Dict[str, Tuple[dict, float]] = {}
        self._lock = threading.Lock()
        self._ttl_seconds = ttl_seconds
        logger.info(f"ModelInfoCache initialized with TTL of {ttl_seconds} seconds")
    
    def get(self, cache_key: str) -> Optional[dict]:
        """
        Retrieve model information from cache if available and not expired.
        
        Args:
            cache_key: Unique identifier for the cached model info
                      (typically "instance_id:model_name")
        
        Returns:
            Cached model information dict if available and valid, None otherwise
        """
        with self._lock:
            if cache_key not in self._cache:
                logger.debug(f"Cache miss for key: {cache_key}")
                return None
            
            model_info, timestamp = self._cache[cache_key]
            current_time = time.time()
            
            # Check if entry has expired
            if current_time - timestamp > self._ttl_seconds:
                logger.debug(f"Cache entry expired for key: {cache_key}")
                del self._cache[cache_key]
                return None
            
            logger.debug(f"Cache hit for key: {cache_key}")
            return model_info
    
    def set(self, cache_key: str, model_info: dict) -> None:
        """
        Store model information in cache with current timestamp.
        
        Args:
            cache_key: Unique identifier for the cached model info
            model_info: Model information dictionary to cache
        """
        with self._lock:
            self._cache[cache_key] = (model_info, time.time())
            logger.debug(f"Cached model info for key: {cache_key}")
    
    def invalidate(self, cache_key: str) -> bool:
        """
        Remove a specific entry from the cache.
        
        Args:
            cache_key: Unique identifier for the cached model info to remove
        
        Returns:
            True if entry was removed, False if it didn't exist
        """
        with self._lock:
            if cache_key in self._cache:
                del self._cache[cache_key]
                logger.debug(f"Invalidated cache for key: {cache_key}")
                return True
            return False
    
    def clear(self) -> None:
        """Remove all entries from the cache."""
        with self._lock:
            count = len(self._cache)
            self._cache.clear()
            logger.info(f"Cleared {count} entries from cache")
    
    def cleanup_expired(self) -> int:
        """
        Remove all expired entries from the cache.
        
        Returns:
            Number of expired entries removed
        """
        with self._lock:
            current_time = time.time()
            expired_keys = [
                key for key, (_, timestamp) in self._cache.items()
                if current_time - timestamp > self._ttl_seconds
            ]
            
            for key in expired_keys:
                del self._cache[key]
            
            if expired_keys:
                logger.info(f"Cleaned up {len(expired_keys)} expired cache entries")
            
            return len(expired_keys)
    
    def get_stats(self) -> dict:
        """
        Get cache statistics.
        
        Returns:
            Dictionary containing cache size and other statistics
        """
        with self._lock:
            current_time = time.time()
            valid_entries = sum(
                1 for _, timestamp in self._cache.values()
                if current_time - timestamp <= self._ttl_seconds
            )
            
            return {
                'total_entries': len(self._cache),
                'valid_entries': valid_entries,
                'expired_entries': len(self._cache) - valid_entries,
                'ttl_seconds': self._ttl_seconds
            }


# Global cache instance
_global_cache: Optional[ModelInfoCache] = None


def get_cache() -> ModelInfoCache:
    """
    Get the global model info cache instance.
    
    Returns:
        The global ModelInfoCache instance
    """
    global _global_cache
    if _global_cache is None:
        _global_cache = ModelInfoCache()
    return _global_cache


def make_cache_key(instance_id: str, model_name: str) -> str:
    """
    Create a cache key from instance ID and model name.
    
    Args:
        instance_id: Unique identifier for the instance
        model_name: Name of the model
    
    Returns:
        Cache key string in format "instance_id:model_name"
    """
    return f"{instance_id}:{model_name}"
