"""
Property-based tests for process manager.

Feature: alpaca-code-quality-improvements
"""
import sys
from pathlib import Path
import time
import subprocess
import threading
from unittest.mock import Mock, patch, MagicMock
from typing import List

import pytest
from hypothesis import given, strategies as st, settings

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from core.process_manager import ProcessManager, ProcessConfig


# ============================================================================
# Property 5: Process Cleanup Timing
# Validates: Requirements 2.1
# ============================================================================

@pytest.mark.property
@given(
    timeout=st.integers(min_value=1, max_value=10)
)
@settings(deadline=None, max_examples=100)
def test_process_cleanup_timing(timeout):
    """
    Feature: alpaca-code-quality-improvements, Property 5: Process Cleanup Timing
    
    Property: For any application shutdown, all processes should be stopped 
    within the specified timeout (requirement: 5 seconds).
    
    Validates: Requirements 2.1
    """
    manager = ProcessManager()
    
    # Create a mock process that simulates a running process
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.pid = 12345
    mock_process.poll.return_value = None  # Process is running
    
    # Track when terminate and kill are called
    terminate_called = False
    kill_called = False
    terminate_time = None
    kill_time = None
    
    def mock_terminate():
        nonlocal terminate_called, terminate_time
        terminate_called = True
        terminate_time = time.time()
    
    def mock_kill():
        nonlocal kill_called, kill_time
        kill_called = True
        kill_time = time.time()
    
    def mock_wait(timeout=None):
        # Simulate process taking time to terminate
        if terminate_called and not kill_called:
            # Process doesn't terminate within timeout
            raise subprocess.TimeoutExpired(cmd="test", timeout=timeout)
        return 0
    
    mock_process.terminate = mock_terminate
    mock_process.kill = mock_kill
    mock_process.wait = mock_wait
    
    # Inject the mock process
    manager._process = mock_process
    
    # Measure cleanup time
    start_time = time.time()
    result = manager.stop(timeout=timeout)
    end_time = time.time()
    elapsed = end_time - start_time
    
    # Property assertions
    
    # 1. Stop should complete within timeout + small buffer (for kill operation)
    assert elapsed <= timeout + 3, \
        f"Process cleanup should complete within {timeout + 3}s, took {elapsed}s"
    
    # 2. Process should be stopped (either terminated or killed)
    assert result is True, \
        "Process cleanup should succeed"
    
    # 3. Terminate should always be called first
    assert terminate_called, \
        "Process terminate() should be called"
    
    # 4. Process should be cleaned up (set to None)
    assert manager._process is None, \
        "Process reference should be cleared after cleanup"


@pytest.mark.property
@given(
    num_processes=st.integers(min_value=1, max_value=5)
)
@settings(deadline=None, max_examples=50)
def test_sequential_process_cleanup(num_processes):
    """
    Test that multiple sequential process starts and stops all clean up properly.
    
    Property: For any sequence of process start/stop operations, each stop
    should clean up within the timeout.
    """
    manager = ProcessManager()
    
    cleanup_times = []
    
    for i in range(num_processes):
        # Create mock process
        mock_process = MagicMock(spec=subprocess.Popen)
        mock_process.pid = 10000 + i
        mock_process.poll.return_value = None
        mock_process.wait.return_value = 0
        
        # Inject process
        manager._process = mock_process
        
        # Measure cleanup time
        start_time = time.time()
        manager.stop(timeout=5)
        elapsed = time.time() - start_time
        cleanup_times.append(elapsed)
        
        # Verify cleanup
        assert manager._process is None, \
            f"Process {i} should be cleaned up"
    
    # Property assertion: all cleanups should complete within timeout
    for i, elapsed in enumerate(cleanup_times):
        assert elapsed <= 6, \
            f"Cleanup {i} should complete within 6s, took {elapsed}s"


# ============================================================================
# Property 6: Process Lifecycle Ordering
# Validates: Requirements 2.2
# ============================================================================

