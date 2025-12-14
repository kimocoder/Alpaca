"""
Accessibility utilities for Alpaca application.

This module provides helper functions for setting ARIA labels and roles
on GTK widgets to improve screen reader support and accessibility.
"""

from gi.repository import Gtk
import logging

logger = logging.getLogger(__name__)


def set_accessible_label(widget: Gtk.Widget, label: str) -> None:
    """
    Set accessible label for a widget.
    
    Args:
        widget: The GTK widget to label
        label: The accessible label text
    """
    if widget and label:
        widget.update_property(
            [Gtk.AccessibleProperty.LABEL],
            [label]
        )


def set_accessible_description(widget: Gtk.Widget, description: str) -> None:
    """
    Set accessible description for a widget.
    
    Args:
        widget: The GTK widget to describe
        description: The accessible description text
    """
    if widget and description:
        widget.update_property(
            [Gtk.AccessibleProperty.DESCRIPTION],
            [description]
        )


def set_accessible_role(widget: Gtk.Widget, role: Gtk.AccessibleRole) -> None:
    """
    Set accessible role for a widget.
    
    Args:
        widget: The GTK widget
        role: The accessible role
    """
    if widget:
        widget.set_accessible_role(role)


def configure_button_accessibility(
    button: Gtk.Button,
    label: str,
    description: str = None
) -> None:
    """
    Configure accessibility properties for a button.
    
    Args:
        button: The button widget
        label: The accessible label
        description: Optional accessible description
    """
    set_accessible_label(button, label)
    if description:
        set_accessible_description(button, description)


def configure_entry_accessibility(
    entry: Gtk.Entry,
    label: str,
    description: str = None
) -> None:
    """
    Configure accessibility properties for an entry field.
    
    Args:
        entry: The entry widget
        label: The accessible label
        description: Optional accessible description
    """
    set_accessible_label(entry, label)
    if description:
        set_accessible_description(entry, description)


def configure_search_accessibility(
    search_entry: Gtk.SearchEntry,
    label: str,
    description: str = None
) -> None:
    """
    Configure accessibility properties for a search entry.
    
    Args:
        search_entry: The search entry widget
        label: The accessible label
        description: Optional accessible description
    """
    set_accessible_label(search_entry, label)
    if description:
        set_accessible_description(search_entry, description)


def is_high_contrast_enabled() -> bool:
    """
    Check if high contrast mode is currently enabled.
    
    Returns:
        True if high contrast mode is enabled, False otherwise
    """
    settings = Gtk.Settings.get_default()
    if settings:
        theme_name = settings.get_property('gtk-theme-name')
        is_high_contrast = 'HighContrast' in theme_name if theme_name else False
        return is_high_contrast
    return False


def get_contrast_ratio(foreground: tuple, background: tuple) -> float:
    """
    Calculate the contrast ratio between two colors.
    
    This follows the WCAG 2.1 contrast ratio formula.
    
    Args:
        foreground: RGB tuple (r, g, b) with values 0-255
        background: RGB tuple (r, g, b) with values 0-255
    
    Returns:
        The contrast ratio as a float (1.0 to 21.0)
    """
    def relative_luminance(rgb):
        """Calculate relative luminance of an RGB color."""
        r, g, b = [x / 255.0 for x in rgb]
        
        # Apply gamma correction
        def adjust(channel):
            if channel <= 0.03928:
                return channel / 12.92
            else:
                return ((channel + 0.055) / 1.055) ** 2.4
        
        r, g, b = adjust(r), adjust(g), adjust(b)
        
        # Calculate luminance
        return 0.2126 * r + 0.7152 * g + 0.0722 * b
    
    l1 = relative_luminance(foreground)
    l2 = relative_luminance(background)
    
    # Ensure l1 is the lighter color
    if l1 < l2:
        l1, l2 = l2, l1
    
    # Calculate contrast ratio
    return (l1 + 0.05) / (l2 + 0.05)


def check_contrast_compliance(
    foreground: tuple,
    background: tuple,
    is_large_text: bool = False
) -> dict:
    """
    Check if a color combination meets WCAG contrast requirements.
    
    Args:
        foreground: RGB tuple (r, g, b) with values 0-255
        background: RGB tuple (r, g, b) with values 0-255
        is_large_text: True if text is large (18pt+ or 14pt+ bold)
    
    Returns:
        Dictionary with compliance information:
        {
            'ratio': float,
            'wcag_aa': bool,
            'wcag_aaa': bool,
            'level': str
        }
    """
    ratio = get_contrast_ratio(foreground, background)
    
    # WCAG 2.1 requirements
    if is_large_text:
        aa_threshold = 3.0
        aaa_threshold = 4.5
    else:
        aa_threshold = 4.5
        aaa_threshold = 7.0
    
    wcag_aa = ratio >= aa_threshold
    wcag_aaa = ratio >= aaa_threshold
    
    if wcag_aaa:
        level = 'AAA'
    elif wcag_aa:
        level = 'AA'
    else:
        level = 'Fail'
    
    return {
        'ratio': ratio,
        'wcag_aa': wcag_aa,
        'wcag_aaa': wcag_aaa,
        'level': level
    }
