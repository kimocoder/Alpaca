# prompt_library.py
"""
Prompt Library widget for viewing, managing, and using saved prompts
"""

import gi
from gi.repository import Gtk, Adw, GLib
import logging
import threading
from datetime import datetime
from typing import Optional

from ..sql_manager import Instance as SQL, format_datetime

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path='/com/jeffser/Alpaca/widgets/prompt_library/prompt_library.ui')
class PromptLibrary(Adw.Dialog):
    __gtype_name__ = 'AlpacaPromptLibrary'

    prompts_stack = Gtk.Template.Child()
    prompts_listbox = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    category_dropdown = Gtk.Template.Child()
    category_box = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._current_prompts = []
        self._all_prompts = []
        self._categories = []
        
        # Initialize category dropdown
        self._setup_category_dropdown()
        
        # Load prompts when dialog opens
        GLib.idle_add(self._load_prompts)

    def _setup_category_dropdown(self):
        """Setup the category dropdown with initial values"""
        # Create string list for categories
        self._category_model = Gtk.StringList()
        self._category_model.append(_("All Categories"))
        self.category_dropdown.set_model(self._category_model)
        self.category_dropdown.set_selected(0)

    @Gtk.Template.Callback()
    def on_close(self, button=None):
        """Close the dialog"""
        self.close()

    @Gtk.Template.Callback()
    def on_add_prompt(self, button=None):
        """Show dialog to add a new prompt"""
        from . import dialog
        
        options = {
            _('Cancel'): {},
            _('Save'): {
                'appearance': 'suggested',
                'callback': lambda name, content, category: self._save_new_prompt(name, content, category),
                'default': True
            }
        }
        
        d = dialog.Entry(
            _('Add Prompt'),
            _('Create a new prompt for your library'),
            list(options.keys())[0],
            options,
            {'placeholder': _('Prompt Name'), 'text': ''}
        )
        
        # Add content text view
        content_frame = Gtk.Frame()
        content_frame.set_margin_top(12)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(150)
        scrolled.set_hscrollbar_policy(Gtk.PolicyType.NEVER)
        
        content_textview = Gtk.TextView()
        content_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        content_textview.set_top_margin(6)
        content_textview.set_bottom_margin(6)
        content_textview.set_left_margin(6)
        content_textview.set_right_margin(6)
        content_textview.get_buffer().set_text(_("Enter your prompt here..."))
        
        scrolled.set_child(content_textview)
        content_frame.set_child(scrolled)
        d.container.append(content_frame)
        
        # Add category entry
        category_entry = Gtk.Entry()
        category_entry.set_placeholder_text(_("Category (optional)"))
        category_entry.set_margin_top(12)
        d.container.append(category_entry)
        
        # Store references for callback
        d.content_textview = content_textview
        d.category_entry = category_entry
        
        # Override callback to include content and category
        original_callback = options[_('Save')]['callback']
        def enhanced_callback(name):
            buffer = d.content_textview.get_buffer()
            content = buffer.get_text(
                buffer.get_start_iter(),
                buffer.get_end_iter(),
                False
            )
            category = d.category_entry.get_text().strip() or None
            original_callback(name, content, category)
        
        options[_('Save')]['callback'] = enhanced_callback
        
        d.show(self.get_root())

    def _save_new_prompt(self, name: str, content: str, category: Optional[str]):
        """Save a new prompt to the database"""
        if not name.strip() or not content.strip():
            logger.warning("Cannot save prompt with empty name or content")
            return
        
        try:
            prompt_id = SQL.save_prompt(name.strip(), content.strip(), category)
            logger.info(f"Saved new prompt: {prompt_id}")
            
            # Reload prompts
            self._load_prompts()
            
        except Exception as e:
            logger.error(f"Error saving prompt: {e}")
            GLib.idle_add(self.prompts_stack.set_visible_child_name, 'error')

    @Gtk.Template.Callback()
    def on_refresh(self, button=None):
        """Refresh the prompts list"""
        self._load_prompts()

    @Gtk.Template.Callback()
    def on_search(self, entry=None):
        """Filter prompts based on search query"""
        query = self.search_entry.get_text().lower()
        
        if not query:
            self._display_prompts(self._current_prompts)
            return
        
        # Filter prompts by name or content
        filtered = [
            p for p in self._current_prompts
            if query in p[1].lower() or query in p[2].lower()
        ]
        
        self._display_prompts(filtered, searching=True)

    @Gtk.Template.Callback()
    def on_category_changed(self, dropdown, param):
        """Handle category selection change"""
        selected_index = dropdown.get_selected()
        
        if selected_index == 0:
            # "All Categories" selected
            self._current_prompts = self._all_prompts
        else:
            # Specific category selected
            category = self._categories[selected_index - 1]
            self._current_prompts = [
                p for p in self._all_prompts
                if p[3] == category
            ]
        
        # Apply current search filter if any
        query = self.search_entry.get_text()
        if query:
            self.on_search()
        else:
            self._display_prompts(self._current_prompts)

    def _load_prompts(self) -> bool:
        """Load prompts in a background thread"""
        # Show loading state
        self.prompts_stack.set_visible_child_name('loading')
        
        # Run loading in background thread
        threading.Thread(
            target=self._load_prompts_thread,
            daemon=True
        ).start()
        
        return False

    def _load_prompts_thread(self):
        """Background thread for loading prompts"""
        try:
            # Get all prompts from database
            prompts = SQL.get_prompts()
            
            # Get all categories
            categories = SQL.get_prompt_categories()
            
            # Update UI on main thread
            GLib.idle_add(self._update_categories, categories)
            GLib.idle_add(self._display_prompts, prompts)
            
        except Exception as e:
            logger.error(f"Error loading prompts: {e}")
            GLib.idle_add(self.prompts_stack.set_visible_child_name, 'error')

    def _update_categories(self, categories: list) -> bool:
        """Update the category dropdown with available categories"""
        self._categories = categories
        
        # Clear existing categories (except "All Categories")
        while self._category_model.get_n_items() > 1:
            self._category_model.remove(1)
        
        # Add new categories
        for category in categories:
            self._category_model.append(category)
        
        # Show/hide category box based on whether there are categories
        self.category_box.set_visible(len(categories) > 0)
        
        return False

    def _display_prompts(self, prompts: list, searching: bool = False) -> bool:
        """Display prompts in the UI"""
        # Clear existing prompts
        self.prompts_listbox.remove_all()
        
        # Store prompts
        if not searching:
            self._all_prompts = prompts
            self._current_prompts = prompts
        
        if not prompts:
            if searching:
                self.prompts_stack.set_visible_child_name('no-results')
            else:
                self.prompts_stack.set_visible_child_name('empty')
            return False
        
        # Add prompt rows
        for prompt in prompts:
            row = self._create_prompt_row(prompt)
            self.prompts_listbox.append(row)
        
        self.prompts_stack.set_visible_child_name('prompts')
        return False

    def _create_prompt_row(self, prompt: tuple) -> Gtk.ListBoxRow:
        """Create a list box row for a prompt
        
        prompt tuple format:
        (id, name, content, category, created_at)
        """
        row = Gtk.ListBoxRow()
        row.prompt_data = {
            'id': prompt[0],
            'name': prompt[1],
            'content': prompt[2],
            'category': prompt[3],
            'created_at': prompt[4]
        }
        
        # Main container
        main_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12
        )
        
        # Content box (left side)
        content_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            hexpand=True
        )
        
        # Header with prompt name and category
        header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )
        
        # Prompt name
        name_label = Gtk.Label(
            label=row.prompt_data['name'],
            xalign=0,
            hexpand=True,
            ellipsize=3,  # ELLIPSIZE_END
            max_width_chars=50
        )
        name_label.add_css_class('heading')
        header_box.append(name_label)
        
        # Category badge (if exists)
        if row.prompt_data['category']:
            category_label = Gtk.Label(
                label=row.prompt_data['category'],
                xalign=1
            )
            category_label.add_css_class('caption')
            category_label.add_css_class('dim-label')
            category_label.add_css_class('accent')
            header_box.append(category_label)
        
        content_box.append(header_box)
        
        # Prompt content preview
        content = row.prompt_data['content']
        preview_label = Gtk.Label(
            label=content,
            xalign=0,
            wrap=True,
            wrap_mode=2,  # WRAP_WORD
            max_width_chars=70,
            lines=3,
            ellipsize=3  # ELLIPSIZE_END
        )
        preview_label.add_css_class('body')
        content_box.append(preview_label)
        
        # Created date
        try:
            created_dt = datetime.strptime(
                row.prompt_data['created_at'] + (":00" if row.prompt_data['created_at'].count(":") == 1 else ""),
                '%Y/%m/%d %H:%M:%S'
            )
            date_str = format_datetime(created_dt)
        except Exception as e:
            logger.warning(f"Error parsing datetime: {e}")
            date_str = row.prompt_data['created_at']
        
        date_label = Gtk.Label(
            label=_("Created: {}").format(date_str),
            xalign=0
        )
        date_label.add_css_class('caption')
        date_label.add_css_class('dim-label')
        content_box.append(date_label)
        
        main_box.append(content_box)
        
        # Action buttons (right side)
        button_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            valign=Gtk.Align.CENTER
        )
        
        # Use button
        use_button = Gtk.Button(
            icon_name='document-edit-symbolic',
            valign=Gtk.Align.CENTER,
            tooltip_text=_('Use this prompt')
        )
        use_button.add_css_class('flat')
        use_button.add_css_class('circular')
        use_button.connect('clicked', self._on_use_prompt, row)
        button_box.append(use_button)
        
        # Edit button
        edit_button = Gtk.Button(
            icon_name='document-properties-symbolic',
            valign=Gtk.Align.CENTER,
            tooltip_text=_('Edit prompt')
        )
        edit_button.add_css_class('flat')
        edit_button.add_css_class('circular')
        edit_button.connect('clicked', self._on_edit_prompt, row)
        button_box.append(edit_button)
        
        # Delete button
        delete_button = Gtk.Button(
            icon_name='user-trash-symbolic',
            valign=Gtk.Align.CENTER,
            tooltip_text=_('Delete prompt')
        )
        delete_button.add_css_class('flat')
        delete_button.add_css_class('circular')
        delete_button.connect('clicked', self._on_delete_prompt, row)
        button_box.append(delete_button)
        
        main_box.append(button_box)
        
        row.set_child(main_box)
        return row

    def _on_use_prompt(self, button, row):
        """Insert the prompt into the message input"""
        if not hasattr(row, 'prompt_data'):
            return
        
        try:
            window = self.get_root()
            if not window:
                return
            
            # Get the message input buffer
            buffer = window.global_footer.get_buffer()
            
            # Insert the prompt content
            content = row.prompt_data['content']
            buffer.set_text(content, len(content.encode('utf-8')))
            
            # Focus the input
            window.global_footer.message_text_view.grab_focus()
            
            # Close the dialog
            self.close()
            
            logger.info(f"Inserted prompt: {row.prompt_data['name']}")
            
        except Exception as e:
            logger.error(f"Error using prompt: {e}")

    def _on_edit_prompt(self, button, row):
        """Show dialog to edit an existing prompt"""
        if not hasattr(row, 'prompt_data'):
            return
        
        from . import dialog
        
        prompt_data = row.prompt_data
        
        options = {
            _('Cancel'): {},
            _('Save'): {
                'appearance': 'suggested',
                'callback': lambda name, content, category: self._update_prompt(
                    prompt_data['id'], name, content, category
                ),
                'default': True
            }
        }
        
        d = dialog.Entry(
            _('Edit Prompt'),
            _("Editing '{}'").format(prompt_data['name']),
            list(options.keys())[0],
            options,
            {'placeholder': _('Prompt Name'), 'text': prompt_data['name']}
        )
        
        # Add content text view
        content_frame = Gtk.Frame()
        content_frame.set_margin_top(12)
        
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_min_content_height(150)
        scrolled.set_hscrollbar_policy(Gtk.PolicyType.NEVER)
        
        content_textview = Gtk.TextView()
        content_textview.set_wrap_mode(Gtk.WrapMode.WORD)
        content_textview.set_top_margin(6)
        content_textview.set_bottom_margin(6)
        content_textview.set_left_margin(6)
        content_textview.set_right_margin(6)
        content_textview.get_buffer().set_text(prompt_data['content'])
        
        scrolled.set_child(content_textview)
        content_frame.set_child(scrolled)
        d.container.append(content_frame)
        
        # Add category entry
        category_entry = Gtk.Entry()
        category_entry.set_placeholder_text(_("Category (optional)"))
        category_entry.set_text(prompt_data['category'] or '')
        category_entry.set_margin_top(12)
        d.container.append(category_entry)
        
        # Store references for callback
        d.content_textview = content_textview
        d.category_entry = category_entry
        
        # Override callback to include content and category
        original_callback = options[_('Save')]['callback']
        def enhanced_callback(name):
            buffer = d.content_textview.get_buffer()
            content = buffer.get_text(
                buffer.get_start_iter(),
                buffer.get_end_iter(),
                False
            )
            category = d.category_entry.get_text().strip() or None
            original_callback(name, content, category)
        
        options[_('Save')]['callback'] = enhanced_callback
        
        d.show(self.get_root())

    def _update_prompt(self, prompt_id: str, name: str, content: str, category: Optional[str]):
        """Update an existing prompt in the database"""
        if not name.strip() or not content.strip():
            logger.warning("Cannot update prompt with empty name or content")
            return
        
        try:
            success = SQL.update_prompt(
                prompt_id,
                name.strip(),
                content.strip(),
                category
            )
            
            if success:
                logger.info(f"Updated prompt: {prompt_id}")
                # Reload prompts
                self._load_prompts()
            else:
                logger.error(f"Failed to update prompt: {prompt_id}")
                
        except Exception as e:
            logger.error(f"Error updating prompt: {e}")
            GLib.idle_add(self.prompts_stack.set_visible_child_name, 'error')

    def _on_delete_prompt(self, button, row):
        """Handle deleting a prompt"""
        if not hasattr(row, 'prompt_data'):
            return
        
        from . import dialog
        
        prompt_data = row.prompt_data
        
        dialog.simple(
            parent=self.get_root(),
            heading=_('Delete Prompt'),
            body=_("Are you sure you want to delete '{}'?").format(prompt_data['name']),
            callback=lambda: self._delete_prompt(prompt_data['id']),
            button_name=_('Delete'),
            button_appearance='destructive'
        )

    def _delete_prompt(self, prompt_id: str):
        """Delete a prompt from the database"""
        try:
            success = SQL.delete_prompt(prompt_id)
            
            if success:
                logger.info(f"Deleted prompt: {prompt_id}")
                # Reload prompts
                self._load_prompts()
            else:
                logger.error(f"Failed to delete prompt: {prompt_id}")
                
        except Exception as e:
            logger.error(f"Error deleting prompt: {e}")