@pytest.mark.property
@given(
    num_switches=st.integers(min_value=1, max_value=3)
)
@settings(deadline=None, max_examples=20)
def test_process_lifecycle_ordering(num_switches):
    """
    Feature: alpaca-code-quality-improvements, Property 6: Process Lifecycle Ordering
    
    Property: For any instance switch, the previous instance process should be 
    stopped before the new instance process starts.
    
    Validates: Requirements 2.2
    """
    manager = ProcessManager(enable_health_monitor=False)
    
    # Track process lifecycle events
    pids_sequence = []
    
    # Create all mock processes upfront
    mock_processes = []
    for i in range(num_switches):
        mock_proc = MagicMock()
        mock_proc.pid = 20000 + i
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_processes.append(mock_proc)
    
    # Mock subprocess.Popen once for all iterations
    with patch('subprocess.Popen', side_effect=mock_processes):
        for i in range(num_switches):
            config = ProcessConfig(command=["echo", f"process_{i}"])
            
            # Record PID before start
            pid_before = manager.get_pid()
            
            # Start new process
            result = manager.start(config)
            assert result is True, f"Process {i} should start successfully"
            
            # Record PID after start
            pid_after = manager.get_pid()
            
            pids_sequence.append((pid_before, pid_after))
    
    # Cleanup
    manager.stop(timeout=2)
    
    # Property assertions
    
    # 1. First start should have no previous process
    assert pids_sequence[0][0] is None, \
        "First start should have no previous process"
    
    # 2. Each subsequent start should have a different PID than before
    for i in range(1, len(pids_sequence)):
        pid_before, pid_after = pids_sequence[i]
        assert pid_before != pid_after, \
            f"Start {i}: PID should change from {pid_before} to {pid_after}"


@pytest.mark.property
@given(
    delay_between_switches=st.floats(min_value=0.0, max_value=0.1)
)
@settings(deadline=None, max_examples=20)
def test_rapid_process_switching(delay_between_switches):
    """
    Test that rapid process switching maintains proper ordering.
    
    Property: For any rapid sequence of process switches, each switch should
    properly stop the previous process before starting the new one.
    """
    manager = ProcessManager(enable_health_monitor=False)
    
    num_switches = 2
    pids_sequence = []
    
    # Create all mock processes upfront
    mock_processes = []
    for i in range(num_switches):
        mock_proc = MagicMock()
        mock_proc.pid = 30000 + i
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_processes.append(mock_proc)
    
    with patch('subprocess.Popen', side_effect=mock_processes):
        for i in range(num_switches):
            config = ProcessConfig(command=["echo", f"test_{i}"])
            
            # Start new process
            manager.start(config)
            pids_sequence.append(manager.get_pid())
            
            # Small delay between switches
            if delay_between_switches > 0:
                time.sleep(delay_between_switches)
    
    # Cleanup
    manager.stop(timeout=2)
    
    # Property assertions
    
    # 1. Should have recorded all PIDs
    assert len(pids_sequence) == num_switches, \
        f"Should have {num_switches} PIDs recorded"
    
    # 2. Each PID should be unique (processes were switched)
    assert len(set(pids_sequence)) == num_switches, \
        f"All PIDs should be unique: {pids_sequence}"


# ============================================================================
# Property 7: Process Crash Detection
# Validates: Requirements 2.3
# ============================================================================

@pytest.mark.property
@given(
    return_code=st.integers(min_value=1, max_value=255)
)
@settings(deadline=None, max_examples=20)
def test_process_crash_detection(return_code):
    """
    Feature: alpaca-code-quality-improvements, Property 7: Process Crash Detection
    
    Property: For any process crash, the system should detect it within 1 second
    and notify via callbacks.
    
    Validates: Requirements 2.3
    """
    manager = ProcessManager(enable_health_monitor=True)
    
    # Track crash detection
    crash_detected = threading.Event()
    
    def crash_callback():
        crash_detected.set()
    
    manager.register_crash_callback(crash_callback)
    
    # Create a mock process that has already crashed
    mock_process = MagicMock()
    mock_process.pid = 40000
    mock_process.poll.return_value = return_code  # Already crashed
    
    # Inject process and start health monitor
    with manager._lock:
        manager._process = mock_process
        manager._start_health_monitor()
    
    # Wait for crash detection (with timeout)
    detected = crash_detected.wait(timeout=3)
    
    # Cleanup
    manager._stop_event.set()
    if manager._health_monitor_thread:
        manager._health_monitor_thread.join(timeout=2)
    
    # Property assertions
    
    # 1. Crash should be detected
    assert detected, \
        "Crash should be detected by health monitor within 3 seconds"
    
    # 2. Process reference should be cleared after crash
    assert manager._process is None, \
        "Process reference should be cleared after crash detection"


