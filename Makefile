# Makefile for Alpaca
# Simple alternative to meson build system

# Configuration
PREFIX ?= /usr/local
BINDIR = $(PREFIX)/bin
DATADIR = $(PREFIX)/share
LOCALEDIR = $(PREFIX)/share/locale
PKGDATADIR = $(DATADIR)/Alpaca
MODULEDIR = $(PKGDATADIR)/alpaca
APPID = com.jeffser.Alpaca
VERSION = 8.3.1

# Python
PYTHON ?= python3

# Tools
BLUEPRINT_COMPILER = blueprint-compiler
GLIB_COMPILE_RESOURCES = glib-compile-resources
GLIB_COMPILE_SCHEMAS = glib-compile-schemas
MSGFMT = msgfmt
DESKTOP_FILE_VALIDATE = desktop-file-validate
APPSTREAMCLI = appstreamcli

# Source files
SRC_DIR = src
DATA_DIR = data
PO_DIR = po
ICONS_DIR = $(DATA_DIR)/icons

# Python source files to install
PYTHON_SOURCES = \
	main.py \
	window.py \
	quick_ask.py \
	constants.py \
	ollama_models.py \
	sql_manager.py

# Directories
BUILD_DIR = build
UI_BUILD_DIR = $(BUILD_DIR)/ui

.PHONY: all build install uninstall clean test help

all: build

help:
	@echo "Alpaca Makefile"
	@echo ""
	@echo "Targets:"
	@echo "  all        - Build everything (default)"
	@echo "  build      - Compile blueprints and resources"
	@echo "  install    - Install to PREFIX (default: /usr/local)"
	@echo "  uninstall  - Remove installed files"
	@echo "  clean      - Remove build artifacts"
	@echo "  test       - Run tests"
	@echo "  dev        - Run in development mode"
	@echo ""
	@echo "Variables:"
	@echo "  PREFIX     - Installation prefix (default: /usr/local)"
	@echo "  DESTDIR    - Staging directory for package building"

# Build targets
build: $(BUILD_DIR)/alpaca.gresource $(BUILD_DIR)/alpaca $(BUILD_DIR)/alpaca_search_provider

# Create build directory
$(BUILD_DIR):
	mkdir -p $(BUILD_DIR)
	mkdir -p $(UI_BUILD_DIR)

# Compile blueprint files
$(UI_BUILD_DIR)/.blueprints: $(BUILD_DIR)
	@echo "Compiling blueprint files..."
	@mkdir -p $(UI_BUILD_DIR)/widgets/instances
	@mkdir -p $(UI_BUILD_DIR)/widgets/message
	@mkdir -p $(UI_BUILD_DIR)/widgets/chat
	@mkdir -p $(UI_BUILD_DIR)/widgets/models
	@mkdir -p $(UI_BUILD_DIR)/widgets/blocks
	@mkdir -p $(UI_BUILD_DIR)/widgets/activities
	$(BLUEPRINT_COMPILER) batch-compile $(UI_BUILD_DIR) $(SRC_DIR) \
		$(SRC_DIR)/ui/notice.blp \
		$(SRC_DIR)/ui/preferences.blp \
		$(SRC_DIR)/ui/quick_ask.blp \
		$(SRC_DIR)/ui/shortcuts.blp \
		$(SRC_DIR)/ui/welcome.blp \
		$(SRC_DIR)/ui/window.blp \
		$(SRC_DIR)/ui/widgets/instances/preferences.blp \
		$(SRC_DIR)/ui/widgets/message/popup.blp \
		$(SRC_DIR)/ui/widgets/message/message.blp \
		$(SRC_DIR)/ui/widgets/chat/folder.blp \
		$(SRC_DIR)/ui/widgets/chat/template_selector.blp \
		$(SRC_DIR)/ui/widgets/chat/chat.blp \
		$(SRC_DIR)/ui/widgets/chat/folder_row.blp \
		$(SRC_DIR)/ui/widgets/chat/chat_row.blp \
		$(SRC_DIR)/ui/widgets/models/added_dialog.blp \
		$(SRC_DIR)/ui/widgets/models/basic_dialog.blp \
		$(SRC_DIR)/ui/widgets/models/basic_button.blp \
		$(SRC_DIR)/ui/widgets/models/pulling_dialog.blp \
		$(SRC_DIR)/ui/widgets/models/available_dialog.blp \
		$(SRC_DIR)/ui/widgets/models/creator_dialog.blp \
		$(SRC_DIR)/ui/widgets/models/info_box.blp \
		$(SRC_DIR)/ui/widgets/models/category_pill.blp \
		$(SRC_DIR)/ui/widgets/models/added_selector.blp \
		$(SRC_DIR)/ui/widgets/blocks/code.blp \
		$(SRC_DIR)/ui/widgets/blocks/latex_renderer.blp \
		$(SRC_DIR)/ui/widgets/blocks/table.blp \
		$(SRC_DIR)/ui/widgets/blocks/editing_text.blp \
		$(SRC_DIR)/ui/widgets/blocks/generating_text.blp \
		$(SRC_DIR)/ui/widgets/activities/web_browser.blp \
		$(SRC_DIR)/ui/widgets/activities/background_remover.blp \
		$(SRC_DIR)/ui/widgets/activities/background_remover_image.blp \
		$(SRC_DIR)/ui/widgets/activities/camera.blp
	@touch $(UI_BUILD_DIR)/.blueprints

# Compile GResource
$(BUILD_DIR)/alpaca.gresource: $(UI_BUILD_DIR)/.blueprints
	@echo "Compiling GResource..."
	cd $(SRC_DIR) && $(GLIB_COMPILE_RESOURCES) --sourcedir=../$(UI_BUILD_DIR) \
		--sourcedir=. \
		--target=../$(BUILD_DIR)/alpaca.gresource \
		alpaca.gresource.xml

# Generate main executable script
$(BUILD_DIR)/alpaca: $(SRC_DIR)/alpaca.py.in $(BUILD_DIR)
	@echo "Generating alpaca executable..."
	sed -e 's|@PYTHON@|$(PYTHON)|g' \
	    -e 's|@VERSION@|$(VERSION)|g' \
	    -e 's|@localedir@|$(LOCALEDIR)|g' \
	    -e 's|@pkgdatadir@|$(PKGDATADIR)|g' \
	    $(SRC_DIR)/alpaca.py.in > $(BUILD_DIR)/alpaca
	chmod +x $(BUILD_DIR)/alpaca

# Generate search provider script
$(BUILD_DIR)/alpaca_search_provider: $(SRC_DIR)/alpaca_search_provider.py.in $(BUILD_DIR)
	@echo "Generating alpaca_search_provider executable..."
	sed -e 's|@PYTHON@|$(PYTHON)|g' \
	    -e 's|@VERSION@|$(VERSION)|g' \
	    -e 's|@localedir@|$(LOCALEDIR)|g' \
	    -e 's|@pkgdatadir@|$(PKGDATADIR)|g' \
	    $(SRC_DIR)/alpaca_search_provider.py.in > $(BUILD_DIR)/alpaca_search_provider
	chmod +x $(BUILD_DIR)/alpaca_search_provider

# Generate desktop files
$(BUILD_DIR)/$(APPID).desktop: $(DATA_DIR)/$(APPID).desktop.in $(BUILD_DIR)
	@echo "Generating desktop file..."
	msgfmt --desktop --template=$(DATA_DIR)/$(APPID).desktop.in \
		-d $(PO_DIR) -o $(BUILD_DIR)/$(APPID).desktop

$(BUILD_DIR)/$(APPID).SearchProvider.desktop: $(DATA_DIR)/$(APPID).SearchProvider.desktop.in $(BUILD_DIR)
	@echo "Generating search provider desktop file..."
	msgfmt --desktop --template=$(DATA_DIR)/$(APPID).SearchProvider.desktop.in \
		-d $(PO_DIR) -o $(BUILD_DIR)/$(APPID).SearchProvider.desktop

# Generate metainfo file
$(BUILD_DIR)/$(APPID).metainfo.xml: $(DATA_DIR)/$(APPID).metainfo.xml.in $(BUILD_DIR)
	@echo "Generating metainfo file..."
	msgfmt --xml --template=$(DATA_DIR)/$(APPID).metainfo.xml.in \
		-d $(PO_DIR) -o $(BUILD_DIR)/$(APPID).metainfo.xml

# Generate service file
$(BUILD_DIR)/$(APPID).SearchProvider.service: $(DATA_DIR)/$(APPID).SearchProvider.service.in $(BUILD_DIR)
	@echo "Generating D-Bus service file..."
	sed -e 's|@appid@|$(APPID)|g' \
	    -e 's|@name@|Alpaca|g' \
	    -e 's|@bindir@|$(BINDIR)|g' \
	    $(DATA_DIR)/$(APPID).SearchProvider.service.in > $(BUILD_DIR)/$(APPID).SearchProvider.service

