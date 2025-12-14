"""
Keyboard navigation utilities for Alpaca application.

This module provides helper functions for improving keyboard navigation
and focus management throughout the application.
"""

from gi.repository import Gtk, Gdk, GLib
import logging

logger = logging.getLogger(__name__)


def make_widget_keyboard_accessible(
    widget: Gtk.Widget,
    can_focus: bool = True,
    focus_on_click: bool = True
) -> None:
    """
    Make a widget keyboard accessible by enabling focus.
    
    Args:
        widget: The GTK widget to make accessible
        can_focus: Whether the widget can receive keyboard focus
        focus_on_click: Whether clicking the widget gives it focus
    """
    if widget:
        widget.set_focusable(can_focus)
        if hasattr(widget, 'set_focus_on_click'):
            widget.set_focus_on_click(focus_on_click)


def setup_focus_chain(container: Gtk.Widget, widgets: list) -> None:
    """
    Set up a custom focus chain for a container.
    
    Args:
        container: The container widget
        widgets: List of widgets in the desired focus order
    """
    if container and widgets:
        try:
            container.set_focus_chain(widgets)
        except Exception as e:
            logger.warning(f"Could not set focus chain: {e}")


def add_focus_css_class(widget: Gtk.Widget, css_class: str = "keyboard-focus") -> None:
    """
    Add a CSS class to a widget when it receives keyboard focus.
    
    Args:
        widget: The widget to add focus styling to
        css_class: The CSS class to add on focus
    """
    if not widget:
        return
    
    def on_focus_in(widget, *args):
        widget.add_css_class(css_class)
    
    def on_focus_out(widget, *args):
        widget.remove_css_class(css_class)
    
    # Connect to focus events
    focus_controller = Gtk.EventControllerFocus()
    focus_controller.connect('enter', on_focus_in)
    focus_controller.connect('leave', on_focus_out)
    widget.add_controller(focus_controller)


def setup_keyboard_navigation_for_list(listbox: Gtk.ListBox) -> None:
    """
    Enhance keyboard navigation for a ListBox.
    
    Adds support for:
    - Arrow keys to navigate
    - Enter/Space to activate
    - Home/End to jump to first/last
    
    Args:
        listbox: The ListBox to enhance
    """
    if not listbox:
        return
    
    def on_key_pressed(controller, keyval, keycode, state):
        # Get currently selected row
        selected_row = listbox.get_selected_row()
        
        if keyval == Gdk.KEY_Home:
            # Jump to first row
            first_row = listbox.get_row_at_index(0)
            if first_row:
                listbox.select_row(first_row)
                first_row.grab_focus()
            return True
        
        elif keyval == Gdk.KEY_End:
            # Jump to last row
            rows = list(listbox)
            if rows:
                last_row = rows[-1]
                listbox.select_row(last_row)
                last_row.grab_focus()
            return True
        
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            # Activate selected row
            if selected_row:
                listbox.emit('row-activated', selected_row)
            return True
        
        return False
    
    key_controller = Gtk.EventControllerKey()
    key_controller.connect('key-pressed', on_key_pressed)
    listbox.add_controller(key_controller)


def setup_keyboard_navigation_for_flowbox(flowbox: Gtk.FlowBox) -> None:
    """
    Enhance keyboard navigation for a FlowBox.
    
    Adds support for:
    - Arrow keys to navigate
    - Enter/Space to activate
    - Home/End to jump to first/last
    
    Args:
        flowbox: The FlowBox to enhance
    """
    if not flowbox:
        return
    
    def on_key_pressed(controller, keyval, keycode, state):
        # Get currently selected child
        selected_children = flowbox.get_selected_children()
        
        if keyval == Gdk.KEY_Home:
            # Jump to first child
            first_child = flowbox.get_child_at_index(0)
            if first_child:
                flowbox.select_child(first_child)
                first_child.grab_focus()
            return True
        
        elif keyval == Gdk.KEY_End:
            # Jump to last child
            children = list(flowbox)
            if children:
                last_child = children[-1]
                flowbox.select_child(last_child)
                last_child.grab_focus()
            return True
        
        elif keyval in (Gdk.KEY_Return, Gdk.KEY_KP_Enter, Gdk.KEY_space):
            # Activate selected child
            if selected_children:
                flowbox.emit('child-activated', selected_children[0])
            return True
        
        return False
    
    key_controller = Gtk.EventControllerKey()
    key_controller.connect('key-pressed', on_key_pressed)
    flowbox.add_controller(key_controller)


