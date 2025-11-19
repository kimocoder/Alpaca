"""
Memory monitoring for detecting and preventing memory leaks.

This module provides centralized memory usage tracking and alerting for
long-running sessions, ensuring memory growth stays within acceptable limits.
"""

import os
import time
import atexit
import logging
import threading
import psutil
from typing import Dict, List, Optional, Callable, Tuple
from datetime import datetime, timedelta
from collections import deque

logger = logging.getLogger(__name__)


class MemoryMonitor:
    """
    Monitors application memory usage and detects potential memory leaks.
    
    Tracks memory usage over time and alerts when memory growth exceeds
    acceptable thresholds (10MB per hour as per requirements).
    """
    
    _instance: Optional['MemoryMonitor'] = None
    _lock = threading.Lock()
    
    def __init__(self, check_interval: int = 300):
        """
        Initialize the memory monitor.
        
        Args:
            check_interval: Interval in seconds between memory checks (default: 300 = 5 minutes)
        """
        self._check_interval = check_interval
        self._monitor_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._alert_callbacks: List[Callable[[float, float], None]] = []
        self._callback_lock = threading.Lock()
        
        # Memory tracking
        self._memory_samples: deque = deque(maxlen=1000)  # Keep last 1000 samples
        self._sample_lock = threading.Lock()
        self._start_time = time.time()
        self._start_memory = self._get_current_memory_mb()
        
        # Alert thresholds
        self._max_growth_per_hour_mb = 10.0  # 10MB per hour as per requirements
        self._alert_threshold_mb = 50.0  # Alert if total growth exceeds 50MB
        
        # Track if we've alerted recently to avoid spam
        self._last_alert_time = 0
        self._alert_cooldown = 300  # 5 minutes between alerts
        
        # Register cleanup on exit
        atexit.register(self.stop_monitoring)
        
        # Start monitoring thread
        self._start_monitoring()
        
        logger.info("Memory monitor initialized")
    
    @classmethod
    def get_instance(cls, check_interval: int = 300) -> 'MemoryMonitor':
        """Get the singleton instance of MemoryMonitor."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls(check_interval)
        return cls._instance
    
    def _get_current_memory_mb(self) -> float:
        """
        Get current memory usage in MB.
        
        Returns:
            Current memory usage in megabytes
        """
        try:
            process = psutil.Process(os.getpid())
            memory_info = process.memory_info()
            # Use RSS (Resident Set Size) as the memory metric
            return memory_info.rss / (1024 * 1024)  # Convert to MB
        except Exception as e:
            logger.error(f"Failed to get memory usage: {e}")
            return 0.0
    
    def _start_monitoring(self) -> None:
        """Start the periodic memory monitoring thread."""
        if self._monitor_thread is None or not self._monitor_thread.is_alive():
            self._stop_event.clear()
            self._monitor_thread = threading.Thread(
                target=self._monitoring_loop,
                daemon=True,
                name="MemoryMonitor"
            )
            self._monitor_thread.start()
            logger.debug("Started memory monitoring thread")
    
    def _monitoring_loop(self) -> None:
        """Periodic monitoring loop that checks memory usage."""
        while not self._stop_event.is_set():
            try:
                # Take memory sample
                current_memory = self._get_current_memory_mb()
                current_time = time.time()
                
                with self._sample_lock:
                    self._memory_samples.append((current_time, current_memory))
                
                # Log memory usage
                elapsed_hours = (current_time - self._start_time) / 3600
                memory_growth = current_memory - self._start_memory
                
                logger.debug(
                    f"Memory usage: {current_memory:.2f} MB "
                    f"(growth: {memory_growth:.2f} MB over {elapsed_hours:.2f} hours)"
                )
                
                # Check for excessive memory growth
                self._check_memory_growth()
                
            except Exception as e:
                logger.error(f"Error in memory monitoring loop: {e}")
            
            # Wait for next check interval or stop event
            if self._stop_event.wait(timeout=self._check_interval):
                break
    
    def _check_memory_growth(self) -> None:
        """Check if memory growth exceeds acceptable thresholds."""
        current_time = time.time()
        current_memory = self._get_current_memory_mb()
        
        # Calculate growth rate over the last hour
        growth_rate = self._calculate_growth_rate_per_hour()
        
        # Check if growth rate exceeds threshold
        if growth_rate > self._max_growth_per_hour_mb:
            # Check cooldown to avoid alert spam
            if current_time - self._last_alert_time >= self._alert_cooldown:
                logger.warning(
                    f"Excessive memory growth detected: {growth_rate:.2f} MB/hour "
                    f"(threshold: {self._max_growth_per_hour_mb} MB/hour)"
                )
                
                # Trigger alert callbacks
                self._trigger_alerts(current_memory, growth_rate)
                self._last_alert_time = current_time
        
        # Also check total growth
        total_growth = current_memory - self._start_memory
        if total_growth > self._alert_threshold_mb:
            if current_time - self._last_alert_time >= self._alert_cooldown:
                logger.warning(
                    f"Total memory growth exceeds threshold: {total_growth:.2f} MB "
                    f"(threshold: {self._alert_threshold_mb} MB)"
                )
                
                self._trigger_alerts(current_memory, growth_rate)
                self._last_alert_time = current_time
    
    def _calculate_growth_rate_per_hour(self) -> float:
        """
        Calculate memory growth rate per hour based on recent samples.
        
        Returns:
            Growth rate in MB per hour
        """
        with self._sample_lock:
            if len(self._memory_samples) < 2:
                return 0.0
            
            # Get samples from the last hour
            current_time = time.time()
            one_hour_ago = current_time - 3600
            
            recent_samples = [
                (t, mem) for t, mem in self._memory_samples
                if t >= one_hour_ago
            ]
            
            if len(recent_samples) < 2:
                # Not enough recent samples, use all available samples
                recent_samples = list(self._memory_samples)
            
            if len(recent_samples) < 2:
                return 0.0
            
            # Calculate linear regression slope (growth rate)
            # Using simple approach: (last - first) / time_diff
            first_time, first_mem = recent_samples[0]
            last_time, last_mem = recent_samples[-1]
            
            time_diff_hours = (last_time - first_time) / 3600
            
            if time_diff_hours == 0:
                return 0.0
            
            memory_diff = last_mem - first_mem
            growth_rate = memory_diff / time_diff_hours
            
            return growth_rate
    
    def _trigger_alerts(self, current_memory: float, growth_rate: float) -> None:
        """
        Trigger all registered alert callbacks.
        
        Args:
            current_memory: Current memory usage in MB
            growth_rate: Memory growth rate in MB per hour
        """
        with self._callback_lock:
            for callback in self._alert_callbacks:
                try:
                    callback(current_memory, growth_rate)
                except Exception as e:
                    logger.error(f"Error in alert callback: {e}")
    
    def register_alert_callback(self, callback: Callable[[float, float], None]) -> None:
        """
        Register a callback to be invoked when excessive memory growth is detected.
        
        Args:
            callback: Function that takes (current_memory_mb, growth_rate_mb_per_hour)
        """
        with self._callback_lock:
            self._alert_callbacks.append(callback)
            logger.debug(f"Registered alert callback: {callback.__name__}")
    
    def unregister_alert_callback(self, callback: Callable[[float, float], None]) -> None:
        """
        Unregister an alert callback.
        
        Args:
            callback: The callback function to remove
        """
        with self._callback_lock:
            if callback in self._alert_callbacks:
                self._alert_callbacks.remove(callback)
                logger.debug(f"Unregistered alert callback: {callback.__name__}")
    
    def get_current_memory_usage(self) -> float:
        """
        Get current memory usage in MB.
        
        Returns:
            Current memory usage in megabytes
        """
        return self._get_current_memory_mb()
    
    def get_memory_growth(self) -> float:
        """
        Get total memory growth since monitoring started.
        
        Returns:
            Memory growth in megabytes
        """
        current_memory = self._get_current_memory_mb()
        return current_memory - self._start_memory
    
    def get_memory_growth_rate(self) -> float:
        """
        Get current memory growth rate per hour.
        
        Returns:
            Growth rate in MB per hour
        """
        return self._calculate_growth_rate_per_hour()
    
    def get_uptime_hours(self) -> float:
        """
        Get application uptime in hours.
        
        Returns:
            Uptime in hours
        """
        return (time.time() - self._start_time) / 3600
    
    def get_memory_statistics(self) -> Dict[str, float]:
        """
        Get comprehensive memory statistics.
        
        Returns:
            Dictionary with memory statistics
        """
        current_memory = self._get_current_memory_mb()
        growth = current_memory - self._start_memory
        growth_rate = self._calculate_growth_rate_per_hour()
        uptime_hours = self.get_uptime_hours()
        
        with self._sample_lock:
            num_samples = len(self._memory_samples)
            
            if num_samples > 0:
                memory_values = [mem for _, mem in self._memory_samples]
                min_memory = min(memory_values)
                max_memory = max(memory_values)
                avg_memory = sum(memory_values) / len(memory_values)
            else:
                min_memory = current_memory
                max_memory = current_memory
                avg_memory = current_memory
        
        return {
            'current_mb': current_memory,
            'start_mb': self._start_memory,
            'growth_mb': growth,
            'growth_rate_mb_per_hour': growth_rate,
            'uptime_hours': uptime_hours,
            'min_mb': min_memory,
            'max_mb': max_memory,
            'avg_mb': avg_memory,
            'num_samples': num_samples,
        }
    
    def get_memory_samples(self, max_samples: Optional[int] = None) -> List[Tuple[float, float]]:
        """
        Get memory samples (timestamp, memory_mb).
        
        Args:
            max_samples: Maximum number of samples to return (most recent)
        
        Returns:
            List of (timestamp, memory_mb) tuples
        """
        with self._sample_lock:
            samples = list(self._memory_samples)
            
            if max_samples is not None and len(samples) > max_samples:
                samples = samples[-max_samples:]
            
            return samples
    
    def reset_baseline(self) -> None:
        """
        Reset the memory baseline to current usage.
        
        This can be useful after known memory-intensive operations.
        """
        self._start_memory = self._get_current_memory_mb()
        self._start_time = time.time()
        
        with self._sample_lock:
            self._memory_samples.clear()
        
        logger.info(f"Reset memory baseline to {self._start_memory:.2f} MB")
    
    def stop_monitoring(self) -> None:
        """Stop the memory monitoring thread."""
        self._stop_event.set()
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=5)
            logger.debug("Stopped memory monitoring thread")
        
        # Log final statistics
        stats = self.get_memory_statistics()
        logger.info(
            f"Memory monitoring stopped. Final stats: "
            f"current={stats['current_mb']:.2f} MB, "
            f"growth={stats['growth_mb']:.2f} MB, "
            f"rate={stats['growth_rate_mb_per_hour']:.2f} MB/hour, "
            f"uptime={stats['uptime_hours']:.2f} hours"
        )
    
    def is_monitoring(self) -> bool:
        """
        Check if monitoring is active.
        
        Returns:
            True if monitoring thread is running
        """
        return (
            self._monitor_thread is not None and
            self._monitor_thread.is_alive() and
            not self._stop_event.is_set()
        )


# Convenience functions for easy access
def get_monitor(check_interval: int = 300) -> MemoryMonitor:
    """Get the global MemoryMonitor instance."""
    return MemoryMonitor.get_instance(check_interval)


def get_current_memory_usage() -> float:
    """Get current memory usage in MB."""
    return get_monitor().get_current_memory_usage()


def get_memory_growth() -> float:
    """Get total memory growth since monitoring started."""
    return get_monitor().get_memory_growth()


def get_memory_growth_rate() -> float:
    """Get current memory growth rate per hour."""
    return get_monitor().get_memory_growth_rate()


def get_memory_statistics() -> Dict[str, float]:
    """Get comprehensive memory statistics."""
    return get_monitor().get_memory_statistics()


def register_alert_callback(callback: Callable[[float, float], None]) -> None:
    """Register a callback for memory growth alerts."""
    get_monitor().register_alert_callback(callback)


def stop_monitoring() -> None:
    """Stop memory monitoring."""
    get_monitor().stop_monitoring()
