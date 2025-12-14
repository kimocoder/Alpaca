"""
Integration tests for token counting in Chat class.
"""

import pytest
from src.services.token_counter import count_chat_tokens, get_token_stats


class MockMessage:
    """Mock message object for testing."""
    
    def __init__(self, content):
        self.content = content
    
    def get_content(self):
        return self.content


class MockChat:
    """Mock chat object that mimics the Chat class structure."""
    
    def __init__(self, messages):
        self.container = messages
    
    def get_token_count(self):
        """Mimic the Chat.get_token_count method."""
        return count_chat_tokens(self)
    
    def get_token_stats(self):
        """Mimic the Chat.get_token_stats method."""
        return get_token_stats(self)


class TestChatTokenIntegration:
    """Test token counting integration with Chat class."""
    
    def test_chat_get_token_count_empty(self):
        """Test get_token_count on empty chat."""
        chat = MockChat([])
        assert chat.get_token_count() == 0
    
    def test_chat_get_token_count_with_messages(self):
        """Test get_token_count with messages."""
        messages = [
            MockMessage("Hello, how are you?"),
            MockMessage("I'm doing great, thanks for asking!"),
            MockMessage("That's wonderful to hear.")
        ]
        chat = MockChat(messages)
        token_count = chat.get_token_count()
        
        assert token_count > 0
        # Rough estimate: ~60 characters total / 4 = ~15 tokens
        assert token_count >= 10
        assert token_count <= 30
    
    def test_chat_get_token_stats_empty(self):
        """Test get_token_stats on empty chat."""
        chat = MockChat([])
        stats = chat.get_token_stats()
        
        assert stats['total_tokens'] == 0
        assert stats['message_count'] == 0
        assert stats['avg_tokens_per_message'] == 0
    
    def test_chat_get_token_stats_with_messages(self):
        """Test get_token_stats with messages."""
        messages = [
            MockMessage("First message here"),
            MockMessage("Second message here"),
            MockMessage("Third message here")
        ]
        chat = MockChat(messages)
        stats = chat.get_token_stats()
        
        assert stats['total_tokens'] > 0
        assert stats['message_count'] == 3
        assert stats['avg_tokens_per_message'] > 0
        
        # Verify average calculation
        expected_avg = stats['total_tokens'] / 3
        assert abs(stats['avg_tokens_per_message'] - expected_avg) < 0.01
    
    def test_chat_token_count_consistency(self):
        """Test that get_token_count and get_token_stats return consistent values."""
        messages = [
            MockMessage("Testing consistency"),
            MockMessage("Between different methods")
        ]
        chat = MockChat(messages)
        
        token_count = chat.get_token_count()
        stats = chat.get_token_stats()
        
        assert token_count == stats['total_tokens']
