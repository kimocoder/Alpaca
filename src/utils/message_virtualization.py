# message_virtualization.py
"""
Message virtualization manager for efficient rendering of large conversations.
Implements virtual scrolling by showing/hiding messages based on viewport visibility.
"""

import gi
from gi.repository import Gtk, GLib
import logging

logger = logging.getLogger(__name__)


class MessageVirtualizationManager:
    """
    Manages message virtualization for a chat container.
    
    This class implements virtual scrolling by:
    - Tracking which messages are visible in the viewport
    - Hiding messages that are far from the viewport
    - Showing messages as they come into view
    - Maintaining a buffer zone around the viewport for smooth scrolling
    """
    
    # Number of messages to keep rendered above/below the viewport
    BUFFER_SIZE = 5
    
    # Minimum number of messages before virtualization kicks in
    MIN_MESSAGES_FOR_VIRTUALIZATION = 20
    
    def __init__(self, scrolled_window: Gtk.ScrolledWindow, container: Gtk.Box):
        """
        Initialize the virtualization manager.
        
        Args:
            scrolled_window: The ScrolledWindow containing the messages
            container: The Box container holding message widgets
        """
        self.scrolled_window = scrolled_window
        self.container = container
        self.enabled = True
        self._update_timeout_id = None
        self._last_adjustment_value = 0
        
        # Connect to scroll events
        vadjustment = self.scrolled_window.get_vadjustment()
        if vadjustment:
            vadjustment.connect('value-changed', self._on_scroll)
    
    def enable(self):
        """Enable virtualization."""
        self.enabled = True
        self._schedule_update()
    
    def disable(self):
        """Disable virtualization and show all messages."""
        self.enabled = False
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
            self._update_timeout_id = None
        self._show_all_messages()
    
    def _on_scroll(self, adjustment):
        """Handle scroll events."""
        if not self.enabled:
            return
        
        # Only update if scroll position changed significantly
        current_value = adjustment.get_value()
        if abs(current_value - self._last_adjustment_value) > 50:
            self._last_adjustment_value = current_value
            self._schedule_update()
    
    def _schedule_update(self):
        """Schedule a viewport update (debounced)."""
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
        
        self._update_timeout_id = GLib.timeout_add(100, self._update_visible_messages)
    
    def _update_visible_messages(self):
        """Update which messages are visible based on viewport."""
        self._update_timeout_id = None
        
        if not self.enabled:
            return False
        
        messages = list(self.container)
        message_count = len(messages)
        
        # Don't virtualize if there aren't many messages
        if message_count < self.MIN_MESSAGES_FOR_VIRTUALIZATION:
            self._show_all_messages()
            return False
        
        # Get viewport bounds
        vadjustment = self.scrolled_window.get_vadjustment()
        if not vadjustment:
            return False
        
        viewport_top = vadjustment.get_value()
        viewport_height = vadjustment.get_page_size()
        viewport_bottom = viewport_top + viewport_height
        
        # Add buffer zones
        buffer_top = max(0, viewport_top - viewport_height)
        buffer_bottom = viewport_bottom + viewport_height
        
        # Update visibility for each message
        visible_count = 0
        hidden_count = 0
        
        for message in messages:
            if not message.get_realized():
                continue
            
            # Get message position
            allocation = message.get_allocation()
            message_top = allocation.y
            message_bottom = message_top + allocation.height
            
            # Check if message is in buffer zone
            is_in_buffer = (message_bottom >= buffer_top and message_top <= buffer_bottom)
            
            if is_in_buffer:
                if not message.get_visible():
                    message.set_visible(True)
                    visible_count += 1
            else:
                if message.get_visible():
                    message.set_visible(False)
                    hidden_count += 1
        
        if visible_count > 0 or hidden_count > 0:
            logger.debug(f"Virtualization: showed {visible_count}, hid {hidden_count} messages")
        
        return False
    
    def _show_all_messages(self):
        """Show all messages (disable virtualization)."""
        for message in list(self.container):
            if not message.get_visible():
                message.set_visible(True)
    
    def update_now(self):
        """Force an immediate update of visible messages."""
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
            self._update_timeout_id = None
        
        if self.enabled:
            self._update_visible_messages()
    
    def on_messages_loaded(self):
        """Call this after messages are loaded to initialize virtualization."""
        # Wait a bit for layout to settle
        GLib.timeout_add(200, self._update_visible_messages)
    
    def cleanup(self):
        """Clean up resources."""
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
            self._update_timeout_id = None
