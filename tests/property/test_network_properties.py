"""
Property-based tests for network client.

Feature: alpaca-code-quality-improvements
"""
import sys
from pathlib import Path
import time
from unittest.mock import Mock, patch, MagicMock
from typing import Optional

import pytest
from hypothesis import given, strategies as st, settings
import requests
from requests.exceptions import RequestException, Timeout, ConnectionError

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from core.network_client import (
    NetworkClient,
    NetworkError,
    NetworkStatus,
    RetryConfig,
    retry_with_backoff
)


# ============================================================================
# Property 2: Network Retry with Exponential Backoff
# Validates: Requirements 1.2, 6.2
# ============================================================================

@pytest.mark.property
@given(
    max_attempts=st.integers(min_value=1, max_value=5),
    base_delay=st.floats(min_value=0.1, max_value=2.0),
    exponential_base=st.floats(min_value=1.5, max_value=3.0)
)
@settings(deadline=None)
def test_network_retry_with_exponential_backoff(
    max_attempts,
    base_delay,
    exponential_base
):
    """
    Feature: alpaca-code-quality-improvements, Property 2: Network Retry with Exponential Backoff
    
    Property: For any network request that fails, the system should retry up to 
    max_attempts times with exponential backoff before failing.
    
    Validates: Requirements 1.2, 6.2
    """
    # Create retry configuration
    config = RetryConfig(
        max_attempts=max_attempts,
        base_delay=base_delay,
        exponential_base=exponential_base
    )
    
    # Track call attempts and delays
    call_count = 0
    delays = []
    
    def failing_function():
        nonlocal call_count
        call_count += 1
        raise ConnectionError(f"Attempt {call_count} failed")
    
    # Patch time.sleep to capture delays without actually sleeping
    with patch('time.sleep') as mock_sleep:
        mock_sleep.side_effect = lambda delay: delays.append(delay)
        
        # Execute function with retry
        with pytest.raises(ConnectionError):
            retry_with_backoff(
                failing_function,
                config=config,
                retryable_exceptions=(ConnectionError,)
            )
    
    # Property assertions
    
    # 1. Function should be called exactly max_attempts times
    assert call_count == max_attempts, \
        f"Function should be called {max_attempts} times, was called {call_count} times"
    
    # 2. Number of delays should be max_attempts - 1 (no delay after last attempt)
    assert len(delays) == max_attempts - 1, \
        f"Should have {max_attempts - 1} delays, got {len(delays)}"
    
    # 3. Delays should follow exponential backoff pattern (capped at max_delay)
    for i, delay in enumerate(delays):
        expected_delay = min(
            base_delay * (exponential_base ** i),
            config.max_delay
        )
        # Allow for small floating point differences
        assert abs(delay - expected_delay) < 0.01, \
            f"Delay {i} should be {expected_delay}, got {delay}"
    
    # 4. Each delay should be larger than or equal to the previous (exponential growth until max_delay)
    for i in range(len(delays) - 1):
        # Delays should increase until they hit max_delay, then stay constant
        assert delays[i + 1] >= delays[i], \
            f"Delay should not decrease: delays[{i+1}]={delays[i+1]} should be >= delays[{i}]={delays[i]}"
        
        # If neither delay has hit max_delay, the next should be strictly greater
        if delays[i] < config.max_delay and delays[i + 1] < config.max_delay:
            assert delays[i + 1] > delays[i], \
                f"Delay should increase exponentially before hitting max: delays[{i+1}]={delays[i+1]} should be > delays[{i}]={delays[i]}"


@pytest.mark.property
@given(
    max_attempts=st.integers(min_value=2, max_value=5),
    success_on_attempt=st.integers(min_value=1, max_value=5)
)
@settings(deadline=None)
def test_retry_succeeds_before_max_attempts(max_attempts, success_on_attempt):
    """
    Test that retry stops when function succeeds before max attempts.
    
    Property: For any retry configuration, if the function succeeds on attempt N
    (where N <= max_attempts), no further attempts should be made.
    """
    # Only test cases where success happens within max_attempts
    if success_on_attempt > max_attempts:
        success_on_attempt = max_attempts
    
    config = RetryConfig(max_attempts=max_attempts)
    
    call_count = 0
    
    def sometimes_succeeds():
        nonlocal call_count
        call_count += 1
        if call_count < success_on_attempt:
            raise ConnectionError(f"Attempt {call_count} failed")
        return f"Success on attempt {call_count}"
    
    with patch('time.sleep'):
        result = retry_with_backoff(
            sometimes_succeeds,
            config=config,
            retryable_exceptions=(ConnectionError,)
        )
    
    # Property assertions
    assert call_count == success_on_attempt, \
        f"Should stop after success on attempt {success_on_attempt}, but made {call_count} attempts"
    
    assert result == f"Success on attempt {success_on_attempt}", \
        "Should return the successful result"


