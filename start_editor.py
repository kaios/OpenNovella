#!/usr/bin/env python3
"""Double-click this file (or run `python start_editor.py`) to open the OpenNovella editor.

OpenNovella - created by Shawn Rapaz and Claude Code.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from opennovella.__main__ import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:] or None))