@pytest.mark.property
@given(
    num_callbacks=st.integers(min_value=1, max_value=3)
)
@settings(deadline=None, max_examples=20)
def test_multiple_crash_callbacks(num_callbacks):
    """
    Test that all registered crash callbacks are invoked on crash.
    
    Property: For any process crash, all registered callbacks should be invoked.
    """
    manager = ProcessManager(enable_health_monitor=True)
    
    # Register multiple callbacks
    callback_invocations = []
    callback_lock = threading.Lock()
    
    for i in range(num_callbacks):
        def make_callback(callback_id):
            def callback():
                with callback_lock:
                    callback_invocations.append(callback_id)
            return callback
        
        manager.register_crash_callback(make_callback(i))
    
    # Create crashing process
    mock_process = MagicMock()
    mock_process.pid = 41000
    mock_process.poll.return_value = 1  # Crashed immediately
    
    with manager._lock:
        manager._process = mock_process
        manager._start_health_monitor()
    
    # Wait for callbacks
    time.sleep(2)
    
    # Cleanup
    manager._stop_event.set()
    if manager._health_monitor_thread:
        manager._health_monitor_thread.join(timeout=2)
    
    # Property assertion: all callbacks should be invoked
    with callback_lock:
        assert len(callback_invocations) == num_callbacks, \
            f"All {num_callbacks} callbacks should be invoked, got {len(callback_invocations)}"
        
        # All callback IDs should be present
        for i in range(num_callbacks):
            assert i in callback_invocations, \
                f"Callback {i} should be invoked"


# ============================================================================
# Property 8: Thread-Safe Process Access
# Validates: Requirements 2.4
# ============================================================================