@pytest.mark.property
@given(
    max_delay=st.floats(min_value=5.0, max_value=20.0),
    num_attempts=st.integers(min_value=3, max_value=10)
)
@settings(deadline=None)
def test_retry_respects_max_delay(max_delay, num_attempts):
    """
    Test that retry delays never exceed max_delay.
    
    Property: For any retry configuration with max_delay, no delay should exceed max_delay.
    """
    config = RetryConfig(
        max_attempts=num_attempts,
        base_delay=1.0,
        max_delay=max_delay,
        exponential_base=2.0
    )
    
    delays = []
    
    def failing_function():
        raise ConnectionError("Always fails")
    
    with patch('time.sleep') as mock_sleep:
        mock_sleep.side_effect = lambda delay: delays.append(delay)
        
        with pytest.raises(ConnectionError):
            retry_with_backoff(
                failing_function,
                config=config,
                retryable_exceptions=(ConnectionError,)
            )
    
    # Property assertion: no delay should exceed max_delay
    for i, delay in enumerate(delays):
        assert delay <= max_delay, \
            f"Delay {i} ({delay}) should not exceed max_delay ({max_delay})"


# ============================================================================
# Property 15: HTTP Timeout Configuration
# Validates: Requirements 6.1
# ============================================================================

@pytest.mark.property
@given(
    api_timeout=st.integers(min_value=10, max_value=60),
    streaming_timeout=st.integers(min_value=100, max_value=500),
    is_streaming=st.booleans()
)
@settings(deadline=None)
def test_http_timeout_configuration(api_timeout, streaming_timeout, is_streaming):
    """
    Feature: alpaca-code-quality-improvements, Property 15: HTTP Timeout Configuration
    
    Property: For any HTTP request, the timeout should be set to the configured value
    for API calls or streaming calls based on the request type.
    
    Validates: Requirements 6.1
    """
    # Create network client with specific timeouts
    client = NetworkClient(
        base_url="http://test.example.com",
        timeout=api_timeout,
        streaming_timeout=streaming_timeout
    )
    
    # Mock the session.post method to capture timeout
    captured_timeout = None
    
    def mock_post(*args, **kwargs):
        nonlocal captured_timeout
        captured_timeout = kwargs.get('timeout')
        
        # Create a mock response
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        return response
    
    with patch.object(client.session, 'post', side_effect=mock_post):
        try:
            client.post(
                endpoint="/test",
                json={"test": "data"},
                stream=is_streaming,
                retry_count=1  # Only try once for faster test
            )
        except Exception:
            pass  # Ignore any errors, we just want to check timeout
    
    # Property assertion: timeout should match the request type
    expected_timeout = streaming_timeout if is_streaming else api_timeout
    
    assert captured_timeout == expected_timeout, \
        f"Timeout should be {expected_timeout} for {'streaming' if is_streaming else 'API'} request, got {captured_timeout}"


@pytest.mark.property
@given(
    default_timeout=st.integers(min_value=10, max_value=60),
    custom_timeout=st.integers(min_value=5, max_value=120)
)
@settings(deadline=None)
def test_custom_timeout_override(default_timeout, custom_timeout):
    """
    Test that custom timeout parameter overrides default timeout.
    
    Property: For any request with a custom timeout parameter, that timeout
    should be used instead of the default.
    """
    client = NetworkClient(
        base_url="http://test.example.com",
        timeout=default_timeout
    )
    
    captured_timeout = None
    
    def mock_post(*args, **kwargs):
        nonlocal captured_timeout
        captured_timeout = kwargs.get('timeout')
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        return response
    
    with patch.object(client.session, 'post', side_effect=mock_post):
        try:
            client.post(
                endpoint="/test",
                json={"test": "data"},
                timeout=custom_timeout,
                retry_count=1
            )
        except Exception:
            pass
    
    # Property assertion: custom timeout should be used
    assert captured_timeout == custom_timeout, \
        f"Custom timeout {custom_timeout} should override default {default_timeout}, got {captured_timeout}"


# ============================================================================
# Property 16: Streaming Interruption Handling
# Validates: Requirements 6.3
# ============================================================================

