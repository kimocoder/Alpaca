"""
Property-based tests for temporary file cleanup.

Feature: alpaca-code-quality-improvements
"""
import sys
from pathlib import Path
import os
import time
import tempfile
import threading

import pytest
from hypothesis import given, strategies as st, assume, settings, HealthCheck

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from utils.temp_file_manager import TempFileManager


# ============================================================================
# Helper strategies
# ============================================================================

@st.composite
def temp_file_strategy(draw):
    """Strategy for creating temporary files with content."""
    content_size = draw(st.integers(min_value=1, max_value=10000))
    content = b'x' * content_size
    
    # Create a temporary file
    with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
        f.write(content)
        temp_path = f.name
    
    return temp_path


@st.composite
def temp_dir_strategy(draw):
    """Strategy for creating temporary directories."""
    # Create a temporary directory
    temp_dir = tempfile.mkdtemp()
    
    # Optionally add some files to it
    num_files = draw(st.integers(min_value=0, max_value=5))
    for i in range(num_files):
        file_path = os.path.join(temp_dir, f"file_{i}.txt")
        with open(file_path, 'w') as f:
            f.write(f"Content {i}")
    
    return temp_dir


# ============================================================================
# Property 19: Temporary File Cleanup
# Validates: Requirements 8.2
# ============================================================================

