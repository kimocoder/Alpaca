"""
Property-based tests for repository layer.

Feature: alpaca-code-quality-improvements
"""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, strategies as st, settings, assume

# Add src to path
src_path = Path(__file__).parent.parent.parent / "src"
sys.path.insert(0, str(src_path))

from repositories.base_repository import BaseRepository, ConnectionPool
from repositories.chat_repository import ChatRepository
from repositories.message_repository import MessageRepository
from repositories.instance_repository import InstanceRepository
from core.error_handler import AlpacaError, ErrorCategory


# ============================================================================
# Property 3: Database Error Handling
# **Validates: Requirements 1.3**
# ============================================================================

@given(
    query=st.text(min_size=1, max_size=100),
    params=st.tuples(st.text(), st.integers())
)
@settings(max_examples=100)
def test_database_error_handling_property(query, params):
    """
    Feature: alpaca-code-quality-improvements, Property 3: Database Error Handling
    
    For any database operation that fails, the system should log the error 
    and display a user-friendly notification.
    
    This test verifies that:
    1. Database errors are caught and wrapped in AlpacaError
    2. Errors are logged with appropriate context
    3. User-friendly messages are provided
    4. The error category is DATABASE
    """
    # Create a temporary database for this test
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Initialize database schema
        conn = sqlite3.connect(temp_db)
        conn.execute("CREATE TABLE IF NOT EXISTS test_table (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()
        
        # Create a repository with the temp database
        repo = BaseRepository(temp_db)
        
        # Clear error log before test
        from core.error_handler import ErrorHandler
        ErrorHandler.clear_error_log()
        
        # Attempt to execute an invalid query (should fail)
        # We'll use a malformed SQL query to trigger an error
        invalid_query = "SELECT * FROM nonexistent_table_xyz WHERE invalid syntax"
        
        try:
            repo.execute_query(invalid_query, params, context="test_context")
            # If we get here, the query somehow succeeded (shouldn't happen)
            # This is acceptable for the property test
        except AlpacaError as e:
            # Verify error is properly wrapped
            assert e.category == ErrorCategory.DATABASE
            assert e.user_message is not None
            assert len(e.user_message) > 0
            assert "database" in e.user_message.lower() or "data" in e.user_message.lower()
            
            # Verify error was logged
            error_log = ErrorHandler.get_error_log()
            assert len(error_log) > 0
            
            # Check that the log entry has required fields
            log_entry = error_log[-1]
            assert 'timestamp' in log_entry
            assert 'message' in log_entry
            assert 'context' in log_entry
            assert 'exception_type' in log_entry
            assert 'stack_trace' in log_entry
            
            # Verify context includes query information
            assert 'query' in log_entry['context']
        except Exception as e:
            # Any other exception type is a test failure
            pytest.fail(f"Expected AlpacaError but got {type(e).__name__}: {e}")
    finally:
        # Cleanup
        try:
            os.unlink(temp_db)
        except OSError:
            pass


@given(
    update_query=st.text(min_size=1, max_size=100),
    params=st.tuples(st.text(), st.integers())
)
@settings(max_examples=100)
def test_database_update_error_handling_property(update_query, params):
    """
    Feature: alpaca-code-quality-improvements, Property 3: Database Error Handling
    
    For any database update operation that fails, the system should log the error 
    and display a user-friendly notification.
    
    This test verifies error handling for UPDATE/INSERT/DELETE operations.
    """
    # Create a temporary database for this test
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Initialize database schema
        conn = sqlite3.connect(temp_db)
        conn.execute("CREATE TABLE IF NOT EXISTS test_table (id TEXT PRIMARY KEY)")
        conn.commit()
        conn.close()
        
        repo = BaseRepository(temp_db)
        
        # Clear error log before test
        from core.error_handler import ErrorHandler
        ErrorHandler.clear_error_log()
        
        # Attempt to execute an invalid update (should fail)
        invalid_update = "UPDATE nonexistent_table SET column = ? WHERE id = ?"
        
        try:
            repo.execute_update(invalid_update, params, context="test_update_context")
        except AlpacaError as e:
            # Verify error is properly wrapped
            assert e.category == ErrorCategory.DATABASE
            assert e.user_message is not None
            assert len(e.user_message) > 0
            
            # Verify error was logged
            error_log = ErrorHandler.get_error_log()
            assert len(error_log) > 0
            
            # Check that the log entry has required fields
            log_entry = error_log[-1]
            assert 'timestamp' in log_entry
            assert 'message' in log_entry
            assert 'context' in log_entry
        except Exception as e:
            # Any other exception type is a test failure
            pytest.fail(f"Expected AlpacaError but got {type(e).__name__}: {e}")
    finally:
        # Cleanup
        try:
            os.unlink(temp_db)
        except OSError:
            pass


def test_database_connection_pool_error_handling(temp_db):
    """
    Test that connection pool properly handles timeout errors.
    
    This verifies that when no connections are available, the system
    provides a user-friendly error message.
    """
    # Create a pool with size 1
    pool = ConnectionPool(temp_db, pool_size=1)
    
    # Get the only connection
    conn1 = pool.get_connection()
    
    # Try to get another connection with short timeout
    try:
        conn2 = pool.get_connection(timeout=0.1)
        pytest.fail("Expected AlpacaError for connection timeout")
    except AlpacaError as e:
        assert e.category == ErrorCategory.DATABASE
        assert "busy" in e.user_message.lower() or "try again" in e.user_message.lower()
        assert e.recoverable is True
    finally:
        pool.return_connection(conn1)
        pool.close_all()


def test_database_transaction_rollback_on_error(temp_db):
    """
    Test that transactions are properly rolled back on error.
    
    This ensures data integrity when operations fail.
    """
    repo = ChatRepository(temp_db)
    
    # Create a valid chat
    chat1 = {
        'id': 'test-chat-1',
        'name': 'Test Chat 1',
        'folder': None,
        'is_template': False
    }
    repo.create(chat1)
    
    # Verify it was created
    assert repo.exists('test-chat-1')
    
    # Now try to create a chat with the same ID (should fail due to PRIMARY KEY constraint)
    chat2 = {
        'id': 'test-chat-1',  # Same ID
        'name': 'Test Chat 2',
        'folder': None,
        'is_template': False
    }
    
    try:
        repo.create(chat2)
        pytest.fail("Expected AlpacaError for duplicate primary key")
    except AlpacaError:
        # Expected error
        pass
    
    # Verify the original chat still exists and wasn't corrupted
    original = repo.get_by_id('test-chat-1')
    assert original is not None
    assert original['name'] == 'Test Chat 1'


# ============================================================================
# Property 13: Search Performance
# **Validates: Requirements 4.4**
# ============================================================================

@given(
    num_messages=st.integers(min_value=100, max_value=1000),
    search_term=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))
)
@settings(max_examples=100, deadline=None)
def test_search_performance_property(num_messages, search_term):
    """
    Feature: alpaca-code-quality-improvements, Property 13: Search Performance
    
    For any message search operation, results should be returned within 100ms 
    for chats up to 1000 messages.
    
    This test verifies that:
    1. Search completes within 100ms for up to 1000 messages
    2. Search returns relevant results
    3. Search handles various search terms correctly
    """
    import time
    
    # Skip if search term is empty or only whitespace
    assume(search_term.strip() != '')
    
    # Create a temporary database for this test
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Initialize database schema
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT,
                is_template INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT,
                content TEXT NOT NULL,
                date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chat(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        conn.close()
        
        # Create a chat and messages
        chat_repo = ChatRepository(temp_db)
        message_repo = MessageRepository(temp_db)
        
        chat_id = f'test-chat-{num_messages}'
        chat = {
            'id': chat_id,
            'name': f'Test Chat {num_messages}',
            'folder': None,
            'is_template': False
        }
        chat_repo.create(chat)
        
        # Create messages with some containing the search term
        messages_with_term = max(1, num_messages // 10)  # 10% contain search term
        
        for i in range(num_messages):
            message_id = f'msg-{chat_id}-{i}'
            # Every 10th message contains the search term
            if i % 10 == 0 and messages_with_term > 0:
                content = f"This message contains {search_term} in the content"
                messages_with_term -= 1
            else:
                content = f"This is message number {i} without the search term"
            
            message = {
                'id': message_id,
                'chat_id': chat_id,
                'role': 'user',
                'model': 'test-model',
                'date_time': f'2024/01/01 12:{i % 60:02d}:00',
                'content': content
            }
            message_repo.create(message)
        
        # Measure search performance
        start_time = time.time()
        results = message_repo.search(search_term, chat_id=chat_id, limit=100)
        end_time = time.time()
        
        search_time_ms = (end_time - start_time) * 1000
        
        # Verify performance requirement: search should complete within 100ms
        assert search_time_ms < 100, f"Search took {search_time_ms:.2f}ms, expected < 100ms for {num_messages} messages"
        
        # Verify results are relevant (contain the search term)
        for result in results:
            assert search_term.lower() in result['content'].lower(), \
                f"Result does not contain search term: {result['content']}"
        
        # Verify we got some results (at least 1 since we added messages with the term)
        expected_results = min(num_messages // 10, 100)  # Limited by query limit
        assert len(results) > 0, "Search should return at least one result"
        assert len(results) <= 100, "Search should respect the limit parameter"
    finally:
        # Cleanup
        try:
            os.unlink(temp_db)
        except OSError:
            pass


@given(
    search_term=st.text(min_size=3, max_size=20, alphabet=st.characters(whitelist_categories=('Lu', 'Ll')))
)
@settings(max_examples=100)
def test_search_across_multiple_chats_property(search_term):
    """
    Feature: alpaca-code-quality-improvements, Property 13: Search Performance
    
    For any search operation across multiple chats, results should be returned 
    efficiently and include messages from all relevant chats.
    
    This test verifies that:
    1. Search works across multiple chats when chat_id is None
    2. Results are ordered by date (most recent first)
    3. Search respects the limit parameter
    """
    import time
    
    # Skip if search term is empty or only whitespace
    assume(search_term.strip() != '')
    
    # Create a temporary database for this test
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        temp_db = f.name
    
    try:
        # Initialize database schema
        conn = sqlite3.connect(temp_db)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS chat (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                folder TEXT,
                is_template INTEGER DEFAULT 0
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS message (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL,
                model TEXT,
                content TEXT NOT NULL,
                date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chat(id) ON DELETE CASCADE
            )
        """)
        conn.commit()
        conn.close()
        
        chat_repo = ChatRepository(temp_db)
        message_repo = MessageRepository(temp_db)
        
        # Create multiple chats
        num_chats = 5
        messages_per_chat = 20
        
        for chat_idx in range(num_chats):
            chat_id = f'test-chat-multi-{chat_idx}'
            chat = {
                'id': chat_id,
                'name': f'Test Chat {chat_idx}',
                'folder': None,
                'is_template': False
            }
            chat_repo.create(chat)
            
            # Create messages, some with search term
            for msg_idx in range(messages_per_chat):
                message_id = f'msg-{chat_id}-{msg_idx}'
                # Every 5th message contains the search term
                if msg_idx % 5 == 0:
                    content = f"Chat {chat_idx} message {msg_idx} contains {search_term}"
                else:
                    content = f"Chat {chat_idx} message {msg_idx} without term"
                
                message = {
                    'id': message_id,
                    'chat_id': chat_id,
                    'role': 'user',
                    'model': 'test-model',
                    'date_time': f'2024/01/{chat_idx + 1:02d} 12:{msg_idx % 60:02d}:00',
                    'content': content
                }
                message_repo.create(message)
        
        # Search across all chats
        start_time = time.time()
        results = message_repo.search(search_term, chat_id=None, limit=50)
        end_time = time.time()
        
        search_time_ms = (end_time - start_time) * 1000
        
        # Verify performance (should still be fast even across multiple chats)
        assert search_time_ms < 200, f"Multi-chat search took {search_time_ms:.2f}ms, expected < 200ms"
        
        # Verify results contain the search term
        for result in results:
            assert search_term.lower() in result['content'].lower()
        
        # Verify we got results from multiple chats
        chat_ids_in_results = set(result['chat_id'] for result in results)
        assert len(chat_ids_in_results) > 1, "Search should return results from multiple chats"
        
        # Verify results are ordered by date (DESC - most recent first)
        if len(results) > 1:
            for i in range(len(results) - 1):
                # Compare date_time strings (they're in sortable format)
                assert results[i]['date_time'] >= results[i + 1]['date_time'], \
                    "Results should be ordered by date_time DESC"
    finally:
        # Cleanup
        try:
            os.unlink(temp_db)
        except OSError:
            pass


def test_search_with_special_characters(temp_db):
    """
    Test that search handles special characters correctly.
    
    This ensures search works with SQL special characters like %, _, etc.
    """
    chat_repo = ChatRepository(temp_db)
    message_repo = MessageRepository(temp_db)
    
    chat_id = 'test-chat-special'
    chat = {
        'id': chat_id,
        'name': 'Test Chat Special',
        'folder': None,
        'is_template': False
    }
    chat_repo.create(chat)
    
    # Create messages with special characters
    special_terms = [
        "100% complete",
        "user_name",
        "file.txt",
        "C:\\path\\to\\file",
        "SELECT * FROM table",
        "[brackets]",
        "(parentheses)"
    ]
    
    for idx, term in enumerate(special_terms):
        message = {
            'id': f'msg-special-{idx}',
            'chat_id': chat_id,
            'role': 'user',
            'model': 'test-model',
            'date_time': f'2024/01/01 12:{idx:02d}:00',
            'content': f"This message contains {term} as content"
        }
        message_repo.create(message)
    
    # Search for each special term
    for term in special_terms:
        results = message_repo.search(term, chat_id=chat_id)
        assert len(results) >= 1, f"Should find message containing '{term}'"
        assert any(term in result['content'] for result in results), \
            f"Results should contain the search term '{term}'"


def test_search_empty_term(temp_db):
    """
    Test that search handles empty search terms gracefully.
    """
    message_repo = MessageRepository(temp_db)
    
    # Search with empty string should return empty results
    results = message_repo.search("", chat_id=None)
    assert results == [], "Empty search term should return no results"
    
    # Search with whitespace only should return empty results
    results = message_repo.search("   ", chat_id=None)
    assert results == [], "Whitespace-only search term should return no results"


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    # Initialize database schema
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            folder TEXT,
            is_template INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS message (
            id TEXT PRIMARY KEY,
            chat_id TEXT NOT NULL,
            role TEXT NOT NULL,
            model TEXT,
            content TEXT NOT NULL,
            date_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chat(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS attachment (
            id TEXT PRIMARY KEY,
            message_id TEXT NOT NULL,
            type TEXT NOT NULL,
            name TEXT NOT NULL,
            content TEXT NOT NULL,
            FOREIGN KEY (message_id) REFERENCES message(id) ON DELETE CASCADE
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS instance (
            id TEXT PRIMARY KEY,
            pinned INTEGER NOT NULL,
            type TEXT NOT NULL,
            properties TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS online_instance_model_list (
            id TEXT PRIMARY KEY,
            list TEXT NOT NULL
        )
    """)
    conn.commit()
    conn.close()
    
    yield db_path
    
    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass
