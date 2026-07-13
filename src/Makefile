#
# Safe Makefile for Ancient Greek Dictionary Build
#

.PHONY: all install clean

# 1. Safe, space-free filesystem names for compiling
DICT_NAME        = AncientGreekDictionary
DICT_SRC_PATH    = GreekDictionary.xml
DICT_CSS_PATH    = GreekDictionary.css
DICT_PLIST_PATH  = GreekDictionary.plist

DICT2_NAME       = GreekGrammarReference
DICT2_SRC_PATH   = GrammarReference.xml
DICT2_CSS_PATH   = GrammarReference.css
DICT2_PLIST_PATH = GrammarReference.plist

# 2. Your Computer-Wide Compiler Path
DICT_DEV_KIT_OBJ_DIR = /Applications/XcodeAdditionalTools/Utilities/DictionaryDevelopmentKit
DICT_BUILD_TOOL_DIR  = $(DICT_DEV_KIT_OBJ_DIR)/bin

# 3. System & Target Installation Paths
MIN_OS_VERSION   = 10.6
export MACOSX_DEPLOYMENT_TARGET=$(MIN_OS_VERSION)
DICT_BUILD_DIR   = ./objects
BUILD_DICT_XML   = $(DICT_BUILD_TOOL_DIR)/build_dict.sh

# build_dict.sh internally runs xmllint/xsltproc over dict.plist, whose
# DOCTYPE points at http://www.apple.com/DTDs/PropertyList-1.0.dtd - a
# network fetch that libxml2 intermittently truncates mid-response ("Comment
# not terminated"), unrelated to anything in this project's own source
# files (see ../../bin-morphology-recap.md's "Process notes"). macOS already
# ships the identical DTD locally at /System/Library/DTDs/PropertyList.dtd
# (byte-identical apart from a trailing newline); this XML catalog redirects
# that lookup to it, so the build no longer depends on the network fetch
# succeeding at all.
export XML_CATALOG_FILES=$(CURDIR)/xml-catalog.xml

# TARGET DIR: Maps natively to /Users/jonatansolon/Library/Dictionaries
INSTALL_DIR      = $(HOME)/Library/Dictionaries

all:
	@echo "🏗️  Compiling macOS Dictionary (Safe-Name Mode)..."
	"$(BUILD_DICT_XML)" "$(DICT_NAME)" $(DICT_SRC_PATH) $(DICT_CSS_PATH) $(DICT_PLIST_PATH)
	rm -rf "$(DICT_NAME).dictionary"
	cp -R "objects/$(DICT_NAME).dictionary" ./
	"$(BUILD_DICT_XML)" "$(DICT2_NAME)" $(DICT2_SRC_PATH) $(DICT2_CSS_PATH) $(DICT2_PLIST_PATH)
	rm -rf "$(DICT2_NAME).dictionary"
	cp -R "objects/$(DICT2_NAME).dictionary" ./

install: all
	@echo "🚀 Automatically moving bundles to $(INSTALL_DIR)..."
	mkdir -p "$(INSTALL_DIR)"
	rm -rf "$(INSTALL_DIR)/$(DICT_NAME).dictionary"
	cp -R "$(DICT_NAME).dictionary" "$(INSTALL_DIR)/"
	rm -rf "$(INSTALL_DIR)/$(DICT2_NAME).dictionary"
	cp -R "$(DICT2_NAME).dictionary" "$(INSTALL_DIR)/"
	@echo "✅ Installed successfully! Refresh your Dictionary app Settings."

clean:
	@echo "🧹 Cleaning up build artifacts..."
	$(RM) -rf $(DICT_BUILD_DIR)
	$(RM) -rf "$(DICT_NAME).dictionary"
	$(RM) -rf "$(DICT2_NAME).dictionary"