@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,  # 2 seconds for file operations
    max_examples=100
)
@given(
    temp_file=temp_file_strategy()
)
def test_temp_file_cleanup_on_exit(temp_file):
    """
    Feature: alpaca-code-quality-improvements, Property 19: Temporary File Cleanup
    
    Property: For any temporary file created, it should be cleaned up within 
    1 hour or on application exit, whichever comes first.
    
    This test verifies cleanup on exit behavior.
    
    Validates: Requirements 8.2
    """
    # Create a new manager instance for this test
    manager = TempFileManager()
    
    # Verify file exists
    assert os.path.exists(temp_file), "Temporary file should exist"
    
    # Track the file
    manager.track_file(temp_file)
    
    # Verify it's being tracked
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= 1, "File should be tracked"
    
    # Simulate application exit by calling cleanup_all
    cleaned = manager.cleanup_all()
    
    # Property assertion: file should be cleaned up
    assert not os.path.exists(temp_file), \
        "Temporary file should be cleaned up on exit"
    
    assert cleaned >= 1, "At least one file should have been cleaned"
    
    # Verify tracking is cleared
    file_count, dir_count = manager.get_tracked_count()
    assert file_count == 0, "No files should be tracked after cleanup"


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    temp_dir=temp_dir_strategy()
)
def test_temp_directory_cleanup_on_exit(temp_dir):
    """
    Test that temporary directories are cleaned up on exit.
    
    Property: For any temporary directory created, it should be cleaned up
    on application exit.
    """
    # Create a new manager instance
    manager = TempFileManager()
    
    # Verify directory exists
    assert os.path.exists(temp_dir), "Temporary directory should exist"
    
    # Track the directory
    manager.track_directory(temp_dir)
    
    # Verify it's being tracked
    file_count, dir_count = manager.get_tracked_count()
    assert dir_count >= 1, "Directory should be tracked"
    
    # Simulate application exit
    cleaned = manager.cleanup_all()
    
    # Property assertion: directory should be cleaned up
    assert not os.path.exists(temp_dir), \
        "Temporary directory should be cleaned up on exit"
    
    assert cleaned >= 1, "At least one directory should have been cleaned"


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=5000,  # 5 seconds for time-based test
    max_examples=50  # Fewer examples since this involves time delays
)
@given(
    temp_file=temp_file_strategy()
)
def test_temp_file_cleanup_after_one_hour(temp_file):
    """
    Test that temporary files are cleaned up after 1 hour.
    
    Property: For any temporary file created, it should be cleaned up
    within 1 hour if the application is still running.
    
    Note: This test simulates the time passage by manipulating timestamps.
    """
    # Create a new manager instance
    manager = TempFileManager()
    manager._max_age_seconds = 2  # Set to 2 seconds for testing
    
    # Verify file exists
    assert os.path.exists(temp_file), "Temporary file should exist"
    
    # Track the file
    manager.track_file(temp_file)
    
    # Verify it's being tracked
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= 1, "File should be tracked"
    
    # Simulate time passage by modifying the creation timestamp
    with manager._cleanup_lock:
        abs_path = os.path.abspath(temp_file)
        # Set creation time to 3 seconds ago (older than max_age_seconds)
        manager._tracked_files[abs_path] = time.time() - 3
    
    # Run cleanup
    cleaned = manager.cleanup_old_files()
    
    # Property assertion: old file should be cleaned up
    assert not os.path.exists(temp_file), \
        "Temporary file older than max age should be cleaned up"
    
    assert cleaned >= 1, "At least one old file should have been cleaned"
    
    # Verify tracking is cleared
    file_count, dir_count = manager.get_tracked_count()
    assert file_count == 0, "Old files should not be tracked after cleanup"


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=5000,
    max_examples=50
)
@given(
    temp_dir=temp_dir_strategy()
)
def test_temp_directory_cleanup_after_one_hour(temp_dir):
    """
    Test that temporary directories are cleaned up after 1 hour.
    
    Property: For any temporary directory created, it should be cleaned up
    within 1 hour if the application is still running.
    """
    # Create a new manager instance
    manager = TempFileManager()
    manager._max_age_seconds = 2  # Set to 2 seconds for testing
    
    # Verify directory exists
    assert os.path.exists(temp_dir), "Temporary directory should exist"
    
    # Track the directory
    manager.track_directory(temp_dir)
    
    # Simulate time passage
    with manager._cleanup_lock:
        abs_path = os.path.abspath(temp_dir)
        manager._tracked_dirs[abs_path] = time.time() - 3
    
    # Run cleanup
    cleaned = manager.cleanup_old_files()
    
    # Property assertion: old directory should be cleaned up
    assert not os.path.exists(temp_dir), \
        "Temporary directory older than max age should be cleaned up"
    
    assert cleaned >= 1, "At least one old directory should have been cleaned"


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    temp_file=temp_file_strategy()
)
def test_temp_file_not_cleaned_if_recent(temp_file):
    """
    Test that recent temporary files are NOT cleaned up.
    
    Property: For any temporary file created recently (less than 1 hour ago),
    it should NOT be cleaned up during periodic cleanup.
    """
    # Create a new manager instance
    manager = TempFileManager()
    manager._max_age_seconds = 3600  # 1 hour
    
    # Verify file exists
    assert os.path.exists(temp_file), "Temporary file should exist"
    
    # Track the file (with current timestamp)
    manager.track_file(temp_file)
    
    # Run cleanup immediately (file is recent)
    cleaned = manager.cleanup_old_files()
    
    # Property assertion: recent file should NOT be cleaned up
    assert os.path.exists(temp_file), \
        "Recent temporary file should not be cleaned up"
    
    # Verify it's still being tracked
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= 1, "Recent file should still be tracked"
    
    # Clean up manually for test
    os.remove(temp_file)


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    num_files=st.integers(min_value=1, max_value=10)
)
def test_multiple_temp_files_cleanup(num_files):
    """
    Test that multiple temporary files are all cleaned up.
    
    Property: For any number of temporary files created, all should be
    cleaned up on application exit.
    """
    # Create a new manager instance
    manager = TempFileManager()
    
    # Create multiple temporary files
    temp_files = []
    for i in range(num_files):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(f"Content {i}")
            temp_files.append(f.name)
    
    # Track all files
    for temp_file in temp_files:
        manager.track_file(temp_file)
    
    # Verify all exist
    for temp_file in temp_files:
        assert os.path.exists(temp_file), f"File {temp_file} should exist"
    
    # Verify tracking count
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= num_files, f"Should track at least {num_files} files"
    
    # Cleanup all
    cleaned = manager.cleanup_all()
    
    # Property assertion: all files should be cleaned up
    for temp_file in temp_files:
        assert not os.path.exists(temp_file), \
            f"File {temp_file} should be cleaned up"
    
    assert cleaned >= num_files, f"Should clean at least {num_files} files"


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    temp_file=temp_file_strategy()
)
def test_untrack_prevents_cleanup(temp_file):
    """
    Test that untracking a file prevents its cleanup.
    
    Property: For any temporary file that is untracked, it should NOT be
    cleaned up during cleanup operations.
    """
    # Create a new manager instance
    manager = TempFileManager()
    
    # Verify file exists
    assert os.path.exists(temp_file), "Temporary file should exist"
    
    # Track the file
    manager.track_file(temp_file)
    
    # Verify it's being tracked
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= 1, "File should be tracked"
    
    # Untrack the file
    manager.untrack_file(temp_file)
    
    # Verify it's no longer tracked
    file_count, dir_count = manager.get_tracked_count()
    assert file_count == 0, "File should not be tracked after untracking"
    
    # Run cleanup
    manager.cleanup_all()
    
    # Property assertion: untracked file should still exist
    assert os.path.exists(temp_file), \
        "Untracked file should not be cleaned up"
    
    # Clean up manually for test
    os.remove(temp_file)


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=2000,
    max_examples=100
)
@given(
    temp_file=temp_file_strategy()
)
def test_file_age_tracking(temp_file):
    """
    Test that file age is tracked correctly.
    
    Property: For any temporary file, the manager should accurately track
    its age in seconds.
    """
    # Create a new manager instance
    manager = TempFileManager()
    
    # Track the file
    start_time = time.time()
    manager.track_file(temp_file)
    
    # Get age immediately
    age = manager.get_file_age(temp_file)
    
    # Property assertion: age should be very small (just created)
    assert age is not None, "Age should be returned for tracked file"
    assert age >= 0, "Age should be non-negative"
    assert age < 1, "Age should be less than 1 second for just-tracked file"
    
    # Wait a bit
    time.sleep(0.1)
    
    # Get age again
    age2 = manager.get_file_age(temp_file)
    
    # Property assertion: age should have increased
    assert age2 > age, "Age should increase over time"
    
    # Clean up
    os.remove(temp_file)


