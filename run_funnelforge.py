# run_funnelforge.py
# Correct launcher for PyInstaller that preserves package context

import os
import sys
import runpy
from pathlib import Path

if __name__ == "__main__":
    # Ensure project root is on sys.path
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))

    # Explicitly run the package module
    runpy.run_module("funnel_forge.app", run_name="__main__")
