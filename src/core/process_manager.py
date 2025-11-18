"""
Process Manager for handling Ollama subprocess lifecycle with proper synchronization.

This module provides thread-safe process management with graceful shutdown,
health monitoring, and resource cleanup.
"""

import subprocess
import threading
import time
import logging
import atexit
from typing import Optional, Dict, Any, List
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class ProcessConfig:
    """Configuration for managed process"""
    command: List[str]
    env: Optional[Dict[str, str]] = None
    cwd: Optional[str] = None
    timeout: int = 30


class ProcessManager:
    """
    Manages subprocess lifecycle with proper synchronization.
    
    Features:
    - Thread-safe process access
    - Graceful shutdown with timeout
    - Process health monitoring
    - Automatic resource cleanup
    """
    
    def __init__(self, enable_health_monitor: bool = True):
        """
        Initialize the process manager
        
        Args:
            enable_health_monitor: Whether to enable health monitoring (default: True)
        """
        self._process: Optional[subprocess.Popen] = None
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._health_monitor_thread: Optional[threading.Thread] = None
        self._config: Optional[ProcessConfig] = None
        self._last_health_check = 0.0
        self._crash_callbacks: List[callable] = []
        self._enable_health_monitor = enable_health_monitor
        
        # Register cleanup handler
        atexit.register(self._cleanup_on_exit)
    
    def start(self, config: ProcessConfig) -> bool:
        """
        Start a process with the given configuration.
        
        Args:
            config: ProcessConfig with command and environment
            
        Returns:
            True if process started successfully, False otherwise
        """
        # Check if we need to stop existing process (outside lock)
        needs_stop = False
        with self._lock:
            if self._process is not None and self._process.poll() is None:
                needs_stop = True
        
        # Stop existing process if needed (outside lock to avoid deadlock)
        if needs_stop:
            logger.warning("Process already running, stopping it first")
            self.stop(timeout=5)
        
        with self._lock:
            try:
                self._config = config
                self._stop_event.clear()
                
                # Start the process
                self._process = subprocess.Popen(
                    config.command,
                    env=config.env,
                    cwd=config.cwd,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    stdin=subprocess.PIPE
                )
                
                logger.info(f"Process started with PID {self._process.pid}")
                
                # Start health monitoring if enabled
                if self._enable_health_monitor:
                    self._start_health_monitor()
                
                return True
                
            except Exception as e:
                logger.error(f"Failed to start process: {e}")
                self._process = None
                return False
    
    def stop(self, timeout: int = 5) -> bool:
        """
        Stop the process gracefully with timeout.
        
        Args:
            timeout: Maximum time to wait for graceful shutdown in seconds
            
        Returns:
            True if process stopped successfully, False otherwise
        """
        with self._lock:
            return self._stop_process_unsafe(timeout)
    
    def _stop_process_unsafe(self, timeout: int = 5) -> bool:
        """
        Stop process without acquiring lock (internal use only).
        
        Args:
            timeout: Maximum time to wait for graceful shutdown in seconds
            
        Returns:
            True if process stopped successfully, False otherwise
        """
        if self._process is None:
            return True
        
        # Signal health monitor to stop
        self._stop_event.set()
        
        # Check if already terminated
        if self._process.poll() is not None:
            self._process = None
            return True
        
        try:
            # Try graceful termination first
            logger.info(f"Terminating process {self._process.pid}")
            self._process.terminate()
            
            # Wait for process to exit
            try:
                self._process.wait(timeout=timeout)
                logger.info("Process terminated gracefully")
                return True
            except subprocess.TimeoutExpired:
                # Force kill if timeout exceeded
                logger.warning(f"Process did not terminate within {timeout}s, forcing kill")
                self._process.kill()
                self._process.wait(timeout=2)
                logger.info("Process killed")
                return True
                
        except Exception as e:
            logger.error(f"Error stopping process: {e}")
            return False
        finally:
            # Close file handles to avoid resource warnings
            if self._process is not None:
                try:
                    if self._process.stdout:
                        self._process.stdout.close()
                    if self._process.stderr:
                        self._process.stderr.close()
                    if self._process.stdin:
                        self._process.stdin.close()
                except Exception:
                    pass  # Ignore errors during cleanup
            
            self._process = None
            # Wait for health monitor thread to finish
            if self._health_monitor_thread and self._health_monitor_thread.is_alive():
                self._health_monitor_thread.join(timeout=2)
    
    def is_running(self) -> bool:
        """
        Check if process is currently running.
        
        Returns:
            True if process is alive, False otherwise
        """
        with self._lock:
            if self._process is None:
                return False
            return self._process.poll() is None
    
    def restart(self) -> bool:
        """
        Restart the process with the same configuration.
        
        Returns:
            True if restart successful, False otherwise
        """
        if self._config is None:
            logger.error("Cannot restart: no configuration available")
            return False
        
        logger.info("Restarting process")
        self.stop(timeout=5)
        return self.start(self._config)
    
    def get_pid(self) -> Optional[int]:
        """
        Get the process ID.
        
        Returns:
            Process ID if running, None otherwise
        """
        with self._lock:
            if self._process is None:
                return None
            return self._process.pid
    
    def register_crash_callback(self, callback: callable) -> None:
        """
        Register a callback to be called when process crashes.
        
        Args:
            callback: Function to call on crash (no arguments)
        """
        with self._lock:
            self._crash_callbacks.append(callback)
    
    def _start_health_monitor(self) -> None:
        """Start the health monitoring thread (must be called with lock held)"""
        # Stop existing monitor if running
        if self._health_monitor_thread and self._health_monitor_thread.is_alive():
            self._stop_event.set()
            # Don't wait here, just start a new one
        
        self._stop_event.clear()
        self._health_monitor_thread = threading.Thread(
            target=self._health_monitor_loop,
            daemon=True,
            name="ProcessHealthMonitor"
        )
        self._health_monitor_thread.start()
    
    def _health_monitor_loop(self) -> None:
        """Health monitoring loop that runs in a separate thread"""
        logger.debug("Health monitor started")
        
        while not self._stop_event.is_set():
            # Check every 0.1 seconds for faster response
            if self._stop_event.wait(timeout=0.1):
                break
            
            with self._lock:
                if self._process is None:
                    break
                
                # Check if process has crashed
                returncode = self._process.poll()
                if returncode is not None:
                    logger.error(f"Process crashed with return code {returncode}")
                    
                    # Call crash callbacks
                    for callback in self._crash_callbacks:
                        try:
                            callback()
                        except Exception as e:
                            logger.error(f"Error in crash callback: {e}")
                    
                    self._process = None
                    break
                
                self._last_health_check = time.time()
        
        logger.debug("Health monitor stopped")
    
    def _cleanup_on_exit(self) -> None:
        """Cleanup handler called on application exit"""
        logger.info("Cleaning up processes on exit")
        
        # Use a shorter timeout for exit cleanup
        with self._lock:
            if self._process is not None:
                self._stop_process_unsafe(timeout=5)