@pytest.mark.property
@given(
    chunks_before_failure=st.integers(min_value=0, max_value=10),
    failure_type=st.sampled_from([ConnectionError, Timeout, RequestException])
)
@settings(deadline=None)
def test_streaming_interruption_handling(chunks_before_failure, failure_type):
    """
    Feature: alpaca-code-quality-improvements, Property 16: Streaming Interruption Handling
    
    Property: For any connection interruption during streaming, the system should 
    handle it gracefully without crashing.
    
    Validates: Requirements 6.3
    """
    client = NetworkClient(base_url="http://test.example.com")
    
    # Create mock response that yields some chunks then fails
    chunks_yielded = []
    
    def mock_iter_content(chunk_size=None, decode_unicode=False):
        for i in range(chunks_before_failure):
            yield f"chunk_{i}"
        # Simulate interruption
        raise failure_type("Connection interrupted")
    
    mock_response = Mock()
    mock_response.iter_content = mock_iter_content
    
    def mock_post(*args, **kwargs):
        if kwargs.get('stream'):
            return mock_response
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        return response
    
    with patch.object(client.session, 'post', side_effect=mock_post):
        # Property assertion: streaming should handle interruption gracefully
        # It should not raise an exception, just stop yielding
        try:
            for chunk in client.stream_post(endpoint="/test", json={"test": "data"}):
                chunks_yielded.append(chunk)
            
            # If we get here, the interruption was handled gracefully
            graceful_handling = True
        except Exception as e:
            # Streaming should NOT raise exceptions on interruption
            graceful_handling = False
            pytest.fail(
                f"Streaming should handle {failure_type.__name__} gracefully, "
                f"but raised {type(e).__name__}: {e}"
            )
    
    # Property assertions
    assert graceful_handling, \
        "Streaming should handle interruptions gracefully without raising exceptions"
    
    # Should have yielded all chunks before the failure
    assert len(chunks_yielded) == chunks_before_failure, \
        f"Should have yielded {chunks_before_failure} chunks before interruption, got {len(chunks_yielded)}"
    
    # Verify network status was updated to disconnected
    assert client.get_status() == NetworkStatus.DISCONNECTED, \
        "Network status should be DISCONNECTED after streaming interruption"


@pytest.mark.property
@given(
    num_chunks=st.integers(min_value=1, max_value=20)
)
@settings(deadline=None)
def test_streaming_without_interruption(num_chunks):
    """
    Test that streaming works correctly without interruptions.
    
    Property: For any successful streaming response, all chunks should be yielded.
    """
    client = NetworkClient(base_url="http://test.example.com")
    
    def mock_iter_content(chunk_size=None, decode_unicode=False):
        for i in range(num_chunks):
            yield f"chunk_{i}"
    
    mock_response = Mock()
    mock_response.iter_content = mock_iter_content
    
    def mock_post(*args, **kwargs):
        if kwargs.get('stream'):
            return mock_response
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        return response
    
    with patch.object(client.session, 'post', side_effect=mock_post):
        chunks_yielded = list(client.stream_post(endpoint="/test", json={"test": "data"}))
    
    # Property assertions
    assert len(chunks_yielded) == num_chunks, \
        f"Should yield all {num_chunks} chunks, got {len(chunks_yielded)}"
    
    for i, chunk in enumerate(chunks_yielded):
        assert chunk == f"chunk_{i}", \
            f"Chunk {i} should be 'chunk_{i}', got '{chunk}'"


# ============================================================================
# Property 17: Network Reconnection Data Preservation
# Validates: Requirements 6.5
# ============================================================================

@pytest.mark.property
@given(
    data_dict=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.one_of(
            st.text(max_size=50),
            st.integers(),
            st.booleans()
        ),
        min_size=1,
        max_size=10
    ),
    failures_before_success=st.integers(min_value=1, max_value=2)
)
@settings(deadline=None)
def test_network_reconnection_data_preservation(data_dict, failures_before_success):
    """
    Feature: alpaca-code-quality-improvements, Property 17: Network Reconnection Data Preservation
    
    Property: For any network reconnection after loss, no user data or chat state 
    should be lost.
    
    Validates: Requirements 6.5
    """
    client = NetworkClient(base_url="http://test.example.com")
    
    # Track the data sent in each attempt
    attempts = []
    call_count = 0
    
    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        # Capture the data sent
        sent_data = kwargs.get('json', {})
        attempts.append(sent_data)
        
        # Fail for the first N attempts, then succeed
        if call_count <= failures_before_success:
            raise ConnectionError("Network unavailable")
        
        # Success
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        response.json = Mock(return_value={"status": "success"})
        return response
    
    with patch.object(client.session, 'post', side_effect=mock_post):
        with patch('time.sleep'):  # Skip actual delays
            # Make request with data
            response = client.post(
                endpoint="/test",
                json=data_dict,
                retry_count=failures_before_success + 1
            )
    
    # Property assertions
    
    # 1. Request should eventually succeed
    assert response is not None, "Request should eventually succeed after retries"
    
    # 2. Data should be preserved across all retry attempts
    assert len(attempts) == failures_before_success + 1, \
        f"Should have made {failures_before_success + 1} attempts, made {len(attempts)}"
    
    # 3. All attempts should send the exact same data
    for i, attempt_data in enumerate(attempts):
        assert attempt_data == data_dict, \
            f"Attempt {i} should send original data, but data differs: {attempt_data} != {data_dict}"
    
    # 4. Network status should be CONNECTED after successful reconnection
    assert client.get_status() == NetworkStatus.CONNECTED, \
        "Network status should be CONNECTED after successful reconnection"


