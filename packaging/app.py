"""PyInstaller entry point (a plain script: the frozen app can't start from a relative import)."""
import os
import sys

if sys.stdout is None:   # windowed Windows build has no console; CLI output would crash print()
    sys.stdout = sys.stderr = open(os.devnull, "w")

from rigitems.cli import main

main()
