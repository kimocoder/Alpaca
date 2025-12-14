# window.py
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
Handles the main window
"""

import json, threading, os, re, gettext, shutil, logging, time, requests, sys, tempfile, importlib.util
import numpy as np

from datetime import datetime

from gi.repository import Adw, Gtk, Gdk, GLib, GtkSource, Gio, Spelling

from .sql_manager import generate_uuid, generate_numbered_name, prettify_model_name, Instance as SQL
from . import widgets as Widgets
from .constants import data_dir, source_dir, cache_dir, HIGHLIGHT_ALPHA
from .utils import keyboard_navigation

logger = logging.getLogger(__name__)

@Gtk.Template(resource_path='/com/jeffser/Alpaca/window.ui')
class AlpacaWindow(Adw.ApplicationWindow):
    __gtype_name__ = 'AlpacaWindow'

    localedir = os.path.join(source_dir, 'locale')

    gettext.bindtextdomain('com.jeffser.Alpaca', localedir)
    gettext.textdomain('com.jeffser.Alpaca')
    _ = gettext.gettext

    #Elements
    new_chat_splitbutton = Gtk.Template.Child()
    local_model_stack = Gtk.Template.Child()
    available_model_stack = Gtk.Template.Child()
    model_manager_stack = Gtk.Template.Child()
    instance_manager_stack = Gtk.Template.Child()
    main_navigation_view = Gtk.Template.Child()
    local_model_flowbox = Gtk.Template.Child()
    available_model_flowbox = Gtk.Template.Child()
    split_view_overlay = Gtk.Template.Child()
    toast_overlay = Gtk.Template.Child()
    chat_bin = Gtk.Template.Child()
    chat_list_navigationview = Gtk.Template.Child()
    global_footer = Gtk.Template.Child()
    model_searchbar = Gtk.Template.Child()
    searchentry_models = Gtk.Template.Child()
    model_search_button = Gtk.Template.Child()
    message_searchbar = Gtk.Template.Child()
    searchentry_messages = Gtk.Template.Child()
    model_filter_button = Gtk.Template.Child()

    file_filter_db = Gtk.Template.Child()

    banner = Gtk.Template.Child()

    instance_preferences_page = Gtk.Template.Child()
    instance_listbox = Gtk.Template.Child()
    available_models_stack_page = Gtk.Template.Child()
    model_manager_bottom_view_switcher = Gtk.Template.Child()
    model_manager_top_view_switcher = Gtk.Template.Child()
    last_selected_instance_row = None

    chat_splitview = Gtk.Template.Child()
    activities_page = Gtk.Template.Child()
    chat_page = Gtk.Template.Child()
    last_breakpoint_status = False

    chat_searchbar = Gtk.Template.Child()
    context_indicator_box = Gtk.Template.Child()
    context_indicator_label = Gtk.Template.Child()

    @Gtk.Template.Callback()
    def explore_available_models(self, button):
        if len(Widgets.models.common.available_models_data) == 0:
            Widgets.dialog.simple(
                parent = self,
                heading = _("No Models"),
                body = _("This instance does not provide any models"),
                callback = self.get_application().lookup_action('instance_manager').activate,
                button_name = _("Manage Instances")
            )
        else:
            self.model_manager_stack.set_visible_child_name('available_models')

    @Gtk.Template.Callback()
    def chat_list_page_changed(self, navigationview, page=None):
        if self.chat_searchbar.get_search_mode():
            self.chat_searchbar.set_search_mode(False)
            previous_page = navigationview.get_previous_page(navigationview.get_visible_page())
            if previous_page:
                previous_page.on_search('')

    @Gtk.Template.Callback()
    def last_breakpoint_applied(self, bp):
        self.last_breakpoint_status = True

    @Gtk.Template.Callback()
    def last_breakpoint_unapplied(self, bp):
        if len(self.activities_page.get_child().tabview.get_pages()) > 0:
            GLib.idle_add(self.chat_splitview.set_collapsed, False)
        self.chat_splitview.set_show_content(True)
        self.last_breakpoint_status = False

    @Gtk.Template.Callback()
    def show_activities_button_pressed(self, button):
        self.chat_splitview.set_show_content(False)

    @Gtk.Template.Callback()
    def add_instance(self, button):
        def selected(ins):
            if ins.instance_type == 'ollama:managed' and not shutil.which('ollama'):
                Widgets.dialog.simple(
                    parent = button.get_root(),
                    heading = _("Ollama Was Not Found"),
                    body = _("To add a managed Ollama instance, you must have Ollama installed locally in your device, this is a simple process and should not take more than 5 minutes."),
                    callback = lambda: Gio.AppInfo.launch_default_for_uri('https://jeffser.com/alpaca/installation-guide.html'),
                    button_name = _("Open Tutorial in Web Browser")
                )
            else:
                instance = ins(
                    instance_id=None,
                    properties={}
                )
                Widgets.instances.InstancePreferencesDialog(instance).present(self)

        options = {}
        instance_list = Widgets.instances.ollama_instances.BaseInstance.__subclasses__()
        if os.getenv('ALPACA_OLLAMA_ONLY', '0') != '1':
            instance_list += Widgets.instances.openai_instances.BaseInstance.__subclasses__()
        for ins_type in instance_list:
            options[ins_type.instance_type_display] = ins_type

        Widgets.dialog.simple_dropdown(
            parent = button.get_root(),
            heading = _("Add Instance"),
            body = _("Select a type of instance to add"),
            callback = lambda option, options=options: selected(options[option]),
            items = options.keys()
        )

    @Gtk.Template.Callback()
    def instance_changed(self, listbox, row):
        def change_instance():
            if self.last_selected_instance_row:
                self.last_selected_instance_row.instance.stop()

            self.last_selected_instance_row = row

            Widgets.models.update_added_model_list(self)
            Widgets.models.update_available_model_list(self)

            if row:
                self.settings.set_string('selected-instance', row.instance.instance_id)
                self.get_application().lookup_action('model_creator_existing').set_enabled(row.instance.instance_type in ('ollama', 'ollama:managed'))
                self.get_application().lookup_action('model_creator_gguf').set_enabled(row.instance.instance_type in ('ollama', 'ollama:managed'))

            listbox.set_sensitive(True)
        if listbox.get_sensitive():
            listbox.set_sensitive(False)
            threading.Thread(target=change_instance, daemon=True).start()

    @Gtk.Template.Callback()
    def model_manager_stack_changed(self, viewstack, params):
        self.local_model_flowbox.unselect_all()
        self.available_model_flowbox.unselect_all()
        self.model_search_button.set_sensitive(viewstack.get_visible_child_name() not in ('model_creator', 'instances'))
        self.model_search_button.set_active(self.model_search_button.get_active() and viewstack.get_visible_child_name() not in ('model_creator', 'instances'))

    @Gtk.Template.Callback()
    def closing_app(self, user_data):
        def close():
            try:
                self.settings.set_string('default-chat', self.chat_bin.get_child().chat_id)
            except Exception as e:
                logger.warning(f"Could not save default chat: {e}")
            
            try:
                current_instance = self.get_current_instance()
                if hasattr(current_instance, 'stop'):
                    current_instance.stop()
            except Exception as e:
                logger.warning(f"Error stopping current instance: {e}")
            
            try:
                if Widgets.voice.message_dictated:
                    Widgets.voice.message_dictated.popup.tts_button.set_active(False)
            except Exception as e:
                logger.warning(f"Error stopping voice: {e}")
            
            # Quit from the GLib main loop to avoid teardown races with worker threads
            GLib.idle_add(self.get_application().quit)

        def switch_to_hide():
            self.set_hide_on_close(True)
            self.close() #Recalls this function

        if self.get_hide_on_close():
            logger.info("Hiding app...")
        else:
            logger.info("Closing app...")
            is_chat_busy = any([chat_row.chat.busy for chat_row in list(self.get_chat_list_page().chat_list_box)])
            is_model_downloading = any([el for el in list(self.local_model_flowbox) if el.get_child().progressbar.get_visible()])
            if is_chat_busy or is_model_downloading:
                options = {
                    _('Cancel'): {'default': True},
                    _('Hide'): {'callback': switch_to_hide},
                    _('Close'): {'callback': close, 'appearance': 'destructive'},
                }
                Widgets.dialog.Options(
                    heading = _('Close Alpaca?'),
                    body = _('A task is currently in progress. Are you sure you want to close Alpaca?'),
                    close_response = list(options.keys())[0],
                    options = options,
                ).show(self)
                return True
            else:
                close()

    @Gtk.Template.Callback()
    def chat_search_changed(self, entry):
        self.get_chat_list_page().on_search(entry.get_text())

    @Gtk.Template.Callback()
    def model_search_changed(self, entry):
        filtered_categories = set()
        if self.model_filter_button.get_popover():
            filtered_categories = set([c.get_name() for c in list(self.model_filter_button.get_popover().get_child()) if c.get_active()])
        results_local = False

        if len(list(self.local_model_flowbox)) > 0:
            for model in list(self.local_model_flowbox):
                string_search = re.search(entry.get_text(), model.get_child().get_search_string(), re.IGNORECASE)
                category_filter = len(filtered_categories) == 0 or model.get_child().get_search_categories() & filtered_categories or not self.model_searchbar.get_search_mode()
                model.set_visible(string_search and category_filter)
                results_local = results_local or model.get_visible()
                if not model.get_visible() and model in self.local_model_flowbox.get_selected_children():
                    self.local_model_flowbox.unselect_all()
            self.local_model_stack.set_visible_child_name('content' if results_local or not entry.get_text() else 'no-results')
        else:
            self.local_model_stack.set_visible_child_name('no-models')

        results_available = False
        if len(Widgets.models.common.available_models_data) > 0:
            self.available_models_stack_page.set_visible(True)
            for model in list(self.available_model_flowbox):
                string_search = re.search(entry.get_text(), model.get_child().get_search_string(), re.IGNORECASE)
                category_filter = len(filtered_categories) == 0 or model.get_child().get_search_categories() & filtered_categories or not self.model_searchbar.get_search_mode()
                model.set_visible(string_search and category_filter)
                results_available = results_available or model.get_visible()
                if not model.get_visible() and model in self.available_model_flowbox.get_selected_children():
                    self.available_model_flowbox.unselect_all()
            self.available_model_stack.set_visible_child_name('content' if results_available else 'no-results')
        else:
            self.available_models_stack_page.set_visible(False)

    @Gtk.Template.Callback()
    def message_search_changed(self, entry, current_chat=None):
        search_term=entry.get_text()
        message_results = 0
        if not current_chat and self.chat_bin.get_child():
            current_chat = self.chat_bin.get_child()
        if current_chat:
            try:
                for message in list(current_chat.container):
                    if message:
                        content = message.get_content()
                        if content:
                            string_search = re.search(search_term, content, re.IGNORECASE)
                            message.set_visible(string_search)
                            message_results += 1 if string_search else 0
                            for block in list(message.block_container):
                                if isinstance(block, Widgets.blocks.text.Text):
                                    if search_term:
                                        content = block.get_content().replace('&', '&amp;')
                                        search_text = search_term.replace('&', '&amp;')
                                        highlighted_text = re.sub(f"({search_text})", rf"<span background='yellow' bgalpha='{HIGHLIGHT_ALPHA}'>\1</span>", content, flags=re.IGNORECASE)
                                        block.set_markup(highlighted_text)
                                    else:
                                        block.set_content(block.get_content())
            except Exception as e:
                logger.error(e)
                pass
            if message_results > 0 or not search_term:
                if len(list(current_chat.container)) > 0:
                    current_chat.set_visible_child_name('content')
                else:
                    current_chat.set_visible_child_name('welcome-screen')
            else:
                current_chat.set_visible_child_name('no-results')

    def send_message(self, mode:int=0, available_tools:dict={}): #mode 0=user 1=system
        buffer = self.global_footer.get_buffer()

        raw_message = buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
        if not raw_message.strip():
            return

        current_chat = self.chat_bin.get_child()
        if current_chat.busy == True:
            return

        if self.get_current_instance().instance_type == 'empty':
            self.get_application().lookup_action('instance_manager').activate()
            return

        current_model = self.get_selected_model().get_name()
        if current_model is None:
            Widgets.dialog.show_toast(_("Please select a model before chatting"), current_chat.get_root())
            return

        # Bring tab to top
        row = current_chat.row
        chat_list = row.get_parent()
        GLib.idle_add(chat_list.unselect_all)
        GLib.idle_add(chat_list.remove, row)
        GLib.idle_add(chat_list.prepend, row)
        GLib.idle_add(chat_list.select_row, row)

        m_element = Widgets.message.Message(
            dt=datetime.now(),
            message_id=generate_uuid(),
            mode=mode*2
        )
        current_chat.add_message(m_element)

        for old_attachment in list(self.global_footer.attachment_container.container):
            attachment = m_element.add_attachment(
                file_id = generate_uuid(),
                name = old_attachment.file_name,
                attachment_type = old_attachment.file_type,
                content = old_attachment.file_content
            )
            old_attachment.delete()
            SQL.insert_or_update_attachment(m_element, attachment)

        m_element.block_container.set_content(raw_message)

        SQL.insert_or_update_message(m_element)

        buffer.set_text("", 0)

        # Update context indicator after adding user message
        self.schedule_context_indicator_update()

        if mode==0:
            m_element_bot = Widgets.message.Message(
                dt=datetime.now(),
                message_id=generate_uuid(),
                mode=1,
                author=current_model
            )
            current_chat.add_message(m_element_bot)
            SQL.insert_or_update_message(m_element_bot)
            if len(available_tools) > 0:
                threading.Thread(target=self.get_current_instance().use_tools, args=(m_element_bot, current_model, available_tools, True), daemon=True).start()
            else:
                threading.Thread(target=self.get_current_instance().generate_message, args=(m_element_bot, current_model), daemon=True).start()
        elif mode==1:
            current_chat.set_visible_child_name('content')

    def get_selected_model(self):
        selected_item = self.global_footer.model_selector.get_selected_item()
        if selected_item:
            return selected_item.model
        else:
            return Widgets.models.added.FallbackModel

    def get_current_instance(self):
        if self.instance_listbox.get_selected_row():
            return self.instance_listbox.get_selected_row().instance
        else:
            return Widgets.instances.Empty()

    def prepare_alpaca(self):
        self.main_navigation_view.replace_with_tags(['chat'])

        #Chat History
        root_folder = Widgets.chat.Folder(show_bar=False)
        self.chat_list_navigationview.add(root_folder)
        root_folder.update()

        if self.get_application().args.new_chat:
            self.get_chat_list_page().new_chat(self.get_application().args.new_chat)

        # Ollama is available but there are no instances added
        if not any(i.get("type") == "ollama:managed" for i in SQL.get_instances()) and shutil.which("ollama"):
            SQL.insert_or_update_instance(
                instance_id=generate_uuid(),
                pinned=True,
                instance_type='ollama:managed',
                properties={
                    'name': 'Alpaca',
                    'url': 'http://127.0.0.1:11435',
                }
            )

        Widgets.instances.update_instance_list(
            instance_listbox=self.instance_listbox,
            selected_instance_id=self.settings.get_value('selected-instance').unpack()
        )

    def on_chat_imported(self, file):
        if file:
            if os.path.isfile(os.path.join(cache_dir, 'import.db')):
                os.remove(os.path.join(cache_dir, 'import.db'))
            file.copy(Gio.File.new_for_path(os.path.join(cache_dir, 'import.db')), Gio.FileCopyFlags.OVERWRITE, None, None, None, None)
            chat_names = [tab.chat.get_name() for tab in list(self.get_chat_list_page().chat_list_box)]
            for chat in SQL.import_chat(os.path.join(cache_dir, 'import.db'), chat_names, self.get_chat_list_page().folder_id):
                self.get_chat_list_page().add_chat(
                    chat_name=chat[1],
                    chat_id=chat[0],
                    is_template=False,
                    mode=1
                )
            Widgets.dialog.show_toast(_("Chat imported successfully"), self)

    def toggle_searchbar(self):
        current_tag = self.main_navigation_view.get_visible_page_tag()

        searchbars = {
            'chat': self.message_searchbar,
            'model_manager': self.model_searchbar
        }

        if searchbars.get(current_tag):
            searchbars.get(current_tag).set_search_mode(not searchbars.get(current_tag).get_search_mode())

    def get_chat_list_page(self):
        return self.chat_list_navigationview.get_visible_page()

    def push_or_pop(self, page_name:str):
        if self.main_navigation_view.get_visible_page().get_tag() != page_name:
            GLib.idle_add(self.main_navigation_view.push_by_tag, page_name)
        else:
            GLib.idle_add(self.main_navigation_view.pop_to_tag, 'chat')

    def show_global_search(self):
        """Show the global search dialog"""
        search_dialog = Widgets.global_search.GlobalSearch()
        search_dialog.present(self)
    
    def show_statistics_dashboard(self):
        """Show the statistics dashboard dialog"""
        statistics_dialog = Widgets.statistics.StatisticsDashboard()
        statistics_dialog.present(self)
    
    def show_bookmarks(self):
        """Show the bookmarks dialog"""
        # TODO: Implement bookmarks dialog (Task 17-19)
        Widgets.dialog.show_toast(_("Bookmarks feature coming soon"), self)
    
    def show_prompt_library(self):
        """Show the prompt library dialog"""
        # TODO: Implement prompt library dialog (Task 24-28)
        Widgets.dialog.show_toast(_("Prompt Library feature coming soon"), self)
    
    def show_backup(self):
        """Show the backup & restore preferences"""
        preferences_dialog = Widgets.preferences.PreferencesDialog()
        preferences_dialog.present(self)
        # Navigate to backup page
        GLib.idle_add(preferences_dialog.set_visible_page, preferences_dialog.backup_page)
    
    def regenerate_last_message(self):
        """Regenerate the last AI message in the current chat"""
        current_chat = self.chat_bin.get_child()
        if not current_chat:
            Widgets.dialog.show_toast(_("No active chat"), self)
            return
        
        # Get all messages in the chat
        messages = list(current_chat.container)
        if not messages:
            Widgets.dialog.show_toast(_("No messages to regenerate"), self)
            return
        
        # Find the last AI message (mode=1)
        last_ai_message = None
        for message in reversed(messages):
            if hasattr(message, 'mode') and message.mode == 1:
                last_ai_message = message
                break
        
        if not last_ai_message:
            Widgets.dialog.show_toast(_("No AI messages to regenerate"), self)
            return
        
        # Trigger regeneration
        if hasattr(last_ai_message, 'popup') and hasattr(last_ai_message.popup, 'regenerate_message'):
            last_ai_message.popup.regenerate_message()
        else:
            Widgets.dialog.show_toast(_("Cannot regenerate this message"), self)
    
    def copy_last_response(self):
        """Copy the last AI response to clipboard"""
        current_chat = self.chat_bin.get_child()
        if not current_chat:
            Widgets.dialog.show_toast(_("No active chat"), self)
            return
        
        # Get all messages in the chat
        messages = list(current_chat.container)
        if not messages:
            Widgets.dialog.show_toast(_("No messages to copy"), self)
            return
        
        # Find the last AI message (mode=1)
        last_ai_message = None
        for message in reversed(messages):
            if hasattr(message, 'mode') and message.mode == 1:
                last_ai_message = message
                break
        
        if not last_ai_message:
            Widgets.dialog.show_toast(_("No AI messages to copy"), self)
            return
        
        # Copy to clipboard
        if hasattr(last_ai_message, 'get_content'):
            clipboard = Gdk.Display().get_default().get_clipboard()
            clipboard.set(last_ai_message.get_content())
            Widgets.dialog.show_toast(_("Last response copied to clipboard"), self)
        else:
            Widgets.dialog.show_toast(_("Cannot copy this message"), self)
    
    def toggle_tts_last_message(self):
        """Toggle TTS for the last AI message"""
        current_chat = self.chat_bin.get_child()
        if not current_chat:
            Widgets.dialog.show_toast(_("No active chat"), self)
            return
        
        # Get all messages in the chat
        messages = list(current_chat.container)
        if not messages:
            Widgets.dialog.show_toast(_("No messages available"), self)
            return
        
        # Find the last AI message (mode=1)
        last_ai_message = None
        for message in reversed(messages):
            if hasattr(message, 'mode') and message.mode == 1:
                last_ai_message = message
                break
        
        if not last_ai_message:
            Widgets.dialog.show_toast(_("No AI messages available"), self)
            return
        
        # Toggle TTS button
        if hasattr(last_ai_message, 'popup') and hasattr(last_ai_message.popup, 'tts_button'):
            tts_button = last_ai_message.popup.tts_button
            if hasattr(tts_button, 'button'):
                # It's a stack with a button inside
                tts_button.button.set_active(not tts_button.button.get_active())
            else:
                # It's a direct button
                tts_button.set_active(not tts_button.get_active())
        else:
            Widgets.dialog.show_toast(_("TTS not available for this message"), self)
    
    def cycle_model(self):
        """Cycle through available models in the model selector"""
        model_selector = self.global_footer.model_selector
        if not model_selector:
            Widgets.dialog.show_toast(_("Model selector not available"), self)
            return
        
        # Get the current selection
        current_index = model_selector.selector.get_selected()
        
        # Get the model list
        model_list = Widgets.models.added.model_selector_model
        if not model_list or len(list(model_list)) == 0:
            Widgets.dialog.show_toast(_("No models available"), self)
            return
        
        # Calculate next index (wrap around)
        next_index = (current_index + 1) % len(list(model_list))
        
        # Set the new selection
        model_selector.selector.set_selected(next_index)
        
        # Show toast with the new model name
        selected_item = model_selector.get_selected_item()
        if selected_item and hasattr(selected_item, 'model'):
            model_name = selected_item.model.get_name()
            Widgets.dialog.show_toast(_("Switched to model: {}").format(model_name), self)

    def update_context_indicator(self, chat=None):
        """
        Update the context indicator with token count from the current chat.
        
        Args:
            chat: The chat to get token count from. If None, uses current chat.
        """
        if chat is None:
            chat = self.chat_bin.get_child()
        
        if not chat:
            self.context_indicator_label.set_text('0 tokens')
            self.context_indicator_box.remove_css_class('warning')
            self._hide_context_warning_banner()
            return
        
        try:
            from .services.token_counter import count_chat_tokens, get_token_stats
            
            # Get token count from chat
            token_count = count_chat_tokens(chat)
            
            # Get the model's context limit from the current instance
            context_limit = self._get_model_context_limit()
            
            # Format the display
            if token_count >= 1000000:
                display_text = f'{token_count / 1000000:.1f}M tokens'
            elif token_count >= 1000:
                display_text = f'{token_count / 1000:.1f}K tokens'
            else:
                display_text = f'{token_count} tokens'
            
            self.context_indicator_label.set_text(display_text)
            
            # Calculate usage percentage
            usage_percentage = (token_count / context_limit * 100) if context_limit > 0 else 0
            
            # Update tooltip with more details
            stats = get_token_stats(chat)
            tooltip = _(
                'Context window usage\n'
                'Total tokens: {total} / {limit} ({percentage:.1f}%)\n'
                'Messages: {count}\n'
                'Avg per message: {avg:.1f}'
            ).format(
                total=token_count,
                limit=context_limit,
                percentage=usage_percentage,
                count=stats['message_count'],
                avg=stats['avg_tokens_per_message']
            )
            self.context_indicator_box.set_tooltip_text(tooltip)
            
            # Add warning class and show banner if approaching context limit
            # Warn at 80% of context limit
            warning_threshold = context_limit * 0.8
            
            if token_count >= warning_threshold:
                self.context_indicator_box.add_css_class('warning')
                self._show_context_warning_banner(token_count, context_limit, usage_percentage)
            else:
                self.context_indicator_box.remove_css_class('warning')
                self._hide_context_warning_banner()
                
        except Exception as e:
            logger.warning(f"Error updating context indicator: {e}")
            self.context_indicator_label.set_text('0 tokens')
            self.context_indicator_box.remove_css_class('warning')
            self._hide_context_warning_banner()
    
    def _get_model_context_limit(self) -> int:
        """
        Get the context window limit for the current model.
        
        Returns:
            The context limit in tokens (defaults to 16384 if not available)
        """
        try:
            current_instance = self.get_current_instance()
            if current_instance and hasattr(current_instance, 'properties'):
                # Get num_ctx from instance properties, default to 16384
                return current_instance.properties.get('num_ctx', 16384)
        except Exception as e:
            logger.warning(f"Error getting model context limit: {e}")
        
        # Default context limit if we can't determine it
        return 16384
    
    def _show_context_warning_banner(self, token_count: int, context_limit: int, usage_percentage: float):
        """
        Show a warning banner when approaching context limit.
        
        Args:
            token_count: Current token count
            context_limit: Maximum context limit
            usage_percentage: Percentage of context used
        """
        if not hasattr(self, '_context_warning_banner'):
            # Create the banner if it doesn't exist
            self._context_warning_banner = Adw.Banner()
            self._context_warning_banner.set_button_label(_("Start New Chat"))
            self._context_warning_banner.connect('button-clicked', self._on_context_warning_action)
            
            # Insert banner at the top of the chat content
            chat_content = self.chat_bin.get_parent()
            if chat_content and isinstance(chat_content, Gtk.Box):
                # Find the toast overlay position
                for i, child in enumerate(list(chat_content)):
                    if isinstance(child, Adw.ToastOverlay):
                        chat_content.insert_child_after(self._context_warning_banner, None)
                        break
        
        # Update banner message
        if usage_percentage >= 95:
            message = _(
                'Context limit nearly reached ({percentage:.0f}% used). '
                'Consider starting a new chat to continue the conversation effectively.'
            ).format(percentage=usage_percentage)
        else:
            message = _(
                'Approaching context limit ({percentage:.0f}% used). '
                'You may want to start a new chat soon to maintain response quality.'
            ).format(percentage=usage_percentage)
        
        self._context_warning_banner.set_title(message)
        self._context_warning_banner.set_revealed(True)
    
    def _hide_context_warning_banner(self):
        """Hide the context warning banner."""
        if hasattr(self, '_context_warning_banner'):
            self._context_warning_banner.set_revealed(False)
    
    def _on_context_warning_action(self, banner):
        """
        Handle the action button click on the context warning banner.
        
        Args:
            banner: The banner widget that triggered the action
        """
        # Trigger the new chat action
        self.get_application().lookup_action('new_chat').activate()
    
    def schedule_context_indicator_update(self):
        """
        Schedule a context indicator update after a short delay.
        
        This is useful to batch updates when multiple messages
        are added in quick succession.
        """
        # Use GLib.idle_add to schedule update on next idle cycle
        GLib.timeout_add(500, self._do_context_indicator_update)
    
    def _do_context_indicator_update(self):
        """Internal method to perform the scheduled update."""
        self.update_context_indicator()
        return False  # Don't repeat

    def prepare_screenshoter(self):
        #used to take screenshots of widgets for documentation
        widget = self.get_focus().get_parent()
        while True:
            if 'Alpaca' in repr(widget):
                break
            widget = widget.get_parent()

        widget.unparent()
        Adw.ApplicationWindow(
            width_request=640,
            height_request=10,
            content=widget
        ).present()

    def _setup_keyboard_navigation(self):
        """Set up keyboard navigation enhancements for the main window."""
        try:
            # Enhance keyboard navigation for model flowboxes
            keyboard_navigation.setup_keyboard_navigation_for_flowbox(self.local_model_flowbox)
            keyboard_navigation.setup_keyboard_navigation_for_flowbox(self.available_model_flowbox)
            
            # Enhance keyboard navigation for instance listbox
            keyboard_navigation.setup_keyboard_navigation_for_list(self.instance_listbox)
            
            # Make search entries keyboard accessible
            keyboard_navigation.make_entry_keyboard_accessible(self.searchentry_models)
            keyboard_navigation.make_entry_keyboard_accessible(self.searchentry_messages)
            
            # Add focus indicators to key buttons
            keyboard_navigation.add_focus_css_class(self.new_chat_splitbutton)
            keyboard_navigation.add_focus_css_class(self.model_search_button)
            keyboard_navigation.add_focus_css_class(self.model_filter_button)
            
            # Make context indicator focusable for keyboard users
            keyboard_navigation.make_widget_keyboard_accessible(self.context_indicator_box)
            keyboard_navigation.add_focus_css_class(self.context_indicator_box)
            
            logger.info("Keyboard navigation enhancements applied successfully")
        except Exception as e:
            logger.warning(f"Error setting up keyboard navigation: {e}")

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.activities_page.set_child(Widgets.activities.ActivityManager())

        actions = [[{
            'label': _('New Chat'),
            'callback': lambda: self.get_application().lookup_action('new_chat').activate(),
            'icon': 'chat-message-new-symbolic'
        },{
            'label': _('New Folder'),
            'callback': lambda: self.get_application().lookup_action('new_folder').activate(),
            'icon': 'folder-new-symbolic'
        }]]
        popover = Widgets.dialog.Popover(actions)
        popover.set_has_arrow(True)
        popover.set_halign(0)
        self.new_chat_splitbutton.set_popover(popover)

        self.model_searchbar.connect_entry(self.searchentry_models)
        self.model_searchbar.connect('notify::search-mode-enabled', lambda *_: self.model_search_changed(self.searchentry_models))

        self.set_focus(self.global_footer.message_text_view)
        
        # Set up keyboard navigation enhancements
        self._setup_keyboard_navigation()

        self.settings = Gio.Settings(schema_id="com.jeffser.Alpaca")
        for el in ("default-width", "default-height", "maximized", "hide-on-close"):
            self.settings.bind(el, self, el, Gio.SettingsBindFlags.DEFAULT)

        # Zoom
        Widgets.preferences.set_zoom(Widgets.preferences.get_zoom())

        universal_actions = {
            'new_chat': [lambda *_: self.get_chat_list_page().new_chat(), ['<primary>n']],
            'new_folder': [lambda *_: self.get_chat_list_page().prompt_new_folder(), ['<primary>d']],
            'import_chat': [lambda *_: Widgets.dialog.simple_file(
                parent=self,
                file_filters=[self.file_filter_db],
                callback=self.on_chat_imported
            )],
            'duplicate_current_chat': [lambda *_: self.chat_bin.get_child().row.duplicate()],
            'delete_current_chat': [lambda *_: self.chat_bin.get_child().row.prompt_delete(), ['<primary>w']],
            'edit_current_chat': [lambda *_: self.chat_bin.get_child().row.prompt_edit(), ['F2']],
            'export_current_chat': [lambda *_: self.chat_bin.get_child().row.prompt_export()],
            'toggle_sidebar': [lambda *_: self.split_view_overlay.set_show_sidebar(not self.split_view_overlay.get_show_sidebar()), ['F9']],
            'toggle_search': [lambda *_: self.toggle_searchbar(), ['<primary>f']],
            'global_search': [lambda *_: self.show_global_search(), ['<primary><shift>f']],
            'show_bookmarks': [lambda *_: self.show_bookmarks()],
            'show_prompt_library': [lambda *_: self.show_prompt_library()],
            'statistics_dashboard': [lambda *_: self.show_statistics_dashboard(), ['<primary><shift>s']],
            'show_backup': [lambda *_: self.show_backup()],
            'model_manager' : [lambda *_: self.push_or_pop('model_manager'), ['<primary>m']],
            'instance_manager' : [lambda *_: self.push_or_pop('instance_manager'), ['<primary>i']],
            'add_model_by_name' : [lambda *i: Widgets.dialog.simple_entry(
                parent=self,
                heading=_('Pull Model'),
                body=_('Please enter the model name following this template: name:tag'),
                callback=lambda name: Widgets.models.basic.confirm_pull_model(window=self, model_name=name),
                entries={'placeholder': 'deepseek-r1:7b'}
            )],
            'reload_added_models': [lambda *_: GLib.idle_add(Widgets.models.update_added_model_list, self)],
            'start_quick_ask': [lambda *_: self.get_application().create_quick_ask().present(), ['<primary><alt>a']],
            'model_creator_existing': [lambda *_: Widgets.models.common.prompt_existing(self)],
            'model_creator_gguf': [lambda *_: Widgets.models.common.prompt_gguf(self)],
            'preferences': [lambda *_: Widgets.preferences.PreferencesDialog().present(self), ['<primary>comma']],
            'zoom_in': [lambda *_: Widgets.preferences.zoom_in(), ['<primary>plus']],
            'zoom_out': [lambda *_: Widgets.preferences.zoom_out(), ['<primary>minus']],
            'regenerate_message': [lambda *_: self.regenerate_last_message(), ['<primary>r']],
            'copy_last_response': [lambda *_: self.copy_last_response(), ['<primary><shift>c']],
            'toggle_tts': [lambda *_: self.toggle_tts_last_message(), ['<primary>t']],
            'cycle_model': [lambda *_: self.cycle_model(), ['<primary><shift>m']]
        }
        if os.getenv('ALPACA_ENABLE_SCREENSHOT_ACTION', '0') == '1':
            universal_actions['screenshoter'] = [lambda *_: self.prepare_screenshoter(), ['F3']]

        for action_name, data in universal_actions.items():
            self.get_application().create_action(action_name, data[0], data[1] if len(data) > 1 else None)

        def verify_powersaver_mode():
            self.banner.set_revealed(
                Gio.PowerProfileMonitor.dup_default().get_power_saver_enabled() and
                self.settings.get_value('powersaver-warning').unpack() and
                self.get_current_instance().instance_type == 'ollama:managed'
            )
        Gio.PowerProfileMonitor.dup_default().connect("notify::power-saver-enabled", lambda *_: verify_powersaver_mode())
        self.banner.connect('button-clicked', lambda *_: self.banner.set_revealed(False))

        self.prepare_alpaca()
        if self.settings.get_value('skip-welcome').unpack():
            notice_dialog = Widgets.welcome.Notice()
            if not self.settings.get_value('last-notice-seen').unpack() == notice_dialog.get_name():
                notice_dialog.present(self)
        else:
            self.main_navigation_view.replace([Widgets.welcome.Welcome()])