# Generate search provider config
$(BUILD_DIR)/$(APPID).search-provider.ini: $(DATA_DIR)/$(APPID).search-provider.ini $(BUILD_DIR)
	@echo "Generating search provider config..."
	sed -e 's|@appid@|$(APPID)|g' \
	    -e 's|@object_path@|/com/jeffser/Alpaca/SearchProvider|g' \
	    $(DATA_DIR)/$(APPID).search-provider.ini > $(BUILD_DIR)/$(APPID).search-provider.ini

# Install target
install: build $(BUILD_DIR)/$(APPID).desktop $(BUILD_DIR)/$(APPID).SearchProvider.desktop \
         $(BUILD_DIR)/$(APPID).metainfo.xml $(BUILD_DIR)/$(APPID).SearchProvider.service \
         $(BUILD_DIR)/$(APPID).search-provider.ini
	@echo "Installing Alpaca to $(DESTDIR)$(PREFIX)..."
	
	# Install executables
	install -Dm755 $(BUILD_DIR)/alpaca $(DESTDIR)$(BINDIR)/alpaca
	install -Dm755 $(BUILD_DIR)/alpaca_search_provider $(DESTDIR)$(BINDIR)/alpaca_search_provider
	
	# Install Python modules
	install -d $(DESTDIR)$(MODULEDIR)
	install -d $(DESTDIR)$(MODULEDIR)/widgets
	install -d $(DESTDIR)$(MODULEDIR)/widgets/activities
	install -d $(DESTDIR)$(MODULEDIR)/widgets/blocks
	install -d $(DESTDIR)$(MODULEDIR)/widgets/instances
	install -d $(DESTDIR)$(MODULEDIR)/widgets/models
	install -d $(DESTDIR)$(MODULEDIR)/widgets/tools
	install -d $(DESTDIR)$(MODULEDIR)/core
	install -d $(DESTDIR)$(MODULEDIR)/repositories
	install -d $(DESTDIR)$(MODULEDIR)/services
	
	for file in $(PYTHON_SOURCES); do \
		install -Dm644 $(SRC_DIR)/$$file $(DESTDIR)$(MODULEDIR)/$$file; \
	done
	
	# Install widget modules
	install -Dm644 $(SRC_DIR)/widgets/*.py $(DESTDIR)$(MODULEDIR)/widgets/
	install -Dm644 $(SRC_DIR)/widgets/activities/*.py $(DESTDIR)$(MODULEDIR)/widgets/activities/
	install -Dm644 $(SRC_DIR)/widgets/blocks/*.py $(DESTDIR)$(MODULEDIR)/widgets/blocks/
	install -Dm644 $(SRC_DIR)/widgets/instances/*.py $(DESTDIR)$(MODULEDIR)/widgets/instances/
	install -Dm644 $(SRC_DIR)/widgets/models/*.py $(DESTDIR)$(MODULEDIR)/widgets/models/
	install -Dm644 $(SRC_DIR)/widgets/tools/*.py $(DESTDIR)$(MODULEDIR)/widgets/tools/
	
	# Install core, repositories, and services modules
	install -Dm644 $(SRC_DIR)/core/*.py $(DESTDIR)$(MODULEDIR)/core/
	install -Dm644 $(SRC_DIR)/repositories/*.py $(DESTDIR)$(MODULEDIR)/repositories/
	install -Dm644 $(SRC_DIR)/services/*.py $(DESTDIR)$(MODULEDIR)/services/
	
	# Install GResource
	install -Dm644 $(BUILD_DIR)/alpaca.gresource $(DESTDIR)$(PKGDATADIR)/alpaca.gresource
	
	# Install desktop files
	install -Dm644 $(BUILD_DIR)/$(APPID).desktop $(DESTDIR)$(DATADIR)/applications/$(APPID).desktop
	install -Dm644 $(BUILD_DIR)/$(APPID).SearchProvider.desktop $(DESTDIR)$(DATADIR)/applications/$(APPID).SearchProvider.desktop
	
	# Install metainfo
	install -Dm644 $(BUILD_DIR)/$(APPID).metainfo.xml $(DESTDIR)$(DATADIR)/metainfo/$(APPID).metainfo.xml
	
	# Install GSchema
	install -Dm644 $(DATA_DIR)/$(APPID).gschema.xml $(DESTDIR)$(DATADIR)/glib-2.0/schemas/$(APPID).gschema.xml
	
	# Install D-Bus service
	install -Dm644 $(BUILD_DIR)/$(APPID).SearchProvider.service $(DESTDIR)$(DATADIR)/dbus-1/services/$(APPID).SearchProvider.service
	
	# Install search provider config
	install -Dm644 $(BUILD_DIR)/$(APPID).search-provider.ini $(DESTDIR)$(DATADIR)/gnome-shell/search-providers/$(APPID).search-provider.ini
	
	# Install icons
	install -d $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps
	install -d $(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps
	install -Dm644 $(ICONS_DIR)/hicolor/scalable/apps/*.svg $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/
	install -Dm644 $(ICONS_DIR)/hicolor/symbolic/apps/*.svg $(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps/
	
	@echo "Installation complete!"
	@echo ""
	@echo "Post-install steps (run as root if needed):"
	@echo "  $(GLIB_COMPILE_SCHEMAS) $(DESTDIR)$(DATADIR)/glib-2.0/schemas/"
	@echo "  gtk-update-icon-cache -f -t $(DESTDIR)$(DATADIR)/icons/hicolor/"
	@echo "  update-desktop-database $(DESTDIR)$(DATADIR)/applications/"

# Uninstall target
uninstall:
	@echo "Uninstalling Alpaca from $(DESTDIR)$(PREFIX)..."
	rm -f $(DESTDIR)$(BINDIR)/alpaca
	rm -f $(DESTDIR)$(BINDIR)/alpaca_search_provider
	rm -rf $(DESTDIR)$(MODULEDIR)
	rm -f $(DESTDIR)$(PKGDATADIR)/alpaca.gresource
	rm -f $(DESTDIR)$(DATADIR)/applications/$(APPID).desktop
	rm -f $(DESTDIR)$(DATADIR)/applications/$(APPID).SearchProvider.desktop
	rm -f $(DESTDIR)$(DATADIR)/metainfo/$(APPID).metainfo.xml
	rm -f $(DESTDIR)$(DATADIR)/glib-2.0/schemas/$(APPID).gschema.xml
	rm -f $(DESTDIR)$(DATADIR)/dbus-1/services/$(APPID).SearchProvider.service
	rm -f $(DESTDIR)$(DATADIR)/gnome-shell/search-providers/$(APPID).search-provider.ini
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/scalable/apps/$(APPID)*.svg
	rm -f $(DESTDIR)$(DATADIR)/icons/hicolor/symbolic/apps/$(APPID)*.svg
	@echo "Uninstall complete!"

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf $(BUILD_DIR)
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete
	@echo "Clean complete!"

# Test target
test:
	@echo "Running tests..."
	$(PYTHON) -m pytest tests/ -v

# Development mode - run without installing
dev: build
	@echo "Running Alpaca in development mode..."
	GSETTINGS_SCHEMA_DIR=$(DATA_DIR) \
	XDG_DATA_DIRS=$(BUILD_DIR):$$XDG_DATA_DIRS \
	$(PYTHON) -c "import sys; sys.path.insert(0, '$(SRC_DIR)'); from main import main; main('$(VERSION)', '$(PKGDATADIR)')"

# Validate files
validate: $(BUILD_DIR)/$(APPID).desktop $(BUILD_DIR)/$(APPID).metainfo.xml
	@echo "Validating desktop files..."
	-$(DESKTOP_FILE_VALIDATE) $(BUILD_DIR)/$(APPID).desktop
	-$(DESKTOP_FILE_VALIDATE) $(BUILD_DIR)/$(APPID).SearchProvider.desktop
	@echo "Validating metainfo..."
	-$(APPSTREAMCLI) validate --no-net $(BUILD_DIR)/$(APPID).metainfo.xml
	@echo "Validating schema..."
	-$(GLIB_COMPILE_SCHEMAS) --strict --dry-run $(DATA_DIR)

# Show configuration
config:
	@echo "Alpaca Build Configuration"
	@echo "=========================="
	@echo "PREFIX:     $(PREFIX)"
	@echo "BINDIR:     $(BINDIR)"
	@echo "DATADIR:    $(DATADIR)"
	@echo "MODULEDIR:  $(MODULEDIR)"
	@echo "VERSION:    $(VERSION)"
	@echo "PYTHON:     $(PYTHON)"
