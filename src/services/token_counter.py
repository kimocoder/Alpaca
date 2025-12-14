"""
Token counting service for estimating context window usage.

This module provides functionality to estimate token counts for messages
and entire chat conversations. The estimation uses a simple heuristic
based on character count, which provides a reasonable approximation for
most text content.
"""

import re
from typing import List, Optional


def estimate_tokens(text: str) -> int:
    """
    Estimate the number of tokens in a text string.
    
    This uses a simple heuristic: approximately 1 token per 4 characters
    for English text. This is a rough approximation but works reasonably
    well for most use cases without requiring a full tokenizer.
    
    Args:
        text: The text to estimate tokens for
        
    Returns:
        Estimated number of tokens
    """
    if not text:
        return 0
    
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text.strip())
    
    # Check if text is empty after normalization
    if not text:
        return 0
    
    # Basic estimation: ~1 token per 4 characters
    # This is a common approximation for English text
    char_count = len(text)
    token_estimate = max(1, char_count // 4)
    
    return token_estimate


def count_message_tokens(message) -> int:
    """
    Count tokens in a single message.
    
    Args:
        message: A Message widget instance
        
    Returns:
        Estimated token count for the message
    """
    try:
        content = message.get_content()
        return estimate_tokens(content)
    except Exception:
        # If we can't get content, return 0
        return 0


def count_chat_tokens(chat) -> int:
    """
    Count total tokens for all messages in a chat.
    
    This iterates through all messages in the chat container
    and sums up their token counts.
    
    Args:
        chat: A Chat widget instance
        
    Returns:
        Total estimated token count for the chat
    """
    total_tokens = 0
    
    try:
        # Iterate through all messages in the chat container
        for message in list(chat.container):
            total_tokens += count_message_tokens(message)
    except Exception:
        # If something goes wrong, return 0
        return 0
    
    return total_tokens


def get_token_stats(chat) -> dict:
    """
    Get detailed token statistics for a chat.
    
    Args:
        chat: A Chat widget instance
        
    Returns:
        Dictionary containing:
        - total_tokens: Total token count
        - message_count: Number of messages
        - avg_tokens_per_message: Average tokens per message
    """
    total_tokens = 0
    message_count = 0
    
    try:
        for message in list(chat.container):
            tokens = count_message_tokens(message)
            total_tokens += tokens
            message_count += 1
    except Exception:
        pass
    
    avg_tokens = total_tokens / message_count if message_count > 0 else 0
    
    return {
        'total_tokens': total_tokens,
        'message_count': message_count,
        'avg_tokens_per_message': round(avg_tokens, 2)
    }