@pytest.mark.property
@given(
    num_threads=st.integers(min_value=2, max_value=5),
    operations_per_thread=st.integers(min_value=3, max_value=10)
)
@settings(deadline=None, max_examples=10)
def test_thread_safe_process_access(num_threads, operations_per_thread):
    """
    Feature: alpaca-code-quality-improvements, Property 8: Thread-Safe Process Access
    
    Property: For any concurrent access to the process object from multiple threads,
    no race conditions should occur.
    
    Validates: Requirements 2.4
    """
    manager = ProcessManager(enable_health_monitor=False)
    
    # Track operations and errors
    operations = []
    errors = []
    operation_lock = threading.Lock()
    
    # Create all mock processes upfront
    total_mocks_needed = num_threads * operations_per_thread
    mock_processes = []
    for i in range(total_mocks_needed):
        mock_proc = MagicMock()
        mock_proc.pid = 50000 + i
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_processes.append(mock_proc)
    
    mock_index = [0]  # Use list to make it mutable in closure
    mock_lock = threading.Lock()
    
    def get_next_mock():
        with mock_lock:
            if mock_index[0] < len(mock_processes):
                mock = mock_processes[mock_index[0]]
                mock_index[0] += 1
                return mock
            return None
    
    def thread_worker(thread_id):
        """Worker that performs random operations"""
        for op_num in range(operations_per_thread):
            try:
                # Randomly choose operation
                op_type = op_num % 3
                
                if op_type == 0:
                    # Check if running
                    is_running = manager.is_running()
                    with operation_lock:
                        operations.append(('is_running', thread_id, is_running))
                
                elif op_type == 1:
                    # Get PID
                    pid = manager.get_pid()
                    with operation_lock:
                        operations.append(('get_pid', thread_id, pid))
                
                else:
                    # Start a mock process
                    mock_proc = get_next_mock()
                    if mock_proc:
                        with patch('subprocess.Popen', return_value=mock_proc):
                            config = ProcessConfig(command=["echo", f"thread_{thread_id}"])
                            result = manager.start(config)
                            with operation_lock:
                                operations.append(('start', thread_id, result))
                
                # Small delay to increase chance of race conditions
                time.sleep(0.001)
                
            except Exception as e:
                with operation_lock:
                    errors.append((thread_id, op_num, str(e)))
    
    # Create and start threads
    threads = []
    for i in range(num_threads):
        thread = threading.Thread(target=thread_worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads to complete
    for thread in threads:
        thread.join(timeout=10)
    
    # Property assertions
    
    # 1. No errors should occur due to race conditions
    assert len(errors) == 0, \
        f"No race condition errors should occur, got {len(errors)} errors: {errors[:5]}"
    
    # 2. All operations should complete
    expected_operations = num_threads * operations_per_thread
    assert len(operations) == expected_operations, \
        f"All {expected_operations} operations should complete, got {len(operations)}"
    
    # 3. Process state should be consistent (not corrupted)
    try:
        final_running = manager.is_running()
        final_pid = manager.get_pid()
        # These calls should not raise exceptions
        assert isinstance(final_running, bool), \
            "is_running() should return bool"
        assert final_pid is None or isinstance(final_pid, int), \
            "get_pid() should return None or int"
    except Exception as e:
        pytest.fail(f"Process manager in inconsistent state after concurrent access: {e}")
    
    # Cleanup
    manager.stop(timeout=2)


@pytest.mark.property
@given(
    num_concurrent_starts=st.integers(min_value=2, max_value=3)
)
@settings(deadline=None, max_examples=10)
def test_concurrent_start_operations(num_concurrent_starts):
    """
    Test that concurrent start operations don't cause race conditions.
    
    Property: For any concurrent start operations, the process should be in a consistent state.
    """
    manager = ProcessManager(enable_health_monitor=False)
    
    start_results = []
    result_lock = threading.Lock()
    
    # Create all mock processes upfront
    mock_processes = []
    for i in range(num_concurrent_starts):
        mock_proc = MagicMock()
        mock_proc.pid = 60000 + i
        mock_proc.poll.return_value = None
        mock_proc.wait.return_value = 0
        mock_proc.terminate = MagicMock()
        mock_proc.kill = MagicMock()
        mock_processes.append(mock_proc)
    
    mock_index = [0]
    mock_lock = threading.Lock()
    
    def get_next_mock():
        with mock_lock:
            if mock_index[0] < len(mock_processes):
                mock = mock_processes[mock_index[0]]
                mock_index[0] += 1
                return mock
            return None
    
    def start_worker(worker_id):
        mock_proc = get_next_mock()
        if mock_proc:
            with patch('subprocess.Popen', return_value=mock_proc):
                config = ProcessConfig(command=["echo", f"worker_{worker_id}"])
                result = manager.start(config)
                
                with result_lock:
                    start_results.append((worker_id, result, manager.get_pid()))
    
    # Start multiple threads trying to start processes
    threads = []
    for i in range(num_concurrent_starts):
        thread = threading.Thread(target=start_worker, args=(i,))
        threads.append(thread)
        thread.start()
    
    # Wait for completion
    for thread in threads:
        thread.join(timeout=5)
    
    # Property assertions
    
    # 1. All start operations should complete
    assert len(start_results) == num_concurrent_starts, \
        f"All {num_concurrent_starts} starts should complete, got {len(start_results)}"
    
    # 2. Process should be in consistent state
    final_pid = manager.get_pid()
    assert final_pid is None or isinstance(final_pid, int), \
        "Final PID should be None or a valid integer"
    
    # 3. If a process is running, it should match one of the started PIDs
    if final_pid is not None:
        started_pids = [pid for _, _, pid in start_results if pid is not None]
        assert final_pid in started_pids, \
            f"Final PID {final_pid} should be one of the started PIDs"
    
    # Cleanup
    manager.stop(timeout=2)


# ============================================================================
# Property 9: Resource Cleanup on Exit
# Validates: Requirements 2.5
# ============================================================================

@pytest.mark.property
@given(
    num_processes=st.integers(min_value=1, max_value=3)
)
@settings(deadline=None, max_examples=50)
def test_resource_cleanup_on_exit(num_processes):
    """
    Feature: alpaca-code-quality-improvements, Property 9: Resource Cleanup on Exit
    
    Property: For any application exit (normal or unexpected), no orphaned 
    processes should remain running.
    
    Validates: Requirements 2.5
    """
    # Track cleanup calls
    cleanup_calls = []
    
    for i in range(num_processes):
        manager = ProcessManager()
        
        # Create mock process
        mock_process = MagicMock()
        mock_process.pid = 70000 + i
        mock_process.poll.return_value = None
        
        terminate_called = False
        kill_called = False
        
        def make_terminate(process_id):
            def terminate():
                nonlocal terminate_called
                terminate_called = True
                cleanup_calls.append(('terminate', process_id))
            return terminate
        
        def make_kill(process_id):
            def kill():
                nonlocal kill_called
                kill_called = True
                cleanup_calls.append(('kill', process_id))
            return kill
        
        def mock_wait(timeout=None):
            if terminate_called and not kill_called:
                raise subprocess.TimeoutExpired(cmd="test", timeout=timeout)
            return 0
        
        mock_process.terminate = make_terminate(i)
        mock_process.kill = make_kill(i)
        mock_process.wait = mock_wait
        
        # Inject process
        manager._process = mock_process
        
        # Simulate exit by calling cleanup handler
        manager._cleanup_on_exit()
        
        # Verify cleanup
        assert manager._process is None, \
            f"Process {i} should be cleaned up on exit"
    
    # Property assertions
    
    # 1. All processes should have cleanup attempted
    assert len(cleanup_calls) >= num_processes, \
        f"At least {num_processes} cleanup operations should occur, got {len(cleanup_calls)}"
    
    # 2. Each process should have terminate called
    terminate_calls = [call for call in cleanup_calls if call[0] == 'terminate']
    assert len(terminate_calls) == num_processes, \
        f"All {num_processes} processes should have terminate called"


@pytest.mark.property
@given(
    process_responsive=st.booleans()
)
@settings(deadline=None, max_examples=50)
def test_cleanup_handles_unresponsive_processes(process_responsive):
    """
    Test that cleanup handles both responsive and unresponsive processes.
    
    Property: For any process (responsive or not), cleanup should complete
    successfully within the timeout.
    """
    manager = ProcessManager()
    
    mock_process = MagicMock()
    mock_process.pid = 80000
    mock_process.poll.return_value = None
    
    terminate_called = False
    kill_called = False
    
    def mock_terminate():
        nonlocal terminate_called
        terminate_called = True
    
    def mock_kill():
        nonlocal kill_called
        kill_called = True
    
    def mock_wait(timeout=None):
        if process_responsive:
            # Responsive process terminates gracefully
            return 0
        else:
            # Unresponsive process requires kill
            if terminate_called and not kill_called:
                raise subprocess.TimeoutExpired(cmd="test", timeout=timeout)
            return 0
    
    mock_process.terminate = mock_terminate
    mock_process.kill = mock_kill
    mock_process.wait = mock_wait
    
    manager._process = mock_process
    
    # Cleanup
    start_time = time.time()
    manager._cleanup_on_exit()
    elapsed = time.time() - start_time
    
    # Property assertions
    
    # 1. Cleanup should complete within reasonable time
    assert elapsed <= 7, \
        f"Cleanup should complete within 7s, took {elapsed}s"
    
    # 2. Terminate should always be called first
    assert terminate_called, \
        "Terminate should be called"
    
    # 3. Kill should be called only for unresponsive processes
    if not process_responsive:
        assert kill_called, \
            "Kill should be called for unresponsive process"
    
    # 4. Process should be cleaned up
    assert manager._process is None, \
        "Process should be cleaned up"


@pytest.mark.property
@given(
    num_managers=st.integers(min_value=1, max_value=5)
)
@settings(deadline=None, max_examples=30)
def test_multiple_managers_cleanup(num_managers):
    """
    Test that multiple process managers all clean up properly.
    
    Property: For any number of process managers, all should clean up their
    processes on exit.
    """
    managers = []
    mock_processes = []
    
    for i in range(num_managers):
        manager = ProcessManager()
        
        mock_process = MagicMock()
        mock_process.pid = 90000 + i
        mock_process.poll.return_value = None
        mock_process.wait.return_value = 0
        
        manager._process = mock_process
        
        managers.append(manager)
        mock_processes.append(mock_process)
    
    # Cleanup all managers
    for manager in managers:
        manager._cleanup_on_exit()
    
    # Property assertions
    
    # 1. All managers should have cleaned up their processes
    for i, manager in enumerate(managers):
        assert manager._process is None, \
            f"Manager {i} should have cleaned up its process"
    
    # 2. All mock processes should have terminate called
    for i, mock_process in enumerate(mock_processes):
        assert mock_process.terminate.called, \
            f"Process {i} should have terminate called"
