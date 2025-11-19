# ollama_instances.py

from gi.repository import Adw, Gtk, GLib

import requests, json, logging, os, shutil, subprocess, threading, re, signal, pwd, getpass
from .. import dialog, tools, chat
from ...ollama_models import OLLAMA_MODELS
from ...constants import data_dir, cache_dir, TITLE_GENERATION_PROMPT_OLLAMA, MAX_TOKENS_TITLE_GENERATION
from ...sql_manager import generate_uuid, dict_to_metadata_string, Instance as SQL
from ...core.process_manager import ProcessManager, ProcessConfig
from ...core.error_handler import ErrorHandler, ErrorCategory
from ...core.network_client import NetworkClient, NetworkError, NetworkStatus

logger = logging.getLogger(__name__)

# Base instance, don't use directly
class BaseInstance:
    description = None
    process = None
    _network_client = None

    def get_network_client(self) -> NetworkClient:
        """Get or create NetworkClient for this instance."""
        if self._network_client is None:
            self._network_client = NetworkClient(
                base_url=self.properties.get('url'),
                timeout=30,
                streaming_timeout=300
            )
        return self._network_client

    def prepare_chat(self, bot_message):
        chat_element = bot_message.get_ancestor(chat.Chat)
        if chat_element and chat_element.chat_id:
            chat_element.row.spinner.set_visible(True)
            try:
                bot_message.get_root().global_footer.toggle_action_button(False)
            except:
                pass

            chat_element.busy = True
            chat_element.set_visible_child_name('content')

        messages = chat_element.convert_to_ollama()[:list(chat_element.container).index(bot_message)]
        return chat_element, messages

    def generate_message(self, bot_message, model:str):
        chat, messages = self.prepare_chat(bot_message)

        if chat.chat_id and [m.get('role') for m in messages].count('assistant') == 0 and chat.get_name().startswith(_("New Chat")):
            threading.Thread(
                target=self.generate_chat_title,
                args=(
                    chat,
                    messages[-1].get('content'),
                    model
                ),
                daemon=True
            ).start()
        self.generate_response(bot_message, chat, messages, model)

    def use_tools(self, bot_message, model:str, available_tools:dict, generate_message:bool):
        chat, messages = self.prepare_chat(bot_message)
        bot_message.block_container.prepare_generating_block()

        if chat.chat_id and [m.get('role') for m in messages].count('assistant') == 0 and chat.get_name().startswith(_("New Chat")):
            threading.Thread(
                target=self.generate_chat_title,
                args=(
                    chat,
                    messages[-1].get('content'),
                    model
                ),
                daemon=True
            ).start()

        message_response = ''
        try:
            params = {
                "model": model,
                "messages": messages,
                "stream": False,
                "tools": [v.get_metadata() for v in available_tools.values()],
                "think": False
            }
            
            client = self.get_network_client()
            # Prepare headers
            headers = {
                "Content-Type": "application/json"
            }
            if self.properties.get('api'):
                headers["Authorization"] = "Bearer {}".format(self.properties.get('api'))
            
            # Make request with NetworkClient
            client.session.headers.update(headers)
            response = client.post('api/chat', json=params, stream=False)
            tool_calls = response.json().get('message', {}).get('tool_calls', [])
            for tc in tool_calls:
                function = tc.get('function')
                if available_tools.get(function.get('name')):
                    message_response, tool_response = available_tools.get(function.get('name')).run(function.get('arguments'), messages, bot_message)
                    generate_message = generate_message and not bool(message_response)

                    attachment_content = []

                    if len(function.get('arguments', {})) > 0:
                        attachment_content += [
                            '## {}'.format(_('Arguments')),
                            '| {} | {} |'.format(_('Argument'), _('Value')),
                            '| --- | --- |'
                        ]
                        attachment_content += ['| {} | {} |'.format(k, v) for k, v in function.get('arguments', {}).items()]

                    attachment_content += [
                        '## {}'.format(_('Result')),
                        str(tool_response)
                    ]

                    attachment = bot_message.add_attachment(
                        file_id = generate_uuid(),
                        name = available_tools.get(function.get('name')).display_name,
                        attachment_type = 'tool',
                        content = '\n'.join(attachment_content)
                    )
                    SQL.insert_or_update_attachment(bot_message, attachment)
                    messages.append({
                        'role': 'assistant',
                        'content': '',
                    })
                    messages.append({
                        'role': 'tool',
                        'content': str(tool_response)
                    })
        except Exception as e:
            dialog.simple_error(
                parent = bot_message.get_root(),
                title = _('Tool Error'),
                body = _('An error occurred while running tool'),
                error_log = e
            )
            logger.error(e)

        if generate_message:
            self.generate_response(bot_message, chat, messages, model)
        else:
            bot_message.block_container.set_content(str(message_response))
            bot_message.finish_generation('')

    def generate_response(self, bot_message, chat, messages:list, model:str):
        bot_message.block_container.prepare_generating_block()

        if self.properties.get('share_name', 0) > 0:
            user_display_name = None
            if self.properties.get('share_name') == 1:
                user_display_name = getpass.getuser().title()
            elif self.properties.get('share_name') == 2:
                gecos_temp = pwd.getpwnam(getpass.getuser()).pw_gecos.split(',')
                if len(gecos_temp) > 0:
                    user_display_name = pwd.getpwnam(getpass.getuser()).pw_gecos.split(',')[0].title()

            if user_display_name:
                messages.insert(0, {
                    'role': 'system',
                    'content': 'The user is called {}'.format(user_display_name)
                })

        model_info = self.get_model_info(model)
        if model_info:
            if model_info.get('system'):
                messages.insert(0, {
                    'role': 'system',
                    'content': model_info.get('system')
                })

        params = {
            "model": model,
            "messages": messages,
            "stream": True,
            "think": self.properties.get('think', False) and 'thinking' in model_info.get('capabilities', []),
            "keep_alive": self.properties.get('keep_alive', 300)
        }

        if self.properties.get("override_parameters"):
            params["options"] = {}
            params["options"]["temperature"] = self.properties.get('temperature', 0.7)
            params["options"]["num_ctx"] = self.properties.get('num_ctx', 16384)
            if self.properties.get('seed', 0) != 0:
                params["options"]["seed"] = self.properties.get('seed')

        data = {'done': True}
        if chat.busy:
            try:
                client = self.get_network_client()
                
                # Prepare headers
                headers = {
                    "Content-Type": "application/json"
                }
                if self.properties.get('api'):
                    headers["Authorization"] = "Bearer {}".format(self.properties.get('api'))
                
                # Update session headers
                client.session.headers.update(headers)
                
                # Make streaming request with NetworkClient
                response = client.post('api/chat', json=params, stream=True)
                bot_message.block_container.clear()
                
                if response.status_code == 200:
                    for line in response.iter_lines():
                        if line:
                            data = json.loads(line.decode('utf-8'))
                            bot_message.update_message(data.get('message', {}).get('content'))
                        if not chat.busy or data.get('done'):
                            break
                else:
                    response_json = response.json()
                    if response_json.get('error') == 'unauthorized' and response_json.get('signin_url'):
                        attachment = bot_message.add_attachment(
                            file_id = generate_uuid(),
                            name = 'Ollama Login',
                            attachment_type = 'link',
                            content = response_json.get('signin_url')
                        )
                        SQL.insert_or_update_attachment(bot_message, attachment)
                        bot_message.update_message("🦙 Just a quick heads-up! To access the Ollama cloud models, you'll need to log into your Ollama account first.")
                    logger.error(response.content)
            except NetworkError as e:
                # Handle network-specific errors
                ErrorHandler.handle_exception(
                    exception=e,
                    context="BaseInstance.generate_response",
                    user_message=_("Network error during message generation. Please check your connection."),
                    show_dialog=True,
                    parent_widget=bot_message.get_root()
                )
                if self.row:
                    self.row.get_parent().unselect_all()
            except Exception as e:
                dialog.simple_error(
                    parent = bot_message.get_root(),
                    title = _('Instance Error'),
                    body = _('Message generation failed'),
                    error_log = e
                )
                logger.error(e)
                if self.row:
                    self.row.get_parent().unselect_all()
        metadata_string = None
        if self.properties.get('show_response_metadata'):
            metadata_string = dict_to_metadata_string(data)
        bot_message.finish_generation(metadata_string)

    def generate_chat_title(self, chat, prompt:str, fallback_model:str):
        if not chat.row or not chat.row.get_parent():
            return
        model = self.get_title_model()
        params = {
            "options": {
                "temperature": 0.2
            },
            "model": model or fallback_model,
            "max_tokens": MAX_TOKENS_TITLE_GENERATION,
            "stream": False,
            "messages": [
                {
                    "role": "user",
                    "content": '{}\n\n{}'.format(TITLE_GENERATION_PROMPT_OLLAMA, prompt)
                }
            ],
            "format": {
                "type": "object",
                "properties": {
                    "title": {
                        "type": "string"
                    },
                    "emoji": {
                        "type": "string"
                    }
                },
                "required": [
                    "title"
                ]
            },
            'think': False,
            "keep_alive": 0
        }
        if self.properties.get("override_parameters"):
            params["options"]["num_ctx"] = self.properties.get('num_ctx', 16384)
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {
                "Content-Type": "application/json"
            }
            if self.properties.get('api'):
                headers["Authorization"] = "Bearer {}".format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Make request with NetworkClient
            response = client.post('api/chat', json=params, stream=False)
            data = json.loads(response.json().get('message', {}).get('content', '{"title": "New Chat"}'))
            generated_title = data.get('title').replace('\n', '').strip()

            if len(generated_title) > 30:
                generated_title = generated_title[:30].strip() + '...'

            if data.get('emoji'):
                chat.row.edit(
                    new_name='{} {}'.format(data.get('emoji').replace('\n', '').strip(), generated_title),
                    is_template=chat.is_template
                )
            else:
                chat.row.edit(
                    new_name=generated_title,
                    is_template=chat.is_template
                )
        except Exception as e:
            logger.error(e)


    def get_default_model(self):
        local_models = self.get_local_models()
        if len(local_models) > 0:
            if not self.properties.get('default_model') or not self.properties.get('default_model') in [m.get('name') for m in local_models]:
                self.properties['default_model'] = local_models[0].get('name')
            return self.properties.get('default_model')

    def get_title_model(self):
        local_models = self.get_local_models()
        if len(local_models) > 0:
            if self.properties.get('title_model') and not self.properties.get('title_model') in [m.get('name') for m in local_models]:
                self.properties['title_model'] = local_models[0].get('name')
            return self.properties.get('title_model')

    def stop(self):
        pass

    def start(self):
        pass

    def get_local_models(self) -> list:
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {}
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Make request with NetworkClient
            response = client.get('api/tags')
            if response.status_code == 200:
                return json.loads(response.text).get('models')
        except NetworkError as e:
            # Handle network-specific errors
            ErrorHandler.handle_exception(
                exception=e,
                context="BaseInstance.get_local_models",
                user_message=_("Could not retrieve models. Please check your connection."),
                show_dialog=True,
                parent_widget=self.row.get_root() if self.row else None
            )
            if self.row:
                self.row.get_parent().unselect_all()
        except Exception as e:
            dialog.simple_error(
                parent = self.row.get_root() if self.row else None,
                title = _('Instance Error'),
                body = _('Could not retrieve added models'),
                error_log = e
            )
            logger.error(e)
            if self.row:
                self.row.get_parent().unselect_all()
        return []

    def get_available_models(self) -> dict:
        try:
            return OLLAMA_MODELS
        except Exception as e:
            dialog.simple_error(
                parent = self.row.get_root() if self.row else None,
                title = _('Instance Error'),
                body = _('Could not retrieve available models'),
                error_log = e
            )
            logger.error(e)
        return {}

    def get_model_info(self, model_name:str) -> dict:
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json'
            }
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Make request with NetworkClient
            response = client.post('api/show', json={"name": model_name}, stream=False)
            if response.status_code == 200:
                return json.loads(response.text)
        except NetworkError as e:
            # Log network errors but don't show dialog (this is called frequently)
            logger.warning(f"Network error getting model info for {model_name}: {e}")
        except Exception as e:
            logger.error(e)
        return {}

    def pull_model(self, model):
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json'
            }
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Make streaming request with NetworkClient
            response = client.post(
                'api/pull',
                json={'name': model.get_name(), 'stream': True},
                stream=True
            )
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line.decode("utf-8"))
                        if data.get('status'):
                            model.append_progress_line(data.get('status'))
                        if data.get('total') and data.get('completed'):
                            model.update_progressbar(data.get('completed') / data.get('total'))
                        if data.get('status') == 'success':
                            model.update_progressbar(-1)
                            return
        except NetworkError as e:
            # Handle network errors during model pull
            ErrorHandler.log_error(
                message=f"Network error pulling model {model.get_name()}",
                exception=e,
                context={'model': model.get_name()}
            )
            model.get_parent().get_parent().remove(model.get_parent())
        except Exception as e:
            model.get_parent().get_parent().remove(model.get_parent())
            logger.error(e)

    def gguf_exists(self, sha256:str) -> bool:
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {}
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Use session.head for HEAD request
            response = client.session.head(
                f"{client.base_url}/api/blobs/sha256:{sha256}",
                timeout=client.timeout
            )
            return response.status_code == 200
        except Exception as e:
            logger.warning(f"Error checking if GGUF exists: {e}")
            return False

    def upload_gguf(self, gguf_path:str, sha256:str):
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {}
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Upload file with NetworkClient
            with open(gguf_path, 'rb') as f:
                client.post(f'api/blobs/sha256:{sha256}', data=f, stream=False)
        except NetworkError as e:
            ErrorHandler.log_error(
                message=f"Network error uploading GGUF file",
                exception=e,
                context={'gguf_path': gguf_path, 'sha256': sha256}
            )
            raise
        except Exception as e:
            logger.error(f"Error uploading GGUF: {e}")
            raise

    def create_model(self, data:dict, model):
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json'
            }
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Make streaming request with NetworkClient
            response = client.post('api/create', json=data, stream=True)
            if response.status_code == 200:
                for line in response.iter_lines():
                    if line:
                        data = json.loads(line.decode("utf-8"))
                        if data.get('status'):
                            model.append_progress_line(data.get('status'))
                        if data.get('total') and data.get('completed'):
                            model.update_progressbar(data.get('completed') / data.get('total'))
                        if data.get('status') == 'success':
                            model.update_progressbar(-1)
                            return
        except NetworkError as e:
            # Handle network errors during model creation
            ErrorHandler.log_error(
                message=f"Network error creating model",
                exception=e,
                context={'model': model}
            )
            model.get_parent().get_parent().remove(model.get_parent())
        except Exception as e:
            model.get_parent().get_parent().remove(model.get_parent())
            logger.error(e)

    def delete_model(self, model_name:str):
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {
                'Content-Type': 'application/json'
            }
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Use session.delete for DELETE request
            response = client.session.delete(
                f"{client.base_url}/api/delete",
                json={"name": model_name},
                timeout=client.timeout
            )
            return response.status_code == 200
        except NetworkError as e:
            ErrorHandler.log_error(
                message=f"Network error deleting model {model_name}",
                exception=e,
                context={'model_name': model_name}
            )
            return False
        except Exception as e:
            logger.error(f"Error deleting model: {e}")
            return False


