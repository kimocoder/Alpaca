"""
Network client with retry logic and timeout handling for Alpaca.

This module provides a robust HTTP client with exponential backoff retry logic,
configurable timeouts, and connection interruption handling.
"""
import time
import logging
from typing import Optional, Dict, Any, Callable, Tuple, Type
from dataclasses import dataclass
from enum import Enum
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

from .error_handler import ErrorHandler, AlpacaError, ErrorCategory


logger = logging.getLogger('alpaca.network_client')


@dataclass
class RetryConfig:
    """Configuration for retry behavior."""
    max_attempts: int = 3
    base_delay: float = 1.0
    max_delay: float = 10.0
    exponential_base: float = 2.0


class NetworkStatus(Enum):
    """Network connection status."""
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    RECONNECTING = "reconnecting"
    UNKNOWN = "unknown"


class NetworkError(AlpacaError):
    """Network-specific error."""
    
    def __init__(
        self,
        message: str,
        user_message: Optional[str] = None,
        recoverable: bool = True,
        context: Optional[Dict[str, Any]] = None
    ):
        super().__init__(
            message=message,
            category=ErrorCategory.NETWORK,
            user_message=user_message,
            recoverable=recoverable,
            context=context
        )


def retry_with_backoff(
    func: Callable,
    config: Optional[RetryConfig] = None,
    retryable_exceptions: Tuple[Type[Exception], ...] = (RequestException,)
) -> Any:
    """
    Retry function with exponential backoff.
    
    Args:
        func: Function to retry
        config: Retry configuration
        retryable_exceptions: Tuple of exception types that should trigger retry
        
    Returns:
        Result of the function call
        
    Raises:
        The last exception if all retries fail
    """
    if config is None:
        config = RetryConfig()
    
    last_exception = None
    
    for attempt in range(config.max_attempts):
        try:
            return func()
        except retryable_exceptions as e:
            last_exception = e
            
            if attempt == config.max_attempts - 1:
                # Last attempt failed, raise the exception
                logger.error(
                    f"All {config.max_attempts} retry attempts failed: {str(e)}"
                )
                raise
            
            # Calculate delay with exponential backoff
            delay = min(
                config.base_delay * (config.exponential_base ** attempt),
                config.max_delay
            )
            
            logger.warning(
                f"Attempt {attempt + 1}/{config.max_attempts} failed: {str(e)}. "
                f"Retrying in {delay:.1f}s..."
            )
            time.sleep(delay)
    
    # This should never be reached, but just in case
    if last_exception:
        raise last_exception