@pytest.mark.property
@given(
    initial_data=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.text(max_size=50),
        min_size=1,
        max_size=5
    ),
    num_requests=st.integers(min_value=1, max_value=5)
)
@settings(deadline=None)
def test_multiple_requests_preserve_data(initial_data, num_requests):
    """
    Test that multiple requests preserve their individual data.
    
    Property: For any sequence of requests, each request should preserve its
    own data independently.
    """
    client = NetworkClient(base_url="http://test.example.com")
    
    # Track data for each request
    request_data_log = []
    
    def mock_post(*args, **kwargs):
        sent_data = kwargs.get('json', {})
        request_data_log.append(sent_data)
        
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        return response
    
    with patch.object(client.session, 'post', side_effect=mock_post):
        # Make multiple requests with different data
        for i in range(num_requests):
            request_data = {**initial_data, 'request_id': i}
            client.post(
                endpoint="/test",
                json=request_data,
                retry_count=1
            )
    
    # Property assertions
    assert len(request_data_log) == num_requests, \
        f"Should have logged {num_requests} requests, got {len(request_data_log)}"
    
    # Each request should have its unique data preserved
    for i, logged_data in enumerate(request_data_log):
        expected_data = {**initial_data, 'request_id': i}
        assert logged_data == expected_data, \
            f"Request {i} data should be preserved: {logged_data} != {expected_data}"


# ============================================================================
# Additional Network Client Tests
# ============================================================================

@pytest.mark.property
@given(
    status_changes=st.integers(min_value=1, max_value=10)
)
@settings(deadline=None)
def test_network_status_callbacks(status_changes):
    """
    Test that network status callbacks are invoked on status changes.
    
    Property: For any network status change, all registered callbacks should be invoked.
    """
    client = NetworkClient(base_url="http://test.example.com")
    
    # Track callback invocations
    callback_invocations = []
    
    def status_callback(status: NetworkStatus):
        callback_invocations.append(status)
    
    client.add_status_callback(status_callback)
    
    # Simulate status changes by making requests that fail and succeed
    call_count = 0
    
    def mock_post(*args, **kwargs):
        nonlocal call_count
        call_count += 1
        
        # Alternate between success and failure
        if call_count % 2 == 0:
            raise ConnectionError("Network error")
        
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        return response
    
    with patch.object(client.session, 'post', side_effect=mock_post):
        with patch('time.sleep'):
            for i in range(status_changes):
                try:
                    client.post(endpoint="/test", json={}, retry_count=1)
                except NetworkError:
                    pass  # Expected for failed requests
    
    # Property assertion: callbacks should be invoked for status changes
    assert len(callback_invocations) > 0, \
        "Status callbacks should be invoked when status changes"
    
    # All invocations should be valid NetworkStatus values
    for status in callback_invocations:
        assert isinstance(status, NetworkStatus), \
            f"Callback should receive NetworkStatus, got {type(status)}"


@pytest.mark.property
@given(
    endpoint=st.text(min_size=1, max_size=50),
    params=st.dictionaries(
        keys=st.text(min_size=1, max_size=20),
        values=st.text(max_size=50),
        max_size=5
    )
)
@settings(deadline=None)
def test_get_request_with_params(endpoint, params):
    """
    Test that GET requests properly pass parameters.
    
    Property: For any GET request with parameters, those parameters should be
    passed to the underlying HTTP library.
    """
    client = NetworkClient(base_url="http://test.example.com")
    
    captured_params = None
    
    def mock_get(*args, **kwargs):
        nonlocal captured_params
        captured_params = kwargs.get('params')
        
        response = Mock()
        response.status_code = 200
        response.raise_for_status = Mock()
        return response
    
    with patch.object(client.session, 'get', side_effect=mock_get):
        client.get(endpoint=endpoint, params=params, retry_count=1)
    
    # Property assertion: parameters should be passed correctly
    assert captured_params == params, \
        f"GET parameters should be preserved: {captured_params} != {params}"