@pytest.mark.property
@settings(
    suppress_health_check=[HealthCheck.function_scoped_fixture],
    deadline=3000,
    max_examples=50
)
@given(
    num_files=st.integers(min_value=2, max_value=5)
)
def test_thread_safe_tracking(num_files):
    """
    Test that tracking is thread-safe.
    
    Property: For any number of files tracked concurrently from multiple
    threads, all should be tracked correctly without race conditions.
    """
    # Create a new manager instance
    manager = TempFileManager()
    
    # Create temporary files
    temp_files = []
    for i in range(num_files):
        with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
            f.write(f"Content {i}")
            temp_files.append(f.name)
    
    # Track files from multiple threads
    threads = []
    for temp_file in temp_files:
        thread = threading.Thread(target=manager.track_file, args=(temp_file,))
        threads.append(thread)
        thread.start()
    
    # Wait for all threads
    for thread in threads:
        thread.join()
    
    # Property assertion: all files should be tracked
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= num_files, \
        f"Should track all {num_files} files even with concurrent access"
    
    # Clean up
    manager.cleanup_all()


# ============================================================================
# Unit tests for edge cases
# ============================================================================

@pytest.mark.unit
def test_singleton_pattern():
    """Test that TempFileManager follows singleton pattern."""
    manager1 = TempFileManager.get_instance()
    manager2 = TempFileManager.get_instance()
    
    assert manager1 is manager2, "Should return same instance"


@pytest.mark.unit
def test_track_nonexistent_file():
    """Test that tracking a non-existent file doesn't crash."""
    manager = TempFileManager()
    
    # Track a file that doesn't exist
    manager.track_file("/nonexistent/file.txt")
    
    # Should be tracked
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= 1
    
    # Cleanup should handle gracefully
    cleaned = manager.cleanup_all()
    # Won't clean non-existent file, but shouldn't crash
    assert cleaned >= 0


@pytest.mark.unit
def test_untrack_nonexistent_file():
    """Test that untracking a non-tracked file doesn't crash."""
    manager = TempFileManager()
    
    # Untrack a file that was never tracked
    manager.untrack_file("/nonexistent/file.txt")
    
    # Should not crash
    file_count, dir_count = manager.get_tracked_count()
    assert file_count == 0


@pytest.mark.unit
def test_get_age_of_untracked_file():
    """Test that getting age of untracked file returns None."""
    manager = TempFileManager()
    
    age = manager.get_file_age("/nonexistent/file.txt")
    
    assert age is None, "Age of untracked file should be None"


@pytest.mark.unit
def test_cleanup_empty_manager():
    """Test that cleanup on empty manager doesn't crash."""
    manager = TempFileManager()
    
    cleaned = manager.cleanup_all()
    
    assert cleaned == 0, "Should clean 0 files when manager is empty"


@pytest.mark.unit
def test_periodic_cleanup_thread_starts():
    """Test that periodic cleanup thread starts automatically."""
    manager = TempFileManager()
    
    # Thread should be started
    assert manager._cleanup_thread is not None
    assert manager._cleanup_thread.is_alive()
    
    # Stop it
    manager.stop_cleanup_thread()


@pytest.mark.unit
def test_stop_cleanup_thread():
    """Test that cleanup thread can be stopped."""
    manager = TempFileManager()
    
    # Thread should be running
    assert manager._cleanup_thread.is_alive()
    
    # Stop it
    manager.stop_cleanup_thread()
    
    # Give it a moment to stop
    time.sleep(0.1)
    
    # Should be stopped
    assert not manager._cleanup_thread.is_alive()


@pytest.mark.unit
def test_cleanup_with_permission_error():
    """Test that cleanup handles permission errors gracefully."""
    manager = TempFileManager()
    
    # Create a temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test")
        temp_file = f.name
    
    # Track it
    manager.track_file(temp_file)
    
    # Make it read-only (simulate permission error on some systems)
    try:
        os.chmod(temp_file, 0o444)
    except:
        pass  # Skip if chmod not supported
    
    # Try to cleanup (might fail due to permissions, but shouldn't crash)
    try:
        manager.cleanup_all()
    except:
        pytest.fail("Cleanup should handle permission errors gracefully")
    finally:
        # Clean up manually
        try:
            os.chmod(temp_file, 0o644)
            os.remove(temp_file)
        except:
            pass


@pytest.mark.unit
def test_convenience_functions():
    """Test that convenience functions work correctly."""
    from utils.temp_file_manager import (
        get_manager, track_file, track_directory,
        untrack_file, untrack_directory, cleanup_all
    )
    
    # Create a temp file
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        f.write("test")
        temp_file = f.name
    
    # Use convenience functions
    track_file(temp_file)
    
    manager = get_manager()
    file_count, dir_count = manager.get_tracked_count()
    assert file_count >= 1
    
    untrack_file(temp_file)
    
    # Clean up
    os.remove(temp_file)