class NetworkClient:
    """HTTP client with retry logic and timeouts."""
    
    def __init__(
        self,
        base_url: str,
        timeout: int = 30,
        streaming_timeout: int = 300,
        retry_config: Optional[RetryConfig] = None
    ):
        """
        Initialize NetworkClient.
        
        Args:
            base_url: Base URL for API requests
            timeout: Timeout in seconds for regular API calls
            streaming_timeout: Timeout in seconds for streaming requests
            retry_config: Configuration for retry behavior
        """
        self.base_url = base_url.rstrip('/')
        self.timeout = timeout
        self.streaming_timeout = streaming_timeout
        self.retry_config = retry_config or RetryConfig()
        self.session = requests.Session()
        self._status = NetworkStatus.UNKNOWN
        self._status_callbacks: list = []
        
        logger.info(
            f"NetworkClient initialized with base_url={base_url}, "
            f"timeout={timeout}s, streaming_timeout={streaming_timeout}s"
        )
    
    def get_status(self) -> NetworkStatus:
        """Get current network status."""
        return self._status
    
    def add_status_callback(self, callback: Callable[[NetworkStatus], None]) -> None:
        """
        Add callback to be notified of status changes.
        
        Args:
            callback: Function to call when status changes
        """
        self._status_callbacks.append(callback)
    
    def _update_status(self, new_status: NetworkStatus) -> None:
        """Update network status and notify callbacks."""
        if new_status != self._status:
            old_status = self._status
            self._status = new_status
            logger.info(f"Network status changed: {old_status.value} -> {new_status.value}")
            
            for callback in self._status_callbacks:
                try:
                    callback(new_status)
                except Exception as e:
                    logger.error(f"Error in status callback: {e}")
    
    def post(
        self,
        endpoint: str,
        data: Optional[Dict] = None,
        json: Optional[Dict] = None,
        stream: bool = False,
        retry_count: Optional[int] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """
        POST request with retry and timeout.
        
        Args:
            endpoint: API endpoint (relative to base_url)
            data: Form data to send
            json: JSON data to send
            stream: Whether to stream the response
            retry_count: Override default retry count
            timeout: Override default timeout
            
        Returns:
            Response object
            
        Raises:
            NetworkError: If request fails after all retries
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        # Use streaming timeout for streaming requests
        if timeout is None:
            timeout = self.streaming_timeout if stream else self.timeout
        
        # Create retry config with custom retry count if provided
        retry_config = self.retry_config
        if retry_count is not None:
            retry_config = RetryConfig(
                max_attempts=retry_count,
                base_delay=self.retry_config.base_delay,
                max_delay=self.retry_config.max_delay,
                exponential_base=self.retry_config.exponential_base
            )
        
        def _make_request():
            try:
                self._update_status(NetworkStatus.CONNECTED)
                response = self.session.post(
                    url,
                    data=data,
                    json=json,
                    stream=stream,
                    timeout=timeout
                )
                response.raise_for_status()
                return response
            except (ConnectionError, Timeout) as e:
                self._update_status(NetworkStatus.RECONNECTING)
                raise
            except RequestException as e:
                self._update_status(NetworkStatus.DISCONNECTED)
                raise
        
        try:
            return retry_with_backoff(
                _make_request,
                config=retry_config,
                retryable_exceptions=(RequestException,)
            )
        except RequestException as e:
            self._update_status(NetworkStatus.DISCONNECTED)
            
            # Log the error
            ErrorHandler.log_error(
                message=f"POST request to {url} failed",
                exception=e,
                context={'endpoint': endpoint, 'stream': stream}
            )
            
            # Raise NetworkError
            raise NetworkError(
                message=f"POST request failed: {str(e)}",
                user_message="Unable to connect to the service. Please check your network connection.",
                context={'url': url, 'endpoint': endpoint}
            )
    
    def get(
        self,
        endpoint: str,
        params: Optional[Dict] = None,
        retry_count: Optional[int] = None,
        timeout: Optional[int] = None
    ) -> requests.Response:
        """
        GET request with retry and timeout.
        
        Args:
            endpoint: API endpoint (relative to base_url)
            params: Query parameters
            retry_count: Override default retry count
            timeout: Override default timeout
            
        Returns:
            Response object
            
        Raises:
            NetworkError: If request fails after all retries
        """
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        if timeout is None:
            timeout = self.timeout
        
        # Create retry config with custom retry count if provided
        retry_config = self.retry_config
        if retry_count is not None:
            retry_config = RetryConfig(
                max_attempts=retry_count,
                base_delay=self.retry_config.base_delay,
                max_delay=self.retry_config.max_delay,
                exponential_base=self.retry_config.exponential_base
            )
        
        def _make_request():
            try:
                self._update_status(NetworkStatus.CONNECTED)
                response = self.session.get(
                    url,
                    params=params,
                    timeout=timeout
                )
                response.raise_for_status()
                return response
            except (ConnectionError, Timeout) as e:
                self._update_status(NetworkStatus.RECONNECTING)
                raise
            except RequestException as e:
                self._update_status(NetworkStatus.DISCONNECTED)
                raise
        
        try:
            return retry_with_backoff(
                _make_request,
                config=retry_config,
                retryable_exceptions=(RequestException,)
            )
        except RequestException as e:
            self._update_status(NetworkStatus.DISCONNECTED)
            
            # Log the error
            ErrorHandler.log_error(
                message=f"GET request to {url} failed",
                exception=e,
                context={'endpoint': endpoint}
            )
            
            # Raise NetworkError
            raise NetworkError(
                message=f"GET request failed: {str(e)}",
                user_message="Unable to connect to the service. Please check your network connection.",
                context={'url': url, 'endpoint': endpoint}
            )
    
    def stream_post(
        self,
        endpoint: str,
        json: Optional[Dict] = None,
        retry_count: Optional[int] = None
    ):
        """
        POST request with streaming response.
        
        Args:
            endpoint: API endpoint (relative to base_url)
            json: JSON data to send
            retry_count: Override default retry count
            
        Yields:
            Response chunks
            
        Raises:
            NetworkError: If request fails after all retries
        """
        response = self.post(
            endpoint=endpoint,
            json=json,
            stream=True,
            retry_count=retry_count
        )
        
        try:
            for chunk in response.iter_content(chunk_size=None, decode_unicode=True):
                if chunk:
                    yield chunk
        except (ConnectionError, Timeout, RequestException) as e:
            self._update_status(NetworkStatus.DISCONNECTED)
            
            # Log the interruption
            ErrorHandler.log_error(
                message=f"Streaming interrupted for {endpoint}",
                exception=e,
                context={'endpoint': endpoint}
            )
            
            # Don't raise, just stop yielding
            # This allows graceful handling of interruptions
            logger.warning(f"Streaming interrupted: {str(e)}")
    
    def close(self) -> None:
        """Close the session and cleanup resources."""
        self.session.close()
        logger.info("NetworkClient session closed")
