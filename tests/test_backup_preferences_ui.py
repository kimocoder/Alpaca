"""
Tests for backup preferences UI integration.
"""

import unittest
import os
import tempfile
import shutil
from unittest.mock import Mock, patch, MagicMock


class TestBackupPreferencesUI(unittest.TestCase):
    """Test backup preferences UI functionality."""
    
    def setUp(self):
        """Set up test environment."""
        self.test_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.test_dir, "test.db")
        
    def tearDown(self):
        """Clean up test environment."""
        if os.path.exists(self.test_dir):
            shutil.rmtree(self.test_dir)
    
    def test_backup_settings_exist_in_schema(self):
        """Test that backup settings are defined in GSettings schema."""
        # Read the schema file
        schema_path = "data/com.jeffser.Alpaca.gschema.xml"
        
        with open(schema_path, 'r') as f:
            schema_content = f.read()
        
        # Check that backup settings are present
        self.assertIn('backup-auto-enabled', schema_content)
        self.assertIn('backup-interval-hours', schema_content)
        self.assertIn('backup-path', schema_content)
    
    def test_backup_page_exists_in_blueprint(self):
        """Test that backup page is defined in preferences blueprint."""
        blueprint_path = "src/ui/preferences.blp"
        
        with open(blueprint_path, 'r') as f:
            blueprint_content = f.read()
        
        # Check that backup page and widgets are present
        self.assertIn('backup_page', blueprint_content)
        self.assertIn('backup_auto_enabled_switch', blueprint_content)
        self.assertIn('backup_interval_spin', blueprint_content)
        self.assertIn('backup_path_entry', blueprint_content)
        self.assertIn('manual_backup_button_pressed', blueprint_content)
        self.assertIn('restore_backup_button_pressed', blueprint_content)
        self.assertIn('choose_backup_directory_pressed', blueprint_content)
    
    def test_preferences_has_backup_methods(self):
        """Test that preferences.py has backup-related methods."""
        preferences_path = "src/widgets/preferences.py"
        
        with open(preferences_path, 'r') as f:
            preferences_content = f.read()
        
        # Check that backup methods are present
        self.assertIn('manual_backup_button_pressed', preferences_content)
        self.assertIn('restore_backup_button_pressed', preferences_content)
        self.assertIn('choose_backup_directory_pressed', preferences_content)
        self.assertIn('_setup_auto_backup', preferences_content)
        self.assertIn('_update_last_backup_display', preferences_content)
        self.assertIn('from ..services.backup import BackupService', preferences_content)


if __name__ == '__main__':
    unittest.main()
