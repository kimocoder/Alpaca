"""
Context indicator widget for displaying token usage in chat.

This module provides a widget that displays the current token count
and context window usage for the active chat.
"""

import gi
from gi.repository import Gtk, GLib
import logging

logger = logging.getLogger(__name__)


class ContextIndicator(Gtk.Box):
    """
    Widget that displays context window usage information.
    
    Shows the current token count and provides visual feedback
    when approaching context limits.
    """
    
    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=6,
            halign=Gtk.Align.END,
            valign=Gtk.Align.CENTER
        )
        
        # Icon for visual indicator
        self.icon = Gtk.Image.new_from_icon_name('document-text-symbolic')
        self.icon.set_icon_size(Gtk.IconSize.NORMAL)
        self.append(self.icon)
        
        # Label for token count
        self.label = Gtk.Label()
        self.label.set_text('0 tokens')
        self.append(self.label)
        
        # Set tooltip
        self.set_tooltip_text(_('Context window usage'))
        
        # Add CSS class for styling
        self.add_css_class('context-indicator')
        
        # Track current chat
        self._current_chat = None
        self._update_timeout_id = None
    
    def set_chat(self, chat):
        """
        Set the chat to monitor for token count.
        
        Args:
            chat: The Chat widget to monitor
        """
        self._current_chat = chat
        self.update_token_count()
    
    def update_token_count(self):
        """
        Update the displayed token count from the current chat.
        """
        if not self._current_chat:
            self.label.set_text('0 tokens')
            self.remove_css_class('warning')
            return
        
        try:
            # Get token count from chat
            token_count = self._current_chat.get_token_count()
            
            # Format the display
            if token_count >= 1000000:
                display_text = f'{token_count / 1000000:.1f}M tokens'
            elif token_count >= 1000:
                display_text = f'{token_count / 1000:.1f}K tokens'
            else:
                display_text = f'{token_count} tokens'
            
            self.label.set_text(display_text)
            
            # Update tooltip with more details
            stats = self._current_chat.get_token_stats()
            tooltip = _(
                'Context window usage\n'
                'Total tokens: {total}\n'
                'Messages: {count}\n'
                'Avg per message: {avg:.1f}'
            ).format(
                total=token_count,
                count=stats['message_count'],
                avg=stats['avg_tokens_per_message']
            )
            self.set_tooltip_text(tooltip)
            
            # Add warning class if approaching typical context limits
            # Most models have 4K-8K context, so warn at 3K
            if token_count >= 3000:
                self.add_css_class('warning')
            else:
                self.remove_css_class('warning')
                
        except Exception as e:
            logger.warning(f"Error updating token count: {e}")
            self.label.set_text('0 tokens')
            self.remove_css_class('warning')
    
    def schedule_update(self):
        """
        Schedule a token count update after a short delay.
        
        This is useful to batch updates when multiple messages
        are added in quick succession.
        """
        # Cancel any pending update
        if self._update_timeout_id:
            GLib.source_remove(self._update_timeout_id)
        
        # Schedule new update
        self._update_timeout_id = GLib.timeout_add(
            500,  # 500ms delay
            self._do_scheduled_update
        )
    
    def _do_scheduled_update(self):
        """Internal method to perform the scheduled update."""
        self.update_token_count()
        self._update_timeout_id = None
        return False  # Don't repeat
