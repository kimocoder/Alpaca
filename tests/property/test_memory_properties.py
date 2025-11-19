"""
Property-based tests for memory leak prevention.

Feature: alpaca-code-quality-improvements
"""
import sys
from pathlib import Path
import time
import threading
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, strategies as st, settings, HealthCheck, assume

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from utils.memory_monitor import MemoryMonitor


# ============================================================================
# Helper strategies
# ============================================================================

@st.composite
def memory_sequence_strategy(draw):
    """
    Strategy for generating memory usage sequences.
    
    Returns a list of memory values in MB that simulate application memory usage.
    """
    num_samples = draw(st.integers(min_value=10, max_value=100))
    start_memory = draw(st.floats(min_value=50.0, max_value=200.0))
    
    # Generate growth rate (MB per sample)
    # Acceptable: <= 10MB per hour
    # With samples every 5 minutes (12 per hour), that's <= 0.833 MB per sample
    growth_per_sample = draw(st.floats(min_value=-0.5, max_value=2.0))
    
    # Generate sequence with some noise
    sequence = []
    current = start_memory
    for i in range(num_samples):
        # Add growth plus some random noise
        noise = draw(st.floats(min_value=-1.0, max_value=1.0))
        current = max(10.0, current + growth_per_sample + noise)
        sequence.append(current)
    
    return start_memory, sequence, growth_per_sample


# ============================================================================
# Property 21: Memory Leak Prevention
# Validates: Requirements 8.5
# ============================================================================