class OllamaManaged(BaseInstance):
    instance_type = 'ollama:managed'
    instance_type_display = _('Ollama (Managed)')
    description = _('Local AI instance managed directly by Alpaca')

    default_properties = {
        'name': _('Instance'),
        'url': 'http://0.0.0.0:11434',
        'override_parameters': True,
        'temperature': 0.7,
        'seed': 0,
        'num_ctx': 16384,
        'keep_alive': 300,
        'model_directory': os.path.join(data_dir, '.ollama', 'models'),
        'default_model': None,
        'title_model': None,
        'overrides': {
            'HSA_OVERRIDE_GFX_VERSION': '',
            'CUDA_VISIBLE_DEVICES': '0',
            'ROCR_VISIBLE_DEVICES': '1',
            'HIP_VISIBLE_DEVICES': '1'
        },
        'think': False,
        'expose': False,
        'share_name': 0,
        'show_response_metadata': False
    }

    def __init__(self, instance_id:str, properties:dict):
        self.instance_id = instance_id
        self.process_manager = ProcessManager(enable_health_monitor=True)
        self.process = None  # Keep for backward compatibility
        self.log_raw = ''
        self.log_summary = ('', ['dim-label'])
        self.properties = {}
        self.row = None

        # Register crash callback
        self.process_manager.register_crash_callback(self._on_process_crash)

        for key in self.default_properties:
            if key == 'overrides':
                self.properties[key] = {}
                for override in self.default_properties.get(key):
                    self.properties[key][override] = properties.get(key, {}).get(override, self.default_properties.get(key).get(override))
            else:
                self.properties[key] = properties.get(key, self.default_properties.get(key))

    def _on_process_crash(self):
        """Callback invoked when the Ollama process crashes."""
        logger.error("Ollama process crashed")
        self.log_summary = (_("Integrated Ollama instance crashed"), ['dim-label', 'error'])
        self.process = None

        # Notify user if row is available
        if self.row:
            try:
                GLib.idle_add(
                    dialog.show_toast,
                    _("Ollama instance crashed unexpectedly"),
                    self.row.get_root()
                )
            except Exception as e:
                logger.error(f"Failed to show crash notification: {e}")

    def log_output(self, pipe):
        AMD_support_label = "\n<a href='https://github.com/Jeffser/Alpaca/wiki/Installing-Ollama'>{}</a>".format(_('Alpaca Support'))
        with pipe:
            try:
                for line in iter(pipe.readline, b''):
                    # Decode bytes to string
                    line_str = line.decode('utf-8', errors='replace') if isinstance(line, bytes) else line
                    self.log_raw += line_str
                    print(line_str, end='')
                    if 'msg="model request too large for system"' in line_str and self.row:
                        dialog.show_toast(_("Model request too large for system"), self.row.get_root())
                    elif 'msg="amdgpu detected, but no compatible rocm library found.' in line_str:
                        if bool(os.getenv("FLATPAK_ID")):
                            self.log_summary = (_("AMD GPU detected but the extension is missing, Ollama will use CPU.") + AMD_support_label, ['dim-label', 'error'])
                        else:
                            self.log_summary = (_("AMD GPU detected but ROCm is missing, Ollama will use CPU.") + AMD_support_label, ['dim-label', 'error'])
                    elif 'msg="amdgpu is supported"' in line_str:
                        self.log_summary = (_("Using AMD GPU type '{}'").format(line_str.split('=')[-1].replace('\n', '')), ['dim-label', 'success'])
            except Exception as e:
                ErrorHandler.log_error(
                    message="Error reading Ollama process output",
                    exception=e,
                    context={'instance_id': self.instance_id}
                )

    def stop(self):
        """Stop the Ollama instance using ProcessManager."""
        if self.process_manager.is_running():
            logger.info("Stopping Alpaca's Ollama instance")
            try:
                success = self.process_manager.stop(timeout=5)
                if success:
                    self.process = None
                    self.log_summary = (_("Integrated Ollama instance is not running"), ['dim-label'])
                    logger.info("Stopped Alpaca's Ollama instance")
                else:
                    error_msg = "Failed to stop Ollama instance"
                    logger.error(error_msg)
                    ErrorHandler.log_error(
                        message=error_msg,
                        context={'instance_id': self.instance_id}
                    )
            except Exception as e:
                ErrorHandler.handle_exception(
                    exception=e,
                    context="OllamaManaged.stop",
                    user_message=_("Failed to stop Ollama instance"),
                    show_dialog=False,
                    parent_widget=self.row.get_root() if self.row else None
                )
                self.process = None
                self.log_summary = (_("Integrated Ollama instance is not running"), ['dim-label'])

    def start(self):
        """Start the Ollama instance using ProcessManager."""
        if not shutil.which('ollama'):
            error_msg = "Ollama executable not found in PATH"
            logger.error(error_msg)
            ErrorHandler.log_error(
                message=error_msg,
                context={'instance_id': self.instance_id}
            )
            if self.row:
                dialog.simple_error(
                    parent=self.row.get_root(),
                    title=_('Instance Error'),
                    body=_('Ollama is not installed or not in PATH'),
                    error_log=None
                )
            return

        if self.process_manager.is_running():
            logger.info("Ollama instance already running")
            return

        try:
            # Prepare environment variables
            params = self.properties.get('overrides', {}).copy()
            params["OLLAMA_HOST"] = self.properties.get('url')
            params["OLLAMA_MODELS"] = self.properties.get('model_directory')
            if self.properties.get("expose"):
                params["OLLAMA_ORIGINS"] = "chrome-extension://*,moz-extension://*,safari-web-extension://*,http://0.0.0.0,http://127.0.0.1"
            else:
                params["OLLAMA_ORIGINS"] = params.get("OLLAMA_HOST")

            # Remove empty parameters
            for key in list(params):
                if not params.get(key):
                    del params[key]

            # Merge with current environment
            env = {**os.environ, **params}

            # Create process configuration
            config = ProcessConfig(
                command=["ollama", "serve"],
                env=env,
                timeout=30
            )

            logger.info("Starting Alpaca's Ollama instance...")

            # Start the process using ProcessManager
            success = self.process_manager.start(config)

            if success:
                # Get the underlying process for log output (temporary compatibility)
                # Note: This accesses a private member, which is not ideal but needed for log_output
                self.process = self.process_manager._process

                if self.process:
                    # Start log monitoring threads
                    threading.Thread(target=self.log_output, args=(self.process.stdout,), daemon=True).start()
                    threading.Thread(target=self.log_output, args=(self.process.stderr,), daemon=True).start()

                logger.info("Started Alpaca's Ollama instance")

                # Log Ollama version
                try:
                    v_str = subprocess.check_output("ollama -v", shell=True).decode('utf-8')
                    logger.info(v_str.split('\n')[1].strip('Warning: ').strip())
                except Exception as e:
                    logger.warning(f"Could not get Ollama version: {e}")

                self.log_summary = (_("Integrated Ollama instance is running"), ['dim-label', 'success'])
            else:
                raise Exception("ProcessManager failed to start Ollama")

        except Exception as e:
            ErrorHandler.handle_exception(
                exception=e,
                context="OllamaManaged.start",
                user_message=_("Managed Ollama instance failed to start"),
                show_dialog=True,
                parent_widget=self.row.get_root() if self.row else None
            )

            if self.row:
                dialog.simple_error(
                    parent=self.row.get_root(),
                    title=_('Instance Error'),
                    body=_('Managed Ollama instance failed to start'),
                    error_log=e
                )
                self.row.get_parent().unselect_all()

            self.log_summary = (_("Integrated Ollama instance failed to start"), ['dim-label', 'error'])

