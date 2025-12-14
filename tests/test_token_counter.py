"""
Unit tests for token counting functionality.
"""

import pytest
from src.services.token_counter import estimate_tokens, count_message_tokens, count_chat_tokens, get_token_stats


class TestTokenEstimation:
    """Test basic token estimation functionality."""
    
    def test_estimate_tokens_empty_string(self):
        """Test that empty strings return 0 tokens."""
        assert estimate_tokens("") == 0
        assert estimate_tokens("   ") == 0
    
    def test_estimate_tokens_simple_text(self):
        """Test token estimation for simple text."""
        # "Hello world" is 11 characters, should be ~2-3 tokens
        result = estimate_tokens("Hello world")
        assert result > 0
        assert result < 10  # Reasonable upper bound
    
    def test_estimate_tokens_longer_text(self):
        """Test token estimation for longer text."""
        text = "This is a longer piece of text that should have more tokens."
        result = estimate_tokens(text)
        # 62 characters / 4 = ~15 tokens
        assert result >= 10
        assert result <= 20
    
    def test_estimate_tokens_with_whitespace(self):
        """Test that extra whitespace is normalized."""
        text1 = "Hello    world"
        text2 = "Hello world"
        # Should be similar after whitespace normalization
        assert abs(estimate_tokens(text1) - estimate_tokens(text2)) <= 1
    
    def test_estimate_tokens_code_block(self):
        """Test token estimation for code."""
        code = """
def hello():
    print("Hello, world!")
    return True
"""
        result = estimate_tokens(code)
        assert result > 0


class MockMessage:
    """Mock message object for testing."""
    
    def __init__(self, content):
        self.content = content
    
    def get_content(self):
        return self.content


class MockChat:
    """Mock chat object for testing."""
    
    def __init__(self, messages):
        self.container = messages


class TestMessageTokenCounting:
    """Test token counting for messages."""
    
    def test_count_message_tokens(self):
        """Test counting tokens in a single message."""
        message = MockMessage("This is a test message")
        result = count_message_tokens(message)
        assert result > 0
    
    def test_count_message_tokens_empty(self):
        """Test counting tokens in an empty message."""
        message = MockMessage("")
        result = count_message_tokens(message)
        assert result == 0


class TestChatTokenCounting:
    """Test token counting for entire chats."""
    
    def test_count_chat_tokens_empty(self):
        """Test counting tokens in an empty chat."""
        chat = MockChat([])
        result = count_chat_tokens(chat)
        assert result == 0
    
    def test_count_chat_tokens_single_message(self):
        """Test counting tokens in a chat with one message."""
        messages = [MockMessage("Hello world")]
        chat = MockChat(messages)
        result = count_chat_tokens(chat)
        assert result > 0
    
    def test_count_chat_tokens_multiple_messages(self):
        """Test counting tokens in a chat with multiple messages."""
        messages = [
            MockMessage("First message"),
            MockMessage("Second message"),
            MockMessage("Third message")
        ]
        chat = MockChat(messages)
        result = count_chat_tokens(chat)
        assert result > 0
        # Should be more than a single message
        single_result = count_message_tokens(messages[0])
        assert result > single_result


class TestTokenStats:
    """Test token statistics functionality."""
    
    def test_get_token_stats_empty(self):
        """Test getting stats for an empty chat."""
        chat = MockChat([])
        stats = get_token_stats(chat)
        assert stats['total_tokens'] == 0
        assert stats['message_count'] == 0
        assert stats['avg_tokens_per_message'] == 0
    
    def test_get_token_stats_with_messages(self):
        """Test getting stats for a chat with messages."""
        messages = [
            MockMessage("First message"),
            MockMessage("Second message")
        ]
        chat = MockChat(messages)
        stats = get_token_stats(chat)
        
        assert stats['total_tokens'] > 0
        assert stats['message_count'] == 2
        assert stats['avg_tokens_per_message'] > 0
        assert stats['avg_tokens_per_message'] == stats['total_tokens'] / 2