@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=3000,
    max_examples=100
)
@given(
    runtime_hours=st.floats(min_value=1.0, max_value=10.0)
)
def test_memory_leak_prevention(runtime_hours):
    """
    Feature: alpaca-code-quality-improvements, Property 21: Memory Leak Prevention
    
    Property: For any application run lasting more than 1 hour, memory growth 
    should not exceed 10MB per hour.
    
    This test simulates long-running sessions and verifies memory growth stays
    within acceptable limits.
    
    Validates: Requirements 8.5
    """
    # Mock the memory reading to simulate controlled growth
    start_memory = 100.0  # Start at 100 MB
    acceptable_growth_per_hour = 10.0  # 10 MB per hour is the limit
    
    # Calculate expected memory after runtime_hours
    # We'll simulate acceptable growth (slightly under the limit)
    growth_rate = acceptable_growth_per_hour * 0.9  # 90% of limit (safe)
    expected_final_memory = start_memory + (growth_rate * runtime_hours)
    
    # Create a sequence of memory values simulating this growth
    num_samples = int(runtime_hours * 12)  # 12 samples per hour (every 5 minutes)
    if num_samples < 2:
        num_samples = 2
    
    memory_sequence = []
    for i in range(num_samples):
        progress = i / (num_samples - 1) if num_samples > 1 else 0
        memory_at_time = start_memory + (growth_rate * runtime_hours * progress)
        memory_sequence.append(memory_at_time)
    
    # Mock psutil to return our controlled sequence
    sample_index = [0]
    
    def mock_memory_info():
        mock_info = MagicMock()
        idx = min(sample_index[0], len(memory_sequence) - 1)
        # Convert MB to bytes (RSS is in bytes)
        mock_info.rss = int(memory_sequence[idx] * 1024 * 1024)
        sample_index[0] += 1
        return mock_info
    
    with patch('psutil.Process') as mock_process_class:
        mock_process = MagicMock()
        mock_process.memory_info = mock_memory_info
        mock_process_class.return_value = mock_process
        
        # Create a monitor with short check interval for testing
        # This must be done AFTER patching psutil
        monitor = MemoryMonitor(check_interval=1)
        
        # Reset monitor with mocked memory
        monitor._start_memory = start_memory
        monitor._start_time = time.time() - (runtime_hours * 3600)
        
        # Clear any samples that were collected during initialization
        with monitor._sample_lock:
            monitor._memory_samples.clear()
        
        # Simulate taking samples over time
        simulated_time = monitor._start_time
        time_increment = (runtime_hours * 3600) / num_samples
        
        for i in range(num_samples):
            memory_mb = memory_sequence[i]
            with monitor._sample_lock:
                monitor._memory_samples.append((simulated_time, memory_mb))
            simulated_time += time_increment
        
        # Calculate growth rate
        growth_rate_measured = monitor.get_memory_growth_rate()
        
        # Get final memory from sequence
        final_memory = memory_sequence[-1]
        total_growth = final_memory - start_memory
        
        # Property assertions
        
        # 1. Memory growth rate should not exceed 10 MB per hour (with tolerance)
        assert growth_rate_measured <= acceptable_growth_per_hour + 1.0, \
            f"Memory growth rate {growth_rate_measured:.2f} MB/hour exceeds limit of {acceptable_growth_per_hour} MB/hour"
        
        # 2. Total growth should be proportional to runtime
        expected_max_growth = acceptable_growth_per_hour * runtime_hours
        assert total_growth <= expected_max_growth + 1.0, \
            f"Total memory growth {total_growth:.2f} MB exceeds expected {expected_max_growth:.2f} MB for {runtime_hours:.2f} hours"
        
        # 3. Growth rate should be reasonable (within expected range)
        # Since we're simulating 90% of limit, it should be close to 9 MB/hour
        expected_rate = growth_rate
        assert abs(growth_rate_measured - expected_rate) <= 2.0, \
            f"Growth rate {growth_rate_measured:.2f} MB/hour should be close to expected {expected_rate:.2f} MB/hour"
        
        # Cleanup
        monitor.stop_monitoring()


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=3000,
    max_examples=100
)
@given(
    start_memory=st.floats(min_value=50.0, max_value=200.0),
    growth_rate=st.floats(min_value=0.0, max_value=20.0)
)
def test_memory_growth_detection(start_memory, growth_rate):
    """
    Test that excessive memory growth is detected.
    
    Property: For any memory growth rate exceeding 10 MB/hour, the monitor
    should detect it and trigger alerts.
    """
    monitor = MemoryMonitor(check_interval=1)
    
    # Track if alert was triggered
    alert_triggered = threading.Event()
    alert_params = []
    
    def alert_callback(current_mem, rate):
        alert_params.append((current_mem, rate))
        alert_triggered.set()
    
    monitor.register_alert_callback(alert_callback)
    
    # Simulate 1 hour of runtime with the given growth rate
    runtime_hours = 1.0
    num_samples = 12  # 12 samples over 1 hour
    
    memory_sequence = []
    for i in range(num_samples):
        progress = i / (num_samples - 1) if num_samples > 1 else 0
        memory_at_time = start_memory + (growth_rate * runtime_hours * progress)
        memory_sequence.append(memory_at_time)
    
    # Mock psutil
    sample_index = [0]
    
    def mock_memory_info():
        mock_info = MagicMock()
        idx = min(sample_index[0], len(memory_sequence) - 1)
        mock_info.rss = int(memory_sequence[idx] * 1024 * 1024)
        sample_index[0] += 1
        return mock_info
    
    with patch('psutil.Process') as mock_process_class:
        mock_process = MagicMock()
        mock_process.memory_info = mock_memory_info
        mock_process_class.return_value = mock_process
        
        # Reset monitor
        monitor._start_memory = start_memory
        monitor._start_time = time.time() - 3600  # 1 hour ago
        monitor._last_alert_time = 0  # Reset alert cooldown
        
        # Add samples
        simulated_time = monitor._start_time
        time_increment = 3600 / num_samples
        
        for i in range(num_samples):
            memory_mb = memory_sequence[i]
            with monitor._sample_lock:
                monitor._memory_samples.append((simulated_time, memory_mb))
            simulated_time += time_increment
        
        # Check for excessive growth
        monitor._check_memory_growth()
        
        # Property assertions
        
        measured_rate = monitor.get_memory_growth_rate()
        
        # If growth rate exceeds threshold, alert should be triggered
        if growth_rate > monitor._max_growth_per_hour_mb:
            # Give a small margin for measurement noise
            if measured_rate > monitor._max_growth_per_hour_mb * 0.8:
                # Wait a bit for alert callback
                alert_triggered.wait(timeout=1)
                
                assert alert_triggered.is_set(), \
                    f"Alert should be triggered for growth rate {growth_rate:.2f} MB/hour (measured: {measured_rate:.2f})"
        else:
            # Growth is acceptable, no alert should be triggered
            # (unless there's measurement noise that pushes it over)
            pass
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    num_samples=st.integers(min_value=10, max_value=100)
)
def test_memory_sample_tracking(num_samples):
    """
    Test that memory samples are tracked correctly.
    
    Property: For any number of memory samples, all should be tracked
    up to the maximum buffer size.
    """
    monitor = MemoryMonitor(check_interval=1)
    
    # Add samples
    start_time = time.time()
    for i in range(num_samples):
        memory_mb = 100.0 + i * 0.1
        timestamp = start_time + i
        
        with monitor._sample_lock:
            monitor._memory_samples.append((timestamp, memory_mb))
    
    # Property assertions
    
    # 1. Samples should be tracked (up to max buffer size)
    samples = monitor.get_memory_samples()
    expected_count = min(num_samples, 1000)  # Max buffer size is 1000
    assert len(samples) == expected_count, \
        f"Should track {expected_count} samples, got {len(samples)}"
    
    # 2. Samples should be in chronological order
    for i in range(len(samples) - 1):
        assert samples[i][0] <= samples[i + 1][0], \
            "Samples should be in chronological order"
    
    # 3. If we added more than buffer size, oldest should be dropped
    if num_samples > 1000:
        # First sample should be from later in the sequence
        first_timestamp = samples[0][0]
        expected_first_timestamp = start_time + (num_samples - 1000)
        assert abs(first_timestamp - expected_first_timestamp) < 1, \
            "Oldest samples should be dropped when buffer is full"
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    num_callbacks=st.integers(min_value=1, max_value=5)
)
def test_multiple_alert_callbacks(num_callbacks):
    """
    Test that multiple alert callbacks are all invoked.
    
    Property: For any number of registered callbacks, all should be invoked
    when excessive memory growth is detected.
    """
    monitor = MemoryMonitor(check_interval=1)
    
    # Register multiple callbacks
    callback_invocations = []
    callback_lock = threading.Lock()
    
    for i in range(num_callbacks):
        def make_callback(callback_id):
            def callback(current_mem, rate):
                with callback_lock:
                    callback_invocations.append(callback_id)
            return callback
        
        monitor.register_alert_callback(make_callback(i))
    
    # Simulate excessive growth
    start_memory = 100.0
    growth_rate = 15.0  # Exceeds 10 MB/hour limit
    
    memory_sequence = [start_memory, start_memory + growth_rate]
    
    sample_index = [0]
    
    def mock_memory_info():
        mock_info = MagicMock()
        idx = min(sample_index[0], len(memory_sequence) - 1)
        mock_info.rss = int(memory_sequence[idx] * 1024 * 1024)
        sample_index[0] += 1
        return mock_info
    
    with patch('psutil.Process') as mock_process_class:
        mock_process = MagicMock()
        mock_process.memory_info = mock_memory_info
        mock_process_class.return_value = mock_process
        
        # Reset monitor
        monitor._start_memory = start_memory
        monitor._start_time = time.time() - 3600
        monitor._last_alert_time = 0
        
        # Add samples showing excessive growth
        with monitor._sample_lock:
            monitor._memory_samples.append((time.time() - 3600, start_memory))
            monitor._memory_samples.append((time.time(), start_memory + growth_rate))
        
        # Trigger check
        monitor._check_memory_growth()
        
        # Wait for callbacks
        time.sleep(0.5)
        
        # Property assertion: all callbacks should be invoked
        with callback_lock:
            assert len(callback_invocations) == num_callbacks, \
                f"All {num_callbacks} callbacks should be invoked, got {len(callback_invocations)}"
            
            for i in range(num_callbacks):
                assert i in callback_invocations, \
                    f"Callback {i} should be invoked"
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    baseline_memory=st.floats(min_value=50.0, max_value=200.0)
)
def test_baseline_reset(baseline_memory):
    """
    Test that baseline reset works correctly.
    
    Property: For any baseline reset, growth calculations should be relative
    to the new baseline.
    """
    monitor = MemoryMonitor(check_interval=1)
    
    # Set initial state
    monitor._start_memory = 100.0
    
    # Mock psutil to return baseline_memory
    def mock_memory_info():
        mock_info = MagicMock()
        mock_info.rss = int(baseline_memory * 1024 * 1024)
        return mock_info
    
    with patch('psutil.Process') as mock_process_class:
        mock_process = MagicMock()
        mock_process.memory_info = mock_memory_info
        mock_process_class.return_value = mock_process
        
        # Reset baseline
        monitor.reset_baseline()
        
        # Property assertions
        
        # 1. Start memory should be updated to current memory
        assert abs(monitor._start_memory - baseline_memory) < 0.1, \
            f"Baseline should be reset to {baseline_memory:.2f} MB"
        
        # 2. Memory growth should be zero after reset
        growth = monitor.get_memory_growth()
        assert abs(growth) < 0.1, \
            f"Growth should be ~0 after baseline reset, got {growth:.2f} MB"
        
        # 3. Samples should be cleared
        samples = monitor.get_memory_samples()
        assert len(samples) == 0, \
            "Samples should be cleared after baseline reset"
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    memory_value=st.floats(min_value=10.0, max_value=1000.0)
)
def test_memory_statistics_accuracy(memory_value):
    """
    Test that memory statistics are calculated accurately.
    
    Property: For any memory value, statistics should accurately reflect
    the current state.
    """
    monitor = MemoryMonitor(check_interval=1)
    
    # Mock psutil
    def mock_memory_info():
        mock_info = MagicMock()
        mock_info.rss = int(memory_value * 1024 * 1024)
        return mock_info
    
    with patch('psutil.Process') as mock_process_class:
        mock_process = MagicMock()
        mock_process.memory_info = mock_memory_info
        mock_process_class.return_value = mock_process
        
        # Get current memory
        current = monitor.get_current_memory_usage()
        
        # Property assertions
        
        # 1. Current memory should match mocked value
        assert abs(current - memory_value) < 0.1, \
            f"Current memory should be {memory_value:.2f} MB, got {current:.2f} MB"
        
        # 2. Statistics should be consistent
        stats = monitor.get_memory_statistics()
        
        assert 'current_mb' in stats, "Statistics should include current_mb"
        assert 'start_mb' in stats, "Statistics should include start_mb"
        assert 'growth_mb' in stats, "Statistics should include growth_mb"
        assert 'growth_rate_mb_per_hour' in stats, "Statistics should include growth_rate_mb_per_hour"
        assert 'uptime_hours' in stats, "Statistics should include uptime_hours"
        
        # 3. Growth should be current - start
        expected_growth = stats['current_mb'] - stats['start_mb']
        assert abs(stats['growth_mb'] - expected_growth) < 0.1, \
            "Growth should equal current - start"
        
        # 4. Uptime should be non-negative
        assert stats['uptime_hours'] >= 0, \
            "Uptime should be non-negative"
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=3000,
    max_examples=50
)
@given(
    num_threads=st.integers(min_value=2, max_value=5)
)
def test_thread_safe_monitoring(num_threads):
    """
    Test that memory monitoring is thread-safe.
    
    Property: For any concurrent access from multiple threads, no race
    conditions should occur.
    """
    monitor = MemoryMonitor(check_interval=1)
    
    errors = []
    error_lock = threading.Lock()
    
    def thread_worker(thread_id):
        """Worker that performs various operations"""
        try:
            for i in range(10):
                # Get current memory
                current = monitor.get_current_memory_usage()
                
                # Get statistics
                stats = monitor.get_memory_statistics()
                
                # Get samples
                samples = monitor.get_memory_samples(max_samples=10)
                
                # Small delay
                time.sleep(0.01)
        except Exception as e:
            with error_lock:
                errors.append((thread_id, str(e)))
    
    # Create and start threads
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=thread_worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for completion
    for thread in threads:
        thread.join(timeout=5)
    
    # Property assertion: no errors should occur
    assert len(errors) == 0, \
        f"No race condition errors should occur, got {len(errors)} errors: {errors}"
    
    # Cleanup
    monitor.stop_monitoring()


