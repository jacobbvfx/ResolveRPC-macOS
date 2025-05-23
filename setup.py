# filepath: /Users/jacob/Documents/Dev/ResolveRPC-macOS/setup.py
from setuptools import setup
import sys # Import sys module

APP_NAME = "ResolveRPC"
APP_SCRIPT = 'resolve_rich_presence.py'

ICON_FILE = 'ResolveRPC.icns'

# Path to DaVinci Resolve's scripting modules
RESOLVE_SCRIPT_MODULES_PATH = "/Library/Application Support/Blackmagic Design/DaVinci Resolve/Developer/Scripting/Modules"

# Add Resolve's scripting modules path to sys.path so py2app can find it
if RESOLVE_SCRIPT_MODULES_PATH not in sys.path:
    sys.path.append(RESOLVE_SCRIPT_MODULES_PATH)

DATA_FILES = [('', ['topicon.png'])]

OPTIONS = {
    'argv_emulation': False,
    'iconfile': ICON_FILE,
    'plist': {
        'CFBundleName': APP_NAME,
        'CFBundleDisplayName': APP_NAME,
        'CFBundleGetInfoString': "DaVinci Resolve Rich Presence for Discord",
        'CFBundleIdentifier': "net.jacobb.resolverpc",
        'CFBundleVersion': "1.0.0",
        'CFBundleShortVersionString': "1.0",
        'LSUIElement': True,
        'NSHumanReadableCopyright': u"Copyright © 2025 Jacobb. All rights reserved.",
    },
    'packages': [
        'rumps', 
        'pypresence', 
        'psutil', 
        'typing_extensions'
    ],
    'excludes': [], 
    # py2app will find DaVinciResolveScript via sys.path and py_modules
}

setup(
    app=[APP_SCRIPT],
    name=APP_NAME,
    data_files=DATA_FILES,
    options={'py2app': OPTIONS},
    setup_requires=['py2app'],
    py_modules=['DaVinciResolveScript'] # Add DaVinciResolveScript here
)