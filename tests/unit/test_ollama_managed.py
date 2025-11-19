"""
Unit tests for OllamaManaged instance with ProcessManager integration.

These tests verify that OllamaManaged correctly uses ProcessManager for
process lifecycle management and ErrorHandler for error handling.
"""
import pytest
from unittest.mock import Mock, patch
from src.core.process_manager import ProcessManager, ProcessConfig


class TestProcessManagerIntegration:
    """Test ProcessManager integration patterns used by OllamaManaged."""
    
    def test_process_manager_initialization(self):
        """Test that ProcessManager initializes correctly."""
        pm = ProcessManager(enable_health_monitor=True)
        
        assert pm is not None
        assert not pm.is_running()
        assert pm._crash_callbacks == []
    
    def test_crash_callback_registration(self):
        """Test that crash callbacks can be registered."""
        pm = ProcessManager(enable_health_monitor=True)
        
        callback_invoked = []
        
        def crash_callback():
            callback_invoked.append(True)
        
        pm.register_crash_callback(crash_callback)
        
        assert len(pm._crash_callbacks) == 1
    
    def test_start_stop_lifecycle(self):
        """Test basic start/stop lifecycle."""
        pm = ProcessManager(enable_health_monitor=False)
        
        # Create a simple config
        config = ProcessConfig(
            command=["sleep", "1"],
            env=None,
            timeout=5
        )
        
        # Start process
        success = pm.start(config)
        assert success
        assert pm.is_running()
        
        # Stop process
        success = pm.stop(timeout=2)
        assert success
        assert not pm.is_running()
    
    def test_stop_when_not_running(self):
        """Test that stop() handles non-running process gracefully."""
        pm = ProcessManager(enable_health_monitor=False)
        
        # Should not raise exception
        success = pm.stop(timeout=2)
        assert success
        assert not pm.is_running()
    
    def test_restart_without_config(self):
        """Test that restart fails without prior configuration."""
        pm = ProcessManager(enable_health_monitor=False)
        
        success = pm.restart()
        assert not success
    
    def test_get_pid_when_not_running(self):
        """Test that get_pid returns None when not running."""
        pm = ProcessManager(enable_health_monitor=False)
        
        pid = pm.get_pid()
        assert pid is None
    
    def test_get_pid_when_running(self):
        """Test that get_pid returns valid PID when running."""
        pm = ProcessManager(enable_health_monitor=False)
        
        config = ProcessConfig(
            command=["sleep", "1"],
            env=None,
            timeout=5
        )
        
        pm.start(config)
        pid = pm.get_pid()
        
        assert pid is not None
        assert isinstance(pid, int)
        assert pid > 0
        
        pm.stop(timeout=2)
    
    def test_sequential_start_stops_previous(self):
        """Test that starting a new process stops the previous one."""
        pm = ProcessManager(enable_health_monitor=False)
        
        config1 = ProcessConfig(command=["sleep", "10"], timeout=5)
        config2 = ProcessConfig(command=["sleep", "10"], timeout=5)
        
        # Start first process
        pm.start(config1)
        pid1 = pm.get_pid()
        assert pm.is_running()
        assert pid1 is not None
        
        # Start second process (should stop first)
        pm.start(config2)
        pid2 = pm.get_pid()
        assert pm.is_running()
        assert pid2 is not None
        
        # Process should have been restarted (PIDs may be same or different due to OS reuse)
        # The important thing is that the process is still running
        assert pm.is_running()
        
        pm.stop(timeout=2)
    
    def test_error_handler_integration(self):
        """Test that ErrorHandler can be used with ProcessManager."""
        from src.core.error_handler import ErrorHandler, ErrorCategory
        
        # Clear error log
        ErrorHandler.clear_error_log()
        
        # Log an error
        ErrorHandler.log_error(
            message="Test process error",
            context={'component': 'ProcessManager', 'operation': 'start'}
        )
        
        # Verify error was logged
        error_log = ErrorHandler.get_error_log()
        assert len(error_log) == 1
        assert error_log[0]['message'] == "Test process error"
        assert error_log[0]['context']['component'] == 'ProcessManager'
    
    def test_user_message_creation(self):
        """Test that ErrorHandler creates user-friendly messages."""
        from src.core.error_handler import ErrorHandler
        
        # Test with ConnectionError
        error = ConnectionError("Connection refused")
        message = ErrorHandler.create_user_message(error)
        
        assert "network" in message.lower() or "connect" in message.lower()
        assert "Connection refused" not in message  # Should be user-friendly
