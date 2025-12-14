"""
Tests for keyboard navigation utilities.

This module tests the keyboard navigation enhancements for accessibility.
"""

import unittest
from unittest.mock import Mock, MagicMock, patch
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Mock GTK before importing
sys.modules['gi'] = MagicMock()
sys.modules['gi.repository'] = MagicMock()
sys.modules['gi.repository.Gtk'] = MagicMock()
sys.modules['gi.repository.Gdk'] = MagicMock()
sys.modules['gi.repository.GLib'] = MagicMock()
sys.modules['gi.repository.Adw'] = MagicMock()

from utils.keyboard_navigation import (
    make_widget_keyboard_accessible,
    add_focus_css_class,
    make_button_keyboard_accessible,
    make_entry_keyboard_accessible
)


class TestKeyboardNavigationUtilities(unittest.TestCase):
    """Test keyboard navigation utility functions"""
    
    def setUp(self):
        """Set up test fixtures"""
        self.mock_widget = Mock()
        self.mock_widget.set_focusable = Mock()
        self.mock_widget.set_focus_on_click = Mock()
        self.mock_widget.add_controller = Mock()
        self.mock_widget.add_css_class = Mock()
        self.mock_widget.remove_css_class = Mock()
        self.mock_widget.set_tooltip_text = Mock()
    
    def test_make_widget_keyboard_accessible(self):
        """Test making a widget keyboard accessible"""
        make_widget_keyboard_accessible(self.mock_widget)
        
        # Verify widget was made focusable
        self.mock_widget.set_focusable.assert_called_once_with(True)
        self.mock_widget.set_focus_on_click.assert_called_once_with(True)
    
    def test_make_widget_keyboard_accessible_with_custom_params(self):
        """Test making a widget keyboard accessible with custom parameters"""
        make_widget_keyboard_accessible(self.mock_widget, can_focus=False, focus_on_click=False)
        
        # Verify widget was configured with custom parameters
        self.mock_widget.set_focusable.assert_called_once_with(False)
        self.mock_widget.set_focus_on_click.assert_called_once_with(False)
    
    def test_make_widget_keyboard_accessible_none_widget(self):
        """Test that None widget is handled gracefully"""
        # Should not raise an exception
        make_widget_keyboard_accessible(None)
    
    def test_add_focus_css_class(self):
        """Test adding focus CSS class to widget"""
        add_focus_css_class(self.mock_widget, "custom-focus")
        
        # Verify controller was added
        self.mock_widget.add_controller.assert_called_once()
    
    def test_add_focus_css_class_none_widget(self):
        """Test that None widget is handled gracefully"""
        # Should not raise an exception
        add_focus_css_class(None)
    
    def test_make_button_keyboard_accessible(self):
        """Test making a button keyboard accessible"""
        make_button_keyboard_accessible(self.mock_widget, "Test tooltip")
        
        # Verify button was made focusable
        self.mock_widget.set_focusable.assert_called_once_with(True)
        
        # Verify tooltip was set
        self.mock_widget.set_tooltip_text.assert_called_once_with("Test tooltip")
        
        # Verify controller was added for focus styling
        self.mock_widget.add_controller.assert_called()
    
    def test_make_button_keyboard_accessible_without_tooltip(self):
        """Test making a button keyboard accessible without tooltip"""
        make_button_keyboard_accessible(self.mock_widget)
        
        # Verify button was made focusable
        self.mock_widget.set_focusable.assert_called_once_with(True)
        
        # Verify tooltip was not set
        self.mock_widget.set_tooltip_text.assert_not_called()
    
    def test_make_entry_keyboard_accessible(self):
        """Test making an entry keyboard accessible"""
        make_entry_keyboard_accessible(self.mock_widget)
        
        # Verify entry was made focusable
        self.mock_widget.set_focusable.assert_called_once_with(True)
        
        # Verify controller was added for focus styling
        self.mock_widget.add_controller.assert_called()
    
    def test_make_entry_keyboard_accessible_with_next_widget(self):
        """Test making an entry keyboard accessible with next widget"""
        mock_next_widget = Mock()
        self.mock_widget.connect = Mock()
        
        make_entry_keyboard_accessible(self.mock_widget, mock_next_widget)
        
        # Verify entry was made focusable
        self.mock_widget.set_focusable.assert_called_once_with(True)
        
        # Verify activate signal was connected
        self.mock_widget.connect.assert_called_once()
        call_args = self.mock_widget.connect.call_args
        self.assertEqual(call_args[0][0], 'activate')


class TestKeyboardNavigationIntegration(unittest.TestCase):
    """Test keyboard navigation integration scenarios"""
    
    def test_multiple_widgets_can_be_made_accessible(self):
        """Test that multiple widgets can be made accessible"""
        widgets = [Mock() for _ in range(5)]
        
        for widget in widgets:
            widget.set_focusable = Mock()
            widget.set_focus_on_click = Mock()
            make_widget_keyboard_accessible(widget)
        
        # Verify all widgets were made focusable
        for widget in widgets:
            widget.set_focusable.assert_called_once_with(True)
    
    def test_focus_css_class_can_be_added_to_multiple_widgets(self):
        """Test that focus CSS class can be added to multiple widgets"""
        widgets = [Mock() for _ in range(3)]
        
        for widget in widgets:
            widget.add_controller = Mock()
            add_focus_css_class(widget)
        
        # Verify controllers were added to all widgets
        for widget in widgets:
            widget.add_controller.assert_called_once()


if __name__ == '__main__':
    unittest.main()
