"""Export a project as a stand-alone game folder you can share."""

from __future__ import annotations

import os
import shutil

from .story import Story

PLAY_SCRIPT = '''#!/usr/bin/env python3
"""Launcher for "{title}". Made with OpenNovella (by Shawn Rapaz & Claude Code)."""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

try:
    from opennovella.player import play
except ImportError as exc:
    print("This game needs pygame. Install it with:  python -m pip install pygame Pillow")
    print(f"({{exc}})")
    sys.exit(1)

sys.exit(play(os.path.join(HERE, "game")))
'''

PLAYER_README = """{title}
{underline}
{byline}

HOW TO PLAY
  1. Install Python 3.9 or newer from https://www.python.org
  2. Install the game libraries (only needed once):
         python -m pip install pygame Pillow
  3. Run the game:
         python play.py
     (On Windows you can usually just double-click play.py.)

CONTROLS
  Click / Space / Enter ... next line       Esc / Right click ... menu
  H / Scroll up ........... history         A ................... auto mode
  Ctrl (hold) / Tab ....... skip            V ................... hide text box
  F5 / F9 ................. quick save/load F11 ................. fullscreen

MAKING A SINGLE EXECUTABLE (optional, for the game's author)
  python -m pip install pyinstaller
  pyinstaller --onedir --windowed --add-data "game{sep}game" --add-data "opennovella{sep}opennovella" play.py
  The finished game will be in the dist/play folder.

Made with OpenNovella - a visual novel engine by Shawn Rapaz and Claude Code.
"""

_SKIP = shutil.ignore_patterns("__pycache__", "*.pyc", "saves", "*.tmp", ".DS_Store", "Thumbs.db")


def export_game(story: Story, out_dir: str) -> str:
    """Copy the engine (without the editor) and the project into ``out_dir``."""
    if not story.path:
        raise ValueError("Save the project before exporting it.")
    out_dir = os.path.abspath(out_dir)
    if os.path.abspath(story.path) == out_dir or out_dir.startswith(os.path.abspath(story.path) + os.sep):
        raise ValueError("Please export to a folder outside the project folder.")
    if os.path.exists(out_dir) and os.listdir(out_dir):
        raise ValueError(f"The folder {out_dir} is not empty. Choose an empty or new folder.")
    os.makedirs(out_dir, exist_ok=True)

    pkg_src = os.path.dirname(os.path.abspath(__file__))
    shutil.copytree(pkg_src, os.path.join(out_dir, "opennovella"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "editor"))
    shutil.copytree(story.path, os.path.join(out_dir, "game"), ignore=_SKIP)

    with open(os.path.join(out_dir, "play.py"), "w", encoding="utf-8") as fh:
        fh.write(PLAY_SCRIPT.format(title=story.title.replace('"', "'")))
    byline = f"by {story.author}" if story.author else ""
    with open(os.path.join(out_dir, "README.txt"), "w", encoding="utf-8") as fh:
        fh.write(PLAYER_README.format(title=story.title, underline="=" * len(story.title),
                                      byline=byline, sep=os.pathsep))
    return out_dir