class Ollama(BaseInstance):
    instance_type = 'ollama'
    instance_type_display = _('Ollama (External)')
    description = _('Local or remote AI instance not managed by Alpaca')

    default_properties = {
        'name': _('Instance'),
        'url': 'http://0.0.0.0:11434',
        'api': '',
        'override_parameters': True,
        'temperature': 0.7,
        'seed': 0,
        'num_ctx': 16384,
        'keep_alive': 300,
        'default_model': None,
        'title_model': None,
        'think': False,
        'share_name': 0,
        'show_response_metadata': False
    }

    def __init__(self, instance_id:str, properties:dict):
        self.instance_id = instance_id
        self.properties = {}
        self.row = None
        for key in self.default_properties:
            self.properties[key] = properties.get(key, self.default_properties.get(key))

class OllamaCloud(BaseInstance):
    instance_type = 'ollama:cloud'
    instance_type_display = _('Ollama (Cloud)')
    description = _('Online instance directly managed by Ollama (Experimental)')

    default_properties = {
        'name': _('Instance'),
        'url': 'https://ollama.com',
        'api': '',
        'override_parameters': True,
        'temperature': 0.7,
        'seed': 0,
        'num_ctx': 16384,
        'default_model': None,
        'title_model': None,
        'think': False,
        'share_name': 0,
        'show_response_metadata': False
    }

    def __init__(self, instance_id:str, properties:dict):
        self.instance_id = instance_id
        self.properties = {}
        self.row = None
        for key in self.default_properties:
            self.properties[key] = properties.get(key, self.default_properties.get(key))

    def pull_model(self, model):
        SQL.append_online_instance_model_list(self.instance_id, model.get_name())
        GLib.timeout_add(5000, lambda: model.update_progressbar(-1) and False)

    def delete_model(self, model_name:str) -> bool:
        SQL.remove_online_instance_model_list(self.instance_id, model_name)
        return True

    def get_local_models(self) -> list:
        local_models = []
        for model in SQL.get_online_instance_model_list(self.instance_id):
            local_models.append({'name': model})
        return local_models

    def get_available_models(self) -> dict:
        if not self.process:
            self.start()
        try:
            client = self.get_network_client()
            
            # Prepare headers
            headers = {}
            if self.properties.get('api'):
                headers['Authorization'] = 'Bearer {}'.format(self.properties.get('api'))
            
            # Update session headers
            client.session.headers.update(headers)
            
            # Make request with NetworkClient
            response = client.get('api/tags')
            if response.status_code == 200:
                available_models = {}

                for model in [m.get('model') for m in response.json().get('models', [])]:
                    if ':' in model:
                        model_name, model_tag = model.split(':')
                    else:
                        model_name, model_tag = model, ''

                    if not available_models.get(model_name):
                        model_metadata = OLLAMA_MODELS.get(model_name)
                        if model_metadata:
                            available_models[model_name] = {
                                'url': model_metadata.get('url'),
                                'tags': [],
                                'author': model_metadata.get('author'),
                                'categories': model_metadata.get('categories'),
                                'languages': model_metadata.get('languages'),
                                'description': model_metadata.get('description')
                            }
                        else:
                            available_models[model_name] = {
                                'tags': [],
                                'categories': ['cloud']
                            }

                    available_models[model_name]['tags'].append([model_tag, 'cloud'])

                return available_models
        except NetworkError as e:
            # Handle network-specific errors
            ErrorHandler.handle_exception(
                exception=e,
                context="OllamaCloud.get_available_models",
                user_message=_("Could not retrieve models. Please check your connection."),
                show_dialog=True,
                parent_widget=self.row.get_root() if self.row else None
            )
            if self.row:
                self.row.get_parent().unselect_all()
        except Exception as e:
            dialog.simple_error(
                parent = self.row.get_root() if self.row else None,
                title = _('Instance Error'),
                body = _('Could not retrieve added models'),
                error_log = e
            )
            logger.error(e)
            if self.row:
                self.row.get_parent().unselect_all()
        return {}
