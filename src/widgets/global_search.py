# global_search.py
"""
Global search widget for searching across all chats
"""

import gi
from gi.repository import Gtk, Adw, GLib
import logging
import threading
from datetime import datetime
from typing import Optional

from ..services.search import SearchService, SearchResult
from ..utils.accessibility import configure_search_accessibility, set_accessible_label
from ..utils import keyboard_navigation

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path='/com/jeffser/Alpaca/widgets/search/global_search.ui')
class GlobalSearch(Adw.Dialog):
    """
    Dialog for searching across all chats.
    
    Provides a search interface to find messages across all conversations,
    with support for date filtering and result navigation.
    """
    __gtype_name__ = 'AlpacaGlobalSearch'

    search_bar = Gtk.Template.Child()
    search_entry = Gtk.Template.Child()
    results_stack = Gtk.Template.Child()
    results_listbox = Gtk.Template.Child()

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.search_service = SearchService()
        self._search_timeout_id = None
        self._current_results = []
        
        # Configure accessibility
        self._setup_accessibility()
        
        # Set up keyboard navigation
        self._setup_keyboard_navigation()
        
        # Focus the search entry when dialog opens
        GLib.idle_add(self.search_entry.grab_focus)
    
    def _setup_accessibility(self):
        """Configure ARIA labels for accessibility"""
        # Search entry
        configure_search_accessibility(
            self.search_entry,
            _("Search messages across all chats"),
            _("Enter text to search through all your conversations")
        )
        
        # Results list
        set_accessible_label(
            self.results_listbox,
            _("Search results")
        )
    
    def _setup_keyboard_navigation(self):
        """Set up keyboard navigation for the search dialog"""
        try:
            # Enhance keyboard navigation for results list
            keyboard_navigation.setup_keyboard_navigation_for_list(self.results_listbox)
            
            # Add Escape key handler to close dialog
            keyboard_navigation.setup_escape_key_handler(self, lambda: self.close())
            
            # Make search entry fully keyboard accessible
            keyboard_navigation.make_entry_keyboard_accessible(self.search_entry)
            keyboard_navigation.add_focus_css_class(self.search_entry)
            
            logger.debug("Keyboard navigation set up for global search dialog")
        except Exception as e:
            logger.warning(f"Error setting up keyboard navigation for global search: {e}")

    @Gtk.Template.Callback()
    def on_close(self, button=None):
        """Close the dialog"""
        self.close()

    @Gtk.Template.Callback()
    def on_search_changed(self, entry):
        """Handle search text changes with debouncing"""
        # Cancel any pending search
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
        
        query = entry.get_text().strip()
        
        if not query:
            # Show empty state if search is cleared
            GLib.idle_add(self.results_stack.set_visible_child_name, 'empty')
            GLib.idle_add(self.results_listbox.remove_all)
            self._current_results = []
            return
        
        # Debounce search - wait 300ms after user stops typing
        self._search_timeout_id = GLib.timeout_add(300, self._perform_search, query)

    @Gtk.Template.Callback()
    def on_search_activate(self, entry):
        """Handle Enter key press in search entry"""
        # Cancel debounce and search immediately
        if self._search_timeout_id:
            GLib.source_remove(self._search_timeout_id)
            self._search_timeout_id = None
        
        query = entry.get_text().strip()
        if query:
            self._perform_search(query)

    def _perform_search(self, query: str) -> bool:
        """Perform the actual search in a background thread"""
        self._search_timeout_id = None
        
        # Show loading state
        GLib.idle_add(self.results_stack.set_visible_child_name, 'loading')
        
        # Run search in background thread
        threading.Thread(
            target=self._search_thread,
            args=(query,),
            daemon=True
        ).start()
        
        return False  # Don't repeat timeout

    def _search_thread(self, query: str):
        """Background thread for searching"""
        try:
            # Perform the search
            results = self.search_service.search_all_chats(query)
            
            # Update UI on main thread
            GLib.idle_add(self._display_results, results, query)
            
        except Exception as e:
            logger.error(f"Error during search: {e}")
            GLib.idle_add(self.results_stack.set_visible_child_name, 'error')

    def _display_results(self, results: list, query: str) -> bool:
        """Display search results in the UI"""
        # Clear existing results
        self.results_listbox.remove_all()
        self._current_results = results
        
        if not results:
            self.results_stack.set_visible_child_name('no-results')
            return False
        
        # Add result rows
        for result in results:
            row = self._create_result_row(result, query)
            self.results_listbox.append(row)
        
        self.results_stack.set_visible_child_name('results')
        return False

    def _create_result_row(self, result: SearchResult, query: str) -> Gtk.ListBoxRow:
        """Create a list box row for a search result"""
        row = Gtk.ListBoxRow()
        row.result = result  # Store result data on the row
        
        # Set accessible label for the row
        accessible_text = _("Search result in {chat}: {preview}").format(
            chat=result.chat_name,
            preview=result.message_preview[:100]
        )
        set_accessible_label(row, accessible_text)
        
        # Main container
        box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            margin_top=12,
            margin_bottom=12,
            margin_start=12,
            margin_end=12
        )
        
        # Header with chat name and timestamp
        header_box = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12
        )
        
        # Chat name
        chat_label = Gtk.Label(
            label=result.chat_name,
            xalign=0,
            hexpand=True,
            ellipsize=3,  # ELLIPSIZE_END
            max_width_chars=40
        )
        chat_label.add_css_class('heading')
        header_box.append(chat_label)
        
        # Timestamp
        time_str = self._format_timestamp(result.timestamp)
        time_label = Gtk.Label(
            label=time_str,
            xalign=1
        )
        time_label.add_css_class('dim-label')
        time_label.add_css_class('caption')
        header_box.append(time_label)
        
        box.append(header_box)
        
        # Message preview with highlighted search term
        preview_label = Gtk.Label(
            label=result.message_preview,
            xalign=0,
            wrap=True,
            wrap_mode=2,  # WRAP_WORD
            max_width_chars=60,
            lines=3,
            ellipsize=3  # ELLIPSIZE_END
        )
        preview_label.add_css_class('body')
        box.append(preview_label)
        
        row.set_child(box)
        return row

    def _format_timestamp(self, timestamp: datetime) -> str:
        """Format timestamp for display"""
        now = datetime.now()
        diff = now - timestamp
        
        if diff.days == 0:
            # Today - show time
            return timestamp.strftime("%H:%M")
        elif diff.days == 1:
            # Yesterday
            return _("Yesterday")
        elif diff.days < 7:
            # This week - show day name
            return timestamp.strftime("%A")
        elif diff.days < 365:
            # This year - show month and day
            return timestamp.strftime("%b %d")
        else:
            # Older - show full date
            return timestamp.strftime("%Y-%m-%d")

    @Gtk.Template.Callback()
    def on_result_activated(self, listbox, row):
        """Handle clicking on a search result"""
        if not hasattr(row, 'result'):
            return
        
        result = row.result
        
        try:
            # Get the main window
            window = self.get_root()
            
            # Navigate to the chat containing the message
            self._navigate_to_message(window, result)
            
            # Close the search dialog
            self.close()
            
        except Exception as e:
            logger.error(f"Error navigating to message: {e}")

    def _navigate_to_message(self, window, result: SearchResult):
        """Navigate to the chat and message"""
        # Find the chat in the chat list
        chat_list_page = window.get_chat_list_page()
        
        # Search through all chat rows to find the matching chat
        target_chat_row = None
        for row in list(chat_list_page.chat_list_box):
            if hasattr(row, 'chat') and row.chat.chat_id == result.chat_id:
                target_chat_row = row
                break
        
        if target_chat_row:
            # Select the chat row to load it
            chat_list_page.chat_list_box.select_row(target_chat_row)
            
            # Wait a moment for the chat to load, then scroll to the message
            GLib.timeout_add(100, self._scroll_to_message, window, result.message_id)
        else:
            logger.warning(f"Could not find chat with ID: {result.chat_id}")

    def _scroll_to_message(self, window, message_id: str) -> bool:
        """Scroll to and highlight the specific message"""
        try:
            current_chat = window.chat_bin.get_child()
            if not current_chat:
                return False
            
            # Find the message widget
            for message in list(current_chat.container):
                if hasattr(message, 'message_id') and message.message_id == message_id:
                    # Scroll to the message
                    message.grab_focus()
                    
                    # Optionally add a temporary highlight effect
                    # This could be done with CSS classes if desired
                    
                    break
            
        except Exception as e:
            logger.error(f"Error scrolling to message: {e}")
        
        return False  # Don't repeat timeout
