"""
Common test fixtures and utilities for Alpaca tests.
"""
import os
import sys
import tempfile
import sqlite3
from pathlib import Path
from typing import Generator, Dict, Any
from unittest.mock import Mock, MagicMock

import pytest
from hypothesis import settings, Verbosity

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))


# Hypothesis configuration
settings.register_profile("default", max_examples=100, verbosity=Verbosity.normal)
settings.register_profile("ci", max_examples=1000, verbosity=Verbosity.verbose)
settings.register_profile("dev", max_examples=10, verbosity=Verbosity.verbose)
settings.load_profile(os.getenv("HYPOTHESIS_PROFILE", "default"))


# ============================================================================
# Database Fixtures
# ============================================================================

@pytest.fixture
def temp_db() -> Generator[str, None, None]:
    """Create a temporary SQLite database for testing."""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.db', delete=False) as f:
        db_path = f.name
    
    yield db_path
    
    # Cleanup
    try:
        os.unlink(db_path)
    except OSError:
        pass


@pytest.fixture
def db_connection(temp_db: str) -> Generator[sqlite3.Connection, None, None]:
    """Create a database connection with schema."""
    conn = sqlite3.connect(temp_db)
    conn.row_factory = sqlite3.Row
    
    # Create basic schema
    conn.execute("""
        CREATE TABLE IF NOT EXISTS chat (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            folder TEXT,
            is_template INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
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
        CREATE TABLE IF NOT EXISTS instance (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            url TEXT NOT NULL,
            type TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    
    conn.commit()
    
    yield conn
    
    conn.close()


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_chat() -> Dict[str, Any]:
    """Create sample chat data."""
    return {
        'id': 'test-chat-001',
        'name': 'Test Chat',
        'folder': None,
        'is_template': False
    }


@pytest.fixture
def sample_message() -> Dict[str, Any]:
    """Create sample message data."""
    return {
        'id': 'test-msg-001',
        'chat_id': 'test-chat-001',
        'role': 'user',
        'model': None,
        'content': 'Hello, this is a test message.'
    }


@pytest.fixture
def sample_instance() -> Dict[str, Any]:
    """Create sample instance data."""
    return {
        'id': 'test-instance-001',
        'name': 'Test Ollama',
        'url': 'http://localhost:11434',
        'type': 'ollama'
    }


# ============================================================================
# Mock Fixtures
# ============================================================================

@pytest.fixture
def mock_gtk_widget() -> Mock:
    """Create a mock GTK widget."""
    widget = MagicMock()
    widget.get_name.return_value = "MockWidget"
    return widget


@pytest.fixture
def mock_subprocess() -> Mock:
    """Create a mock subprocess.Popen object."""
    process = MagicMock()
    process.pid = 12345
    process.returncode = None
    process.poll.return_value = None
    process.wait.return_value = 0
    process.terminate.return_value = None
    process.kill.return_value = None
    return process


@pytest.fixture
def mock_requests_response() -> Mock:
    """Create a mock requests.Response object."""
    response = MagicMock()
    response.status_code = 200
    response.json.return_value = {'status': 'success'}
    response.text = '{"status": "success"}'
    response.ok = True
    return response


# ============================================================================
# Temporary File Fixtures
# ============================================================================

@pytest.fixture
def temp_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def temp_file() -> Generator[Path, None, None]:
    """Create a temporary file for testing."""
    with tempfile.NamedTemporaryFile(mode='w', delete=False) as f:
        temp_path = Path(f.name)
    
    yield temp_path
    
    # Cleanup
    try:
        temp_path.unlink()
    except OSError:
        pass


# ============================================================================
# Test Utilities
# ============================================================================

class TestFixtures:
    """Common test utilities and helpers."""
    
    @staticmethod
    def create_test_chat(
        chat_id: str = "test-chat",
        name: str = "Test Chat",
        folder: str = None
    ) -> Dict[str, Any]:
        """Create a test chat dictionary."""
        return {
            'id': chat_id,
            'name': name,
            'folder': folder,
            'is_template': False
        }
    
    @staticmethod
    def create_test_message(
        message_id: str = "test-msg",
        chat_id: str = "test-chat",
        content: str = "Test message",
        role: str = "user"
    ) -> Dict[str, Any]:
        """Create a test message dictionary."""
        return {
            'id': message_id,
            'chat_id': chat_id,
            'role': role,
            'model': None,
            'content': content
        }
    
    @staticmethod
    def create_test_instance(
        instance_id: str = "test-instance",
        name: str = "Test Instance",
        url: str = "http://localhost:11434"
    ) -> Dict[str, Any]:
        """Create a test instance dictionary."""
        return {
            'id': instance_id,
            'name': name,
            'url': url,
            'type': 'ollama'
        }
    
    @staticmethod
    def mock_ollama_response(
        content: str = "Test response",
        streaming: bool = False
    ) -> Dict[str, Any]:
        """Create a mock Ollama API response."""
        if streaming:
            return {
                'model': 'test-model',
                'created_at': '2024-01-01T00:00:00Z',
                'message': {
                    'role': 'assistant',
                    'content': content
                },
                'done': False
            }
        else:
            return {
                'model': 'test-model',
                'created_at': '2024-01-01T00:00:00Z',
                'message': {
                    'role': 'assistant',
                    'content': content
                },
                'done': True,
                'total_duration': 1000000000,
                'load_duration': 100000000,
                'prompt_eval_count': 10,
                'eval_count': 20
            }


@pytest.fixture
def test_fixtures() -> TestFixtures:
    """Provide access to test utility class."""
    return TestFixtures()


# ============================================================================
# Cleanup Fixtures
# ============================================================================

@pytest.fixture(scope="function", autouse=True)
def cleanup_database_pools():
    """Cleanup database connection pools after each test."""
    yield
    # Close all connection pools to prevent resource warnings
    try:
        from repositories.base_repository import BaseRepository
        BaseRepository.close_all_pools()
    except ImportError:
        pass
