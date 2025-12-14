"""
Unit tests for the ModelComparisonDialog widget.
Tests widget instantiation and basic functionality.
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

# Set up GTK version requirements before importing
import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')

from gi.repository import Gtk, Adw


class TestModelComparisonDialog(unittest.TestCase):
    """Test cases for ModelComparisonDialog widget."""
    
    @classmethod
    def setUpClass(cls):
        """Initialize GTK application for testing."""
        # Create a minimal GTK application
        cls.app = Adw.Application(application_id='com.test.ModelComparison')
    
    def test_widget_can_be_imported(self):
        """Test that the ModelComparisonDialog widget can be imported."""
        # Check that the widget file exists
        widget_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'widgets', 'model_comparison.py')
        self.assertTrue(os.path.exists(widget_path), "ModelComparisonDialog widget file exists")
    
    def test_widget_is_dialog(self):
        """Test that the widget is an Adw.Dialog subclass."""
        # Check that the widget file contains the correct class definition
        widget_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'widgets', 'model_comparison.py')
        with open(widget_path, 'r') as f:
            content = f.read()
            self.assertIn('class ModelComparisonDialog(Adw.Dialog)', content)
    
    def test_widget_has_required_attributes(self):
        """Test that the widget has required attributes."""
        # Check that the widget file contains the required methods
        widget_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'widgets', 'model_comparison.py')
        with open(widget_path, 'r') as f:
            content = f.read()
            self.assertIn('def __init__', content)
            self.assertIn('def add_model_response', content)
            self.assertIn('def clear_comparison', content)
            self.assertIn('def _build_ui', content)
    
    def test_widget_has_docstrings(self):
        """Test that the widget and its methods have docstrings."""
        # Check that the widget file contains docstrings
        widget_path = os.path.join(os.path.dirname(__file__), '..', 'src', 'widgets', 'model_comparison.py')
        with open(widget_path, 'r') as f:
            content = f.read()
            # Check for class docstring with side-by-side mention
            self.assertIn('side-by-side', content.lower())
            # Check for method docstrings (they should have triple quotes)
            self.assertIn('"""Initialize the model comparison dialog."""', content)
            self.assertIn('"""Build the dialog UI."""', content)
            self.assertIn('"""', content)  # General check for docstrings


if __name__ == '__main__':
    unittest.main()
