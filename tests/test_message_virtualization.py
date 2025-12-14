"""
Tests for message virtualization functionality.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestMessageVirtualizationManager(unittest.TestCase):
    """Test the MessageVirtualizationManager class."""
    
    def setUp(self):
        """Set up test fixtures."""
        # Mock GTK imports
        self.gtk_mock = MagicMock()
        self.glib_mock = MagicMock()
        
        sys.modules['gi'] = MagicMock()
        sys.modules['gi.repository'] = MagicMock()
        sys.modules['gi.repository.Gtk'] = self.gtk_mock
        sys.modules['gi.repository.GLib'] = self.glib_mock
    
    def test_manager_can_be_imported(self):
        """Test that the MessageVirtualizationManager can be imported."""
        from utils.message_virtualization import MessageVirtualizationManager
        self.assertIsNotNone(MessageVirtualizationManager)
    
    def test_manager_initialization(self):
        """Test that the manager initializes correctly."""
        from utils.message_virtualization import MessageVirtualizationManager
        
        scrolled_window = Mock()
        container = Mock()
        vadjustment = Mock()
        scrolled_window.get_vadjustment.return_value = vadjustment
        
        manager = MessageVirtualizationManager(scrolled_window, container)
        
        self.assertIsNotNone(manager)
        self.assertTrue(manager.enabled)
        self.assertEqual(manager.scrolled_window, scrolled_window)
        self.assertEqual(manager.container, container)
    
    def test_manager_has_buffer_size_constant(self):
        """Test that the manager has a BUFFER_SIZE constant."""
        from utils.message_virtualization import MessageVirtualizationManager
        
        self.assertTrue(hasattr(MessageVirtualizationManager, 'BUFFER_SIZE'))
        self.assertIsInstance(MessageVirtualizationManager.BUFFER_SIZE, int)
        self.assertGreater(MessageVirtualizationManager.BUFFER_SIZE, 0)
    
    def test_manager_has_min_messages_constant(self):
        """Test that the manager has a MIN_MESSAGES_FOR_VIRTUALIZATION constant."""
        from utils.message_virtualization import MessageVirtualizationManager
        
        self.assertTrue(hasattr(MessageVirtualizationManager, 'MIN_MESSAGES_FOR_VIRTUALIZATION'))
        self.assertIsInstance(MessageVirtualizationManager.MIN_MESSAGES_FOR_VIRTUALIZATION, int)
        self.assertGreater(MessageVirtualizationManager.MIN_MESSAGES_FOR_VIRTUALIZATION, 0)
    
    def test_manager_enable_disable(self):
        """Test that the manager can be enabled and disabled."""
        from utils.message_virtualization import MessageVirtualizationManager
        
        scrolled_window = Mock()
        container = Mock()
        vadjustment = Mock()
        scrolled_window.get_vadjustment.return_value = vadjustment
        
        # Mock container to be iterable
        container.__iter__ = Mock(return_value=iter([]))
        
        manager = MessageVirtualizationManager(scrolled_window, container)
        
        # Test disable
        manager.disable()
        self.assertFalse(manager.enabled)
        
        # Test enable
        manager.enable()
        self.assertTrue(manager.enabled)
    
    def test_manager_cleanup(self):
        """Test that the manager cleans up resources."""
        from utils.message_virtualization import MessageVirtualizationManager
        
        scrolled_window = Mock()
        container = Mock()
        vadjustment = Mock()
        scrolled_window.get_vadjustment.return_value = vadjustment
        
        manager = MessageVirtualizationManager(scrolled_window, container)
        
        # Should not raise an exception
        manager.cleanup()
    
    def test_manager_has_required_methods(self):
        """Test that the manager has all required methods."""
        from utils.message_virtualization import MessageVirtualizationManager
        
        required_methods = [
            'enable',
            'disable',
            'update_now',
            'on_messages_loaded',
            'cleanup'
        ]
        
        for method_name in required_methods:
            self.assertTrue(
                hasattr(MessageVirtualizationManager, method_name),
                f"MessageVirtualizationManager should have method '{method_name}'"
            )


if __name__ == '__main__':
    unittest.main()
