"""OpenNovella - an easy-to-use visual novel engine written in Python.

Created by Shawn Rapaz and Claude Code.
"""

__version__ = "0.1.0"
__authors__ = ["Shawn Rapaz", "Claude Code"]
__credits__ = "OpenNovella was created by Shawn Rapaz and Claude Code."
__license__ = "GPL-3.0-or-later"

from .story import Story, load_story, create_project  # noqa: E402

__all__ = ["Story", "load_story", "create_project", "__version__"]
