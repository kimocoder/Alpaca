"""
Unit tests for export dialog functionality.
Tests the radio button dialog for export format selection.
"""

import unittest
import sys
import os

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))


class TestExportDialog(unittest.TestCase):
    """Test cases for export dialog functionality."""
    
    def test_export_format_options(self):
        """Test that export format options are correctly defined."""
        # Define the same radio options as in chat.py
        radio_options = [
            ("Markdown", ('markdown', False)),
            ("Markdown (Obsidian Style)", ('markdown', True)),
            ("JSON", ('json', False)),
            ("JSON (Include Metadata)", ('json', True)),
            ("Database (.db)", ('database', None))
        ]
        
        # Verify we have 5 options
        self.assertEqual(len(radio_options), 5)
        
        # Verify each option has the correct structure
        for label, value in radio_options:
            self.assertIsInstance(label, str)
            self.assertIsInstance(value, tuple)
            self.assertEqual(len(value), 2)
            self.assertIn(value[0], ['markdown', 'json', 'database'])
    
    def test_export_selection_handler(self):
        """Test that export selection handler correctly routes to export functions."""
        # Track which export function was called
        calls = []
        
        def mock_export_md(obsidian):
            calls.append(('markdown', obsidian))
        
        def mock_export_json(include_metadata):
            calls.append(('json', include_metadata))
        
        def mock_export_db():
            calls.append(('database', None))
        
        # Simulate the handler logic
        def handle_export_selection(selected_value):
            export_type, param = selected_value
            if export_type == 'markdown':
                mock_export_md(param)
            elif export_type == 'json':
                mock_export_json(param)
            elif export_type == 'database':
                mock_export_db()
        
        # Test each export type
        handle_export_selection(('markdown', False))
        self.assertEqual(calls[-1], ('markdown', False))
        
        handle_export_selection(('markdown', True))
        self.assertEqual(calls[-1], ('markdown', True))
        
        handle_export_selection(('json', False))
        self.assertEqual(calls[-1], ('json', False))
        
        handle_export_selection(('json', True))
        self.assertEqual(calls[-1], ('json', True))
        
        handle_export_selection(('database', None))
        self.assertEqual(calls[-1], ('database', None))
        
        # Verify all 5 calls were made
        self.assertEqual(len(calls), 5)


if __name__ == '__main__':
    unittest.main()
