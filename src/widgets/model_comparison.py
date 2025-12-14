# model_comparison.py
"""
Handles the model comparison widget for side-by-side response comparison
"""

import gi
from gi.repository import Gtk, Adw, GLib, Gio
import threading
import logging
from ..sql_manager import prettify_model_name

logger = logging.getLogger(__name__)


class ModelComparisonDialog(Adw.Dialog):
    """
    Dialog for comparing responses from multiple models side-by-side.
    
    Allows users to send the same prompt to multiple models and view
    their responses in a side-by-side comparison view.
    """
    __gtype_name__ = 'AlpacaModelComparisonDialog'

    def __init__(self, parent_window):
        """
        Initialize the model comparison dialog.
        
        Args:
            parent_window: The parent AlpacaWindow instance
        """
        super().__init__(
            title=_('Model Comparison'),
            follows_content_size=False
        )
        
        self.parent_window = parent_window
        self.comparison_panels = []
        self.current_prompt = ""
        
        # Create main container
        self.toolbar_view = Adw.ToolbarView()
        
        # Create header bar
        header_bar = Adw.HeaderBar()
        self.toolbar_view.add_top_bar(header_bar)
        
        # Create main content
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0
        )
        
        # Create prompt input section
        prompt_frame = Gtk.Frame(
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12
        )
        
        prompt_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12
        )
        
        prompt_label = Gtk.Label(
            label=_('Prompt'),
            halign=Gtk.Align.START,
            css_classes=['title-4']
        )
        prompt_box.append(prompt_label)
        
        # Create scrolled window for prompt text view
        prompt_scrolled = Gtk.ScrolledWindow(
            min_content_height=100,
            max_content_height=200,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC
        )
        
        self.prompt_textview = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            accepts_tab=False,
            css_classes=['card']
        )
        prompt_scrolled.set_child(self.prompt_textview)
        prompt_box.append(prompt_scrolled)
        
        # Create button box
        button_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            halign=Gtk.Align.END
        )
        
        self.compare_button = Gtk.Button(
            label=_('Compare'),
            css_classes=['suggested-action']
        )
        self.compare_button.connect('clicked', self.on_compare_clicked)
        button_box.append(self.compare_button)
        
        prompt_box.append(button_box)
        prompt_frame.set_child(prompt_box)
        main_box.append(prompt_frame)
        
        # Create model selection section
        model_selection_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_start=12,
            margin_end=12,
            margin_bottom=12,
            homogeneous=True
        )
        
        # Get available models
        from . import models
        available_models = list(models.added.model_selector_model)
        
        if len(available_models) < 2:
            # Show message if not enough models
            no_models_label = Gtk.Label(
                label=_('At least 2 models are required for comparison'),
                css_classes=['dim-label']
            )
            model_selection_box.append(no_models_label)
            self.compare_button.set_sensitive(False)
        else:
            # Create model selectors (up to 4 models)
            self.model_dropdowns = []
            for i in range(min(4, len(available_models))):
                model_box = Gtk.Box(
                    orientation=Gtk.Orientation.VERTICAL,
                    spacing=6
                )
                
                model_label = Gtk.Label(
                    label=_('Model {}').format(i + 1),
                    halign=Gtk.Align.START
                )
                model_box.append(model_label)
                
                dropdown = Gtk.DropDown(
                    model=models.added.model_selector_model,
                    selected=i if i < len(available_models) else 0
                )
                dropdown.set_factory(self._create_model_factory())
                self.model_dropdowns.append(dropdown)
                model_box.append(dropdown)
                
                model_selection_box.append(model_box)
        
        main_box.append(model_selection_box)
        
        # Create comparison results section
        self.results_scrolled = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC,
            min_content_width=800,
            min_content_height=400
        )
        
        self.results_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_start=12,
            margin_end=12,
            margin_top=12,
            margin_bottom=12,
            homogeneous=True
        )
        
        self.results_scrolled.set_child(self.results_box)
        main_box.append(self.results_scrolled)
        
        self.toolbar_view.set_content(main_box)
        self.set_child(self.toolbar_view)
    
    def _create_model_factory(self):
        """Create a factory for rendering model names in dropdowns."""
        factory = Gtk.SignalListItemFactory()
        
        def setup(factory, list_item):
            label = Gtk.Label(
                halign=Gtk.Align.START,
                ellipsize=3  # ELLIPSIZE_END
            )
            list_item.set_child(label)
        
        def bind(factory, list_item):
            label = list_item.get_child()
            model_item = list_item.get_item()
            if model_item and hasattr(model_item, 'model'):
                model_name = prettify_model_name(model_item.model.get_name())
                label.set_text(model_name)
        
        factory.connect('setup', setup)
        factory.connect('bind', bind)
        
        return factory
    
    def on_compare_clicked(self, button):
        """Handle the compare button click."""
        # Get prompt text
        buffer = self.prompt_textview.get_buffer()
        start_iter = buffer.get_start_iter()
        end_iter = buffer.get_end_iter()
        self.current_prompt = buffer.get_text(start_iter, end_iter, False).strip()
        
        if not self.current_prompt:
            from . import dialog
            dialog.show_toast(_('Please enter a prompt'), self.parent_window)
            return
        
        # Clear previous results
        self.results_box.remove_all()
        self.comparison_panels = []
        
        # Disable compare button during generation
        self.compare_button.set_sensitive(False)
        
        # Create comparison panels for each selected model
        for dropdown in self.model_dropdowns:
            model_item = dropdown.get_selected_item()
            if model_item and hasattr(model_item, 'model'):
                panel = self._create_comparison_panel(model_item.model)
                self.comparison_panels.append(panel)
                self.results_box.append(panel['container'])
        
        # Start generation for all models
        for panel in self.comparison_panels:
            threading.Thread(
                target=self._generate_response,
                args=(panel,),
                daemon=True
            ).start()
    
    def _create_comparison_panel(self, model):
        """
        Create a panel for displaying a model's response.
        
        Args:
            model: The model object to generate response from
            
        Returns:
            dict: Panel components including container, textview, and spinner
        """
        panel_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6
        )
        
        # Model name header
        header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6
        )
        
        model_name = prettify_model_name(model.get_name())
        model_label = Gtk.Label(
            label=model_name,
            halign=Gtk.Align.START,
            css_classes=['title-4'],
            ellipsize=3  # ELLIPSIZE_END
        )
        header_box.append(model_label)
        
        spinner = Gtk.Spinner(
            spinning=True,
            halign=Gtk.Align.END,
            hexpand=True
        )
        header_box.append(spinner)
        
        panel_box.append(header_box)
        
        # Response text view
        scrolled = Gtk.ScrolledWindow(
            vexpand=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            vscrollbar_policy=Gtk.PolicyType.AUTOMATIC
        )
        
        textview = Gtk.TextView(
            wrap_mode=Gtk.WrapMode.WORD_CHAR,
            editable=False,
            css_classes=['card'],
            margin_start=6,
            margin_end=6,
            margin_top=6,
            margin_bottom=6
        )
        
        scrolled.set_child(textview)
        panel_box.append(scrolled)
        
        return {
            'container': panel_box,
            'textview': textview,
            'spinner': spinner,
            'model': model,
            'model_label': model_label
        }
    
    def _generate_response(self, panel):
        """
        Generate a response from a model.
        
        Args:
            panel: The panel dict containing UI components and model
        """
        try:
            model = panel['model']
            textview = panel['textview']
            spinner = panel['spinner']
            
            # Get the current instance
            instance = self.parent_window.get_current_instance()
            
            # Prepare messages
            messages = [{
                'role': 'user',
                'content': self.current_prompt
            }]
            
            # Generate response
            response_text = ""
            
            def update_text(text):
                buffer = textview.get_buffer()
                buffer.set_text(text)
            
            # Call the instance's generate method
            if hasattr(instance, 'generate_text'):
                # Use a simplified generation approach
                for chunk in instance.generate_text(
                    model=model.get_name(),
                    messages=messages,
                    stream=True
                ):
                    if chunk:
                        response_text += chunk
                        GLib.idle_add(update_text, response_text)
            else:
                # Fallback: show error message
                response_text = _('Error: Unable to generate response from this model')
                GLib.idle_add(update_text, response_text)
            
            # Stop spinner when done
            GLib.idle_add(spinner.stop)
            GLib.idle_add(spinner.set_visible, False)
            
        except Exception as e:
            logger.error(f"Error generating response for model comparison: {e}")
            error_text = _('Error: {}').format(str(e))
            GLib.idle_add(lambda: panel['textview'].get_buffer().set_text(error_text))
            GLib.idle_add(panel['spinner'].stop)
            GLib.idle_add(panel['spinner'].set_visible, False)
        finally:
            # Re-enable compare button when all panels are done
            self._check_all_complete()
    
    def _check_all_complete(self):
        """Check if all model generations are complete and re-enable button."""
        all_complete = all(
            not panel['spinner'].get_spinning()
            for panel in self.comparison_panels
        )
        
        if all_complete:
            GLib.idle_add(self.compare_button.set_sensitive, True)
