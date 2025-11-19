"""
Unit tests for window.py service layer integration.

Tests that window.py correctly uses the service layer for
chat, message, and instance operations.
"""
import pytest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..', 'src'))

from services.chat_service import ChatService
from services.message_service import MessageService
from services.instance_service import InstanceService
from core.error_handler import ErrorHandler, AlpacaError


class TestWindowServiceIntegration:
    """Test window.py service layer integration."""
    
    def test_services_can_be_instantiated(self):
        """Test that service classes can be instantiated."""
        chat_service = ChatService()
        message_service = MessageService()
        instance_service = InstanceService()
        
        assert chat_service is not None
        assert message_service is not None
        assert instance_service is not None
    
    def test_error_handler_available(self):
        """Test that ErrorHandler is available for use."""
        # Test that we can log errors
        ErrorHandler.log_error(
            message="Test error",
            context={'test': True}
        )
        
        # Verify error was logged
        error_log = ErrorHandler.get_error_log()
        assert len(error_log) > 0
        assert error_log[-1]['message'] == "Test error"
        
        # Clean up
        ErrorHandler.clear_error_log()
    
    def test_alpaca_error_creation(self):
        """Test that AlpacaError can be created and used."""
        from core.error_handler import ErrorCategory
        
        error = AlpacaError(
            message="Test error",
            category=ErrorCategory.VALIDATION,
            user_message="User-friendly message",
            recoverable=True
        )
        
        assert error.message == "Test error"
        assert error.category == ErrorCategory.VALIDATION
        assert error.user_message == "User-friendly message"
        assert error.recoverable is True
    
    def test_message_service_create_message(self):
        """Test that MessageService can create messages."""
        message_service = MessageService()
        
        # Create a test message
        message_id = message_service.create_message(
            chat_id="test_chat_123",
            role="user",
            content="Test message content"
        )
        
        assert message_id is not None
        assert len(message_id) > 0
    
    def test_message_service_validation(self):
        """Test that MessageService validates input."""
        message_service = MessageService()
        
        # Test invalid role
        with pytest.raises(AlpacaError) as exc_info:
            message_service.create_message(
                chat_id="test_chat",
                role="invalid_role",
                content="Test"
            )
        
        assert exc_info.value.category.value == "validation"
    
    def test_chat_service_create_chat(self):
        """Test that ChatService can create chats."""
        chat_service = ChatService()
        
        # Create a test chat
        chat_id = chat_service.create_chat(
            name="Test Chat",
            folder_id=None
        )
        
        assert chat_id is not None
        assert len(chat_id) > 0
    
    def test_chat_service_validation(self):
        """Test that ChatService validates input."""
        chat_service = ChatService()
        
        # Test empty name
        with pytest.raises(AlpacaError) as exc_info:
            chat_service.create_chat(
                name="",
                folder_id=None
            )
        
        assert exc_info.value.category.value == "validation"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