def setup_escape_key_handler(widget: Gtk.Widget, callback) -> None:
    """
    Add an Escape key handler to a widget.
    
    Args:
        widget: The widget to add the handler to
        callback: Function to call when Escape is pressed
    """
    if not widget:
        return
    
    def on_key_pressed(controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape:
            callback()
            return True
        return False
    
    key_controller = Gtk.EventControllerKey()
    key_controller.connect('key-pressed', on_key_pressed)
    widget.add_controller(key_controller)


def setup_tab_navigation(widget: Gtk.Widget, forward_target: Gtk.Widget = None, backward_target: Gtk.Widget = None) -> None:
    """
    Set up custom Tab/Shift+Tab navigation for a widget.
    
    Args:
        widget: The widget to add tab navigation to
        forward_target: Widget to focus on Tab (if None, uses default)
        backward_target: Widget to focus on Shift+Tab (if None, uses default)
    """
    if not widget:
        return
    
    def on_key_pressed(controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Tab:
            if state & Gdk.ModifierType.SHIFT_MASK:
                # Shift+Tab - go backward
                if backward_target:
                    backward_target.grab_focus()
                    return True
            else:
                # Tab - go forward
                if forward_target:
                    forward_target.grab_focus()
                    return True
        return False
    
    key_controller = Gtk.EventControllerKey()
    key_controller.connect('key-pressed', on_key_pressed)
    widget.add_controller(key_controller)


def ensure_visible_on_focus(scrolled_window: Gtk.ScrolledWindow, widget: Gtk.Widget) -> None:
    """
    Ensure a widget is visible in a scrolled window when it receives focus.
    
    Args:
        scrolled_window: The scrolled window containing the widget
        widget: The widget that should be made visible on focus
    """
    if not scrolled_window or not widget:
        return
    
    def on_focus_in(widget, *args):
        # Get the widget's allocation
        allocation = widget.get_allocation()
        
        # Get the scrolled window's adjustment
        vadjustment = scrolled_window.get_vadjustment()
        
        if vadjustment:
            # Calculate if widget is visible
            widget_top = allocation.y
            widget_bottom = allocation.y + allocation.height
            viewport_top = vadjustment.get_value()
            viewport_bottom = viewport_top + vadjustment.get_page_size()
            
            # Scroll if widget is not fully visible
            if widget_top < viewport_top:
                vadjustment.set_value(widget_top)
            elif widget_bottom > viewport_bottom:
                vadjustment.set_value(widget_bottom - vadjustment.get_page_size())
    
    focus_controller = Gtk.EventControllerFocus()
    focus_controller.connect('enter', on_focus_in)
    widget.add_controller(focus_controller)


def make_button_keyboard_accessible(button: Gtk.Button, tooltip: str = None) -> None:
    """
    Ensure a button is fully keyboard accessible.
    
    Args:
        button: The button to make accessible
        tooltip: Optional tooltip text to add
    """
    if not button:
        return
    
    make_widget_keyboard_accessible(button)
    add_focus_css_class(button)
    
    if tooltip:
        button.set_tooltip_text(tooltip)


def make_entry_keyboard_accessible(entry: Gtk.Entry, next_widget: Gtk.Widget = None) -> None:
    """
    Ensure an entry field is fully keyboard accessible.
    
    Args:
        entry: The entry to make accessible
        next_widget: Optional widget to focus when Enter is pressed
    """
    if not entry:
        return
    
    make_widget_keyboard_accessible(entry)
    add_focus_css_class(entry)
    
    if next_widget:
        def on_activate(entry):
            next_widget.grab_focus()
        entry.connect('activate', on_activate)


def setup_dialog_keyboard_navigation(dialog: Gtk.Dialog) -> None:
    """
    Set up keyboard navigation for a dialog.
    
    Adds:
    - Escape to close
    - Tab navigation between elements
    - Enter to activate default button
    
    Args:
        dialog: The dialog to enhance
    """
    if not dialog:
        return
    
    # Add Escape key handler
    setup_escape_key_handler(dialog, lambda: dialog.close())
    
    # Focus first focusable widget when dialog is shown
    def on_show(dialog):
        # Find first focusable widget
        def find_first_focusable(widget):
            if widget.get_focusable() and widget.get_visible():
                return widget
            
            # Check children
            child = widget.get_first_child()
            while child:
                result = find_first_focusable(child)
                if result:
                    return result
                child = child.get_next_sibling()
            
            return None
        
        first_focusable = find_first_focusable(dialog)
        if first_focusable:
            GLib.idle_add(first_focusable.grab_focus)
    
    dialog.connect('show', on_show)


def add_skip_to_content_link(window: Gtk.Window, content_widget: Gtk.Widget) -> None:
    """
    Add a "skip to content" link for keyboard navigation.
    
    This is an accessibility feature that allows keyboard users to
    skip navigation elements and jump directly to main content.
    
    Args:
        window: The main window
        content_widget: The main content widget to skip to
    """
    if not window or not content_widget:
        return
    
    skip_button = Gtk.Button(label="Skip to content")
    skip_button.add_css_class("skip-to-content")
    skip_button.set_focusable(True)
    
    def on_skip_clicked(button):
        content_widget.grab_focus()
    
    skip_button.connect('clicked', on_skip_clicked)
    
    # The button should be visually hidden but accessible to keyboard users
    # This is typically done via CSS


def setup_roving_tabindex(container: Gtk.Widget, items: list) -> None:
    """
    Set up roving tabindex pattern for a group of items.
    
    This pattern allows arrow key navigation within a group while
    maintaining a single tab stop for the entire group.
    
    Args:
        container: The container holding the items
        items: List of items to include in roving tabindex
    """
    if not container or not items:
        return
    
    # Only the first item should be in the tab order initially
    for i, item in enumerate(items):
        item.set_focusable(i == 0)
    
    def on_key_pressed(controller, keyval, keycode, state):
        focused_widget = container.get_focus_child()
        if not focused_widget or focused_widget not in items:
            return False
        
        current_index = items.index(focused_widget)
        next_index = None
        
        if keyval in (Gdk.KEY_Right, Gdk.KEY_Down):
            next_index = (current_index + 1) % len(items)
        elif keyval in (Gdk.KEY_Left, Gdk.KEY_Up):
            next_index = (current_index - 1) % len(items)
        
        if next_index is not None:
            # Update focusable state
            focused_widget.set_focusable(False)
            items[next_index].set_focusable(True)
            items[next_index].grab_focus()
            return True
        
        return False
    
    key_controller = Gtk.EventControllerKey()
    key_controller.connect('key-pressed', on_key_pressed)
    container.add_controller(key_controller)