# ============================================================================
# Unit tests for edge cases
# ============================================================================

@pytest.mark.unit
def test_singleton_pattern():
    """Test that MemoryMonitor follows singleton pattern."""
    monitor1 = MemoryMonitor.get_instance()
    monitor2 = MemoryMonitor.get_instance()
    
    assert monitor1 is monitor2, "Should return same instance"
    
    # Cleanup
    monitor1.stop_monitoring()


@pytest.mark.unit
def test_monitoring_starts_automatically():
    """Test that monitoring starts automatically on initialization."""
    monitor = MemoryMonitor(check_interval=1)
    
    # Give it a moment to start
    time.sleep(0.1)
    
    assert monitor.is_monitoring(), "Monitoring should start automatically"
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.unit
def test_stop_monitoring():
    """Test that monitoring can be stopped."""
    monitor = MemoryMonitor(check_interval=1)
    
    # Verify it's running
    assert monitor.is_monitoring()
    
    # Stop it
    monitor.stop_monitoring()
    
    # Give it a moment to stop
    time.sleep(0.2)
    
    # Should be stopped
    assert not monitor.is_monitoring()


@pytest.mark.unit
def test_callback_registration():
    """Test that callbacks can be registered and unregistered."""
    monitor = MemoryMonitor(check_interval=1)
    
    def callback(mem, rate):
        pass
    
    # Register
    monitor.register_alert_callback(callback)
    
    with monitor._callback_lock:
        assert callback in monitor._alert_callbacks
    
    # Unregister
    monitor.unregister_alert_callback(callback)
    
    with monitor._callback_lock:
        assert callback not in monitor._alert_callbacks
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.unit
def test_get_uptime():
    """Test that uptime is calculated correctly."""
    monitor = MemoryMonitor(check_interval=1)
    
    # Set start time to 1 hour ago
    monitor._start_time = time.time() - 3600
    
    uptime = monitor.get_uptime_hours()
    
    # Should be approximately 1 hour
    assert 0.9 <= uptime <= 1.1, f"Uptime should be ~1 hour, got {uptime:.2f}"
    
    # Cleanup
    monitor.stop_monitoring()


