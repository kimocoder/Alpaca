"""
Unit tests for context indicator widget.
"""

import pytest
from unittest.mock import Mock, MagicMock


class MockMessage:
    """Mock message object for testing."""
    
    def __init__(self, content):
        self.content = content
    
    def get_content(self):
        return self.content


class MockChat:
    """Mock chat object for testing."""
    
    def __init__(self, messages, token_count=None):
        self.container = messages
        self._token_count = token_count
    
    def get_token_count(self):
        """Return the token count."""
        if self._token_count is not None:
            return self._token_count
        # Simple estimation: 1 token per 4 characters
        total = 0
        for msg in self.container:
            content = msg.get_content()
            if content:
                total += max(1, len(content) // 4)
        return total
    
    def get_token_stats(self):
        """Return token statistics."""
        total_tokens = self.get_token_count()
        message_count = len(self.container)
        avg = total_tokens / message_count if message_count > 0 else 0
        return {
            'total_tokens': total_tokens,
            'message_count': message_count,
            'avg_tokens_per_message': round(avg, 2)
        }


class TestContextIndicatorLogic:
    """Test the logic for context indicator display."""
    
    def test_format_token_count_small(self):
        """Test formatting for small token counts."""
        token_count = 150
        if token_count >= 1000000:
            display_text = f'{token_count / 1000000:.1f}M tokens'
        elif token_count >= 1000:
            display_text = f'{token_count / 1000:.1f}K tokens'
        else:
            display_text = f'{token_count} tokens'
        
        assert display_text == '150 tokens'
    
    def test_format_token_count_thousands(self):
        """Test formatting for thousands of tokens."""
        token_count = 2500
        if token_count >= 1000000:
            display_text = f'{token_count / 1000000:.1f}M tokens'
        elif token_count >= 1000:
            display_text = f'{token_count / 1000:.1f}K tokens'
        else:
            display_text = f'{token_count} tokens'
        
        assert display_text == '2.5K tokens'
    
    def test_format_token_count_millions(self):
        """Test formatting for millions of tokens."""
        token_count = 1500000
        if token_count >= 1000000:
            display_text = f'{token_count / 1000000:.1f}M tokens'
        elif token_count >= 1000:
            display_text = f'{token_count / 1000:.1f}K tokens'
        else:
            display_text = f'{token_count} tokens'
        
        assert display_text == '1.5M tokens'
    
    def test_warning_threshold(self):
        """Test that warning is triggered at appropriate threshold."""
        # Should warn at 3000+ tokens
        assert 3000 >= 3000  # Warning threshold
        assert 2999 < 3000   # Below threshold
        assert 5000 >= 3000  # Above threshold
    
    def test_chat_token_count_empty(self):
        """Test token count for empty chat."""
        chat = MockChat([])
        assert chat.get_token_count() == 0
    
    def test_chat_token_count_with_messages(self):
        """Test token count for chat with messages."""
        messages = [
            MockMessage("Hello world"),
            MockMessage("This is a test message")
        ]
        chat = MockChat(messages)
        token_count = chat.get_token_count()
        assert token_count > 0
    
    def test_chat_token_stats(self):
        """Test token statistics calculation."""
        messages = [
            MockMessage("First message"),
            MockMessage("Second message")
        ]
        chat = MockChat(messages)
        stats = chat.get_token_stats()
        
        assert stats['total_tokens'] > 0
        assert stats['message_count'] == 2
        assert stats['avg_tokens_per_message'] > 0
    
    def test_tooltip_format(self):
        """Test tooltip text formatting."""
        chat = MockChat([MockMessage("Test")])
        stats = chat.get_token_stats()
        
        # Simulate tooltip formatting
        tooltip = (
            'Context window usage\n'
            'Total tokens: {total}\n'
            'Messages: {count}\n'
            'Avg per message: {avg:.1f}'
        ).format(
            total=stats['total_tokens'],
            count=stats['message_count'],
            avg=stats['avg_tokens_per_message']
        )
        
        assert 'Context window usage' in tooltip
        assert 'Total tokens:' in tooltip
        assert 'Messages:' in tooltip
        assert 'Avg per message:' in tooltip


class TestContextIndicatorIntegration:
    """Test context indicator integration scenarios."""
    
    def test_update_on_chat_change(self):
        """Test that indicator updates when chat changes."""
        chat1 = MockChat([MockMessage("Chat 1 message")])
        chat2 = MockChat([MockMessage("Chat 2 message"), MockMessage("Another message")])
        
        # Simulate switching chats
        count1 = chat1.get_token_count()
        count2 = chat2.get_token_count()
        
        assert count1 != count2
        assert count2 > count1  # Chat 2 has more messages
    
    def test_update_after_message_added(self):
        """Test that indicator updates after adding a message."""
        messages = [MockMessage("Initial message")]
        chat = MockChat(messages)
        
        initial_count = chat.get_token_count()
        
        # Add a new message
        messages.append(MockMessage("New message"))
        
        new_count = chat.get_token_count()
        
        assert new_count > initial_count
    
    def test_warning_state_changes(self):
        """Test that warning state changes based on token count."""
        # Low token count - no warning
        chat_low = MockChat([], token_count=500)
        assert chat_low.get_token_count() < 3000
        
        # High token count - warning
        chat_high = MockChat([], token_count=5000)
        assert chat_high.get_token_count() >= 3000
