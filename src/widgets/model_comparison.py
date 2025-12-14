"""
Model comparison widget for side-by-side response comparison.
Allows users to compare responses from different models.
"""

import gi
gi.require_version('Gtk', '4.0')
gi.require_version('Adw', '1')
from gi.repository import Gtk, Adw


class ModelComparisonDialog(Adw.Dialog):
    """
    Dialog for comparing responses from multiple models side-by-side.
    
    This widget allows users to send the same prompt to multiple models
    and view their responses in a side-by-side comparison view.
    """
    
    def __init__(self, **kwargs):
        """Initialize the model comparison dialog."""
        super().__init__(**kwargs)
        
        # Set dialog properties
        self.set_title("Model Comparison")
        
        # Create main content
        self._build_ui()
    
    def _build_ui(self):
        """Build the dialog UI."""
        # Create a box to hold the comparison view
        content_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        content_box.set_margin_top(12)
        content_box.set_margin_bottom(12)
        content_box.set_margin_start(12)
        content_box.set_margin_end(12)
        
        # Add a label
        label = Gtk.Label(label="Model Comparison")
        label.add_css_class("title-2")
        content_box.append(label)
        
        # Create scrolled window for comparison content
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_vexpand(True)
        scrolled.set_min_content_height(400)
        scrolled.set_min_content_width(600)
        
        # Create comparison grid
        self.comparison_grid = Gtk.Grid()
        self.comparison_grid.set_column_spacing(12)
        self.comparison_grid.set_row_spacing(12)
        scrolled.set_child(self.comparison_grid)
        
        content_box.append(scrolled)
        
        # Set the content
        self.set_child(content_box)
    
    def add_model_response(self, model_name: str, response: str):
        """
        Add a model response to the comparison view.
        
        Args:
            model_name: Name of the model
            response: The model's response text
        """
        # Get current column count
        column = self.comparison_grid.get_child_at(0, 0)
        col_index = 0 if column is None else len([c for c in self.comparison_grid])
        
        # Create model label
        model_label = Gtk.Label(label=model_name)
        model_label.add_css_class("title-3")
        self.comparison_grid.attach(model_label, col_index, 0, 1, 1)
        
        # Create response text view
        text_view = Gtk.TextView()
        text_view.set_editable(False)
        text_view.set_wrap_mode(Gtk.WrapMode.WORD)
        text_view.get_buffer().set_text(response)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_child(text_view)
        scrolled.set_vexpand(True)
        
        self.comparison_grid.attach(scrolled, col_index, 1, 1, 1)
    
    def clear_comparison(self):
        """Clear all model responses from the comparison view."""
        # Remove all children from the grid
        child = self.comparison_grid.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            self.comparison_grid.remove(child)
            child = next_child