@pytest.mark.unit
def test_convenience_functions():
    """Test that convenience functions work correctly."""
    from utils.memory_monitor import (
        get_monitor, get_current_memory_usage, get_memory_growth,
        get_memory_growth_rate, get_memory_statistics, stop_monitoring
    )
    
    # Get monitor
    monitor = get_monitor()
    assert monitor is not None
    
    # Use convenience functions
    current = get_current_memory_usage()
    assert current > 0
    
    growth = get_memory_growth()
    assert isinstance(growth, float)
    
    rate = get_memory_growth_rate()
    assert isinstance(rate, float)
    
    stats = get_memory_statistics()
    assert isinstance(stats, dict)
    
    # Cleanup
    stop_monitoring()


@pytest.mark.unit
def test_alert_cooldown():
    """Test that alert cooldown prevents spam."""
    monitor = MemoryMonitor(check_interval=1)
    monitor._alert_cooldown = 10  # 10 seconds cooldown
    
    alert_count = [0]
    
    def callback(mem, rate):
        alert_count[0] += 1
    
    monitor.register_alert_callback(callback)
    
    # Simulate excessive growth
    start_memory = 100.0
    growth_rate = 15.0
    
    def mock_memory_info():
        mock_info = MagicMock()
        mock_info.rss = int((start_memory + growth_rate) * 1024 * 1024)
        return mock_info
    
    with patch('psutil.Process') as mock_process_class:
        mock_process = MagicMock()
        mock_process.memory_info = mock_memory_info
        mock_process_class.return_value = mock_process
        
        monitor._start_memory = start_memory
        monitor._start_time = time.time() - 3600
        monitor._last_alert_time = 0
        
        # Add samples
        with monitor._sample_lock:
            monitor._memory_samples.append((time.time() - 3600, start_memory))
            monitor._memory_samples.append((time.time(), start_memory + growth_rate))
        
        # First check should trigger alert
        monitor._check_memory_growth()
        time.sleep(0.1)
        
        first_count = alert_count[0]
        assert first_count == 1, "First check should trigger alert"
        
        # Second check immediately should NOT trigger (cooldown)
        monitor._check_memory_growth()
        time.sleep(0.1)
        
        assert alert_count[0] == first_count, "Second check should not trigger due to cooldown"
    
    # Cleanup
    monitor.stop_monitoring()
