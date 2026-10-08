"""Keep dependency caches in the private, writable one-file extraction directory."""
import sys
import tempfile

if hasattr(sys, "_MEIPASS"):
    # Runs before bundled library hooks. The bootloader already created this
    # private directory in LOCALAPPDATA; no default TEMP or app-folder writes.
    tempfile.tempdir = sys._MEIPASS
