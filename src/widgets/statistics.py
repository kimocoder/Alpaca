# statistics.py
#
# Copyright 2024-2025 Jeffser
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.
#
# SPDX-License-Identifier: GPL-3.0-or-later

"""
Statistics dashboard widget for displaying usage analytics.
"""

from gi.repository import Adw, Gtk, GLib
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


@Gtk.Template(resource_path='/com/jeffser/Alpaca/widgets/statistics_dashboard.ui')
class StatisticsDashboard(Adw.Dialog):
    """
    Statistics dashboard dialog showing token usage, response times, and model usage.
    """
    __gtype_name__ = 'AlpacaStatisticsDashboard'
    
    # Template children
    token_usage_label = Gtk.Template.Child()
    token_usage_by_model_box = Gtk.Template.Child()
    response_time_avg_label = Gtk.Template.Child()
    response_time_min_label = Gtk.Template.Child()
    response_time_max_label = Gtk.Template.Child()
    response_time_median_label = Gtk.Template.Child()
    response_time_total_label = Gtk.Template.Child()
    model_usage_box = Gtk.Template.Child()
    date_range_combo = Gtk.Template.Child()
    refresh_button = Gtk.Template.Child()
    
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self._setup_ui()
        self.load_statistics()
    
    def _setup_ui(self):
        """Set up the UI components."""
        # Connect signals
        self.date_range_combo.connect('notify::selected', self._on_date_range_changed)
        self.refresh_button.connect('clicked', self._on_refresh_clicked)
    
    def _on_date_range_changed(self, combo, param):
        """Handle date range selection change."""
        self.load_statistics()
    
    def _on_refresh_clicked(self, button):
        """Handle refresh button click."""
        self.load_statistics()
    
    def _get_date_range(self):
        """
        Get the date range based on the selected option.
        
        Returns:
            Tuple of (date_from, date_to) or (None, None) for all time
        """
        selected = self.date_range_combo.get_selected()
        now = datetime.now()
        
        if selected == 0:  # All time
            return None, None
        elif selected == 1:  # Last 7 days
            return now - timedelta(days=7), now
        elif selected == 2:  # Last 30 days
            return now - timedelta(days=30), now
        elif selected == 3:  # Last 90 days
            return now - timedelta(days=90), now
        else:
            return None, None
    
    def load_statistics(self):
        """Load and display statistics from the database."""
        try:
            from ..services.statistics import StatisticsService
            
            service = StatisticsService()
            date_from, date_to = self._get_date_range()
            
            # Load token usage statistics
            self._load_token_usage(service, date_from, date_to)
            
            # Load response time statistics
            self._load_response_times(service)
            
            # Load model usage statistics
            self._load_model_usage(service)
            
        except Exception as e:
            logger.error(f"Error loading statistics: {e}")
            self._show_error(_("Failed to load statistics"))
    
    def _load_token_usage(self, service, date_from, date_to):
        """
        Load and display token usage statistics.
        
        Args:
            service: StatisticsService instance
            date_from: Start date for filtering
            date_to: End date for filtering
        """
        try:
            stats = service.get_token_usage(date_from, date_to)
            
            # Format total tokens
            total_tokens = stats.total_tokens
            if total_tokens >= 1000000:
                display_text = f'{total_tokens / 1000000:.2f}M'
            elif total_tokens >= 1000:
                display_text = f'{total_tokens / 1000:.2f}K'
            else:
                display_text = str(total_tokens)
            
            self.token_usage_label.set_label(display_text)
            
            # Clear previous model breakdown
            while True:
                child = self.token_usage_by_model_box.get_first_child()
                if child is None:
                    break
                self.token_usage_by_model_box.remove(child)
            
            # Add model breakdown
            if stats.by_model:
                # Sort by usage (descending)
                sorted_models = sorted(
                    stats.by_model.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                
                for model_name, tokens in sorted_models:
                    # Format tokens
                    if tokens >= 1000000:
                        tokens_text = f'{tokens / 1000000:.2f}M'
                    elif tokens >= 1000:
                        tokens_text = f'{tokens / 1000:.2f}K'
                    else:
                        tokens_text = str(tokens)
                    
                    # Calculate percentage
                    percentage = (tokens / total_tokens * 100) if total_tokens > 0 else 0
                    
                    # Create row
                    row = Adw.ActionRow()
                    row.set_title(model_name)
                    row.set_subtitle(f'{tokens_text} tokens ({percentage:.1f}%)')
                    
                    # Add progress bar
                    progress = Gtk.ProgressBar()
                    progress.set_fraction(percentage / 100)
                    progress.set_valign(Gtk.Align.CENTER)
                    progress.add_css_class('osd')
                    row.add_suffix(progress)
                    
                    self.token_usage_by_model_box.append(row)
            else:
                # No data
                label = Gtk.Label()
                label.set_label(_("No token usage data available"))
                label.add_css_class('dim-label')
                label.set_margin_top(12)
                label.set_margin_bottom(12)
                self.token_usage_by_model_box.append(label)
                
        except Exception as e:
            logger.error(f"Error loading token usage: {e}")
            self.token_usage_label.set_label('0')
    
    def _load_response_times(self, service):
        """
        Load and display response time statistics.
        
        Args:
            service: StatisticsService instance
        """
        try:
            stats = service.get_response_times()
            
            if stats.total_requests > 0:
                self.response_time_avg_label.set_label(f'{stats.average_ms:.0f} ms')
                self.response_time_min_label.set_label(f'{stats.min_ms} ms')
                self.response_time_max_label.set_label(f'{stats.max_ms} ms')
                self.response_time_median_label.set_label(f'{stats.median_ms:.0f} ms')
                self.response_time_total_label.set_label(str(stats.total_requests))
            else:
                self.response_time_avg_label.set_label(_('No data'))
                self.response_time_min_label.set_label(_('No data'))
                self.response_time_max_label.set_label(_('No data'))
                self.response_time_median_label.set_label(_('No data'))
                self.response_time_total_label.set_label('0')
                
        except Exception as e:
            logger.error(f"Error loading response times: {e}")
            self.response_time_avg_label.set_label(_('Error'))
    
    def _load_model_usage(self, service):
        """
        Load and display model usage frequency.
        
        Args:
            service: StatisticsService instance
        """
        try:
            usage = service.get_model_usage()
            
            # Clear previous usage data
            while True:
                child = self.model_usage_box.get_first_child()
                if child is None:
                    break
                self.model_usage_box.remove(child)
            
            if usage:
                # Calculate total for percentages
                total_usage = sum(usage.values())
                
                # Sort by usage (descending)
                sorted_usage = sorted(
                    usage.items(),
                    key=lambda x: x[1],
                    reverse=True
                )
                
                for model_name, count in sorted_usage:
                    percentage = (count / total_usage * 100) if total_usage > 0 else 0
                    
                    # Create row
                    row = Adw.ActionRow()
                    row.set_title(model_name)
                    row.set_subtitle(f'{count} uses ({percentage:.1f}%)')
                    
                    # Add progress bar
                    progress = Gtk.ProgressBar()
                    progress.set_fraction(percentage / 100)
                    progress.set_valign(Gtk.Align.CENTER)
                    progress.add_css_class('osd')
                    row.add_suffix(progress)
                    
                    self.model_usage_box.append(row)
            else:
                # No data
                label = Gtk.Label()
                label.set_label(_("No model usage data available"))
                label.add_css_class('dim-label')
                label.set_margin_top(12)
                label.set_margin_bottom(12)
                self.model_usage_box.append(label)
                
        except Exception as e:
            logger.error(f"Error loading model usage: {e}")
    
    def _show_error(self, message):
        """
        Show an error message to the user.
        
        Args:
            message: Error message to display
        """
        # Create a simple error label
        error_label = Gtk.Label()
        error_label.set_label(message)
        error_label.add_css_class('error')
        error_label.set_margin_top(12)
        error_label.set_margin_bottom(12)
