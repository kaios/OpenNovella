"""Collects system information to paste into a bug report."""

from __future__ import annotations

import os
import platform
import sys

from . import __version__

ISSUES_HINT = ("Fill in the sections below and send it to the OpenNovella project "
               "(see BUG_REPORT.md for where and how).")


def _version_of(module: str) -> str:
    try:
        mod = __import__(module)
    except Exception:
        return "not installed"
    if module == "pygame":
        return getattr(mod.version, "ver", "?")
    if module == "tkinter":
        return str(getattr(mod, "TkVersion", "?"))
    return getattr(mod, "__version__", "installed")


def system_info() -> str:
    lines = [
        f"OpenNovella: {__version__}",
        f"Python:      {sys.version.split()[0]} ({platform.python_implementation()})",
        f"OS:          {platform.platform()}",
        f"pygame:      {_version_of('pygame')}",
        f"Pillow:      {_version_of('PIL')}",
        f"tkinter:     {_version_of('tkinter')}",
    ]
    return "\n".join(lines)


def report_template(story_path: str | None = None) -> str:
    crash = ""
    if story_path:
        log = os.path.join(story_path, "saves", "crash.log")
        if os.path.isfile(log):
            with open(log, encoding="utf-8", errors="replace") as fh:
                crash = "\n## Crash log\n```\n" + fh.read()[-6000:] + "\n```\n"
    return f"""# OpenNovella bug report

{ISSUES_HINT}

## What happened?


## What did you expect to happen?


## Steps to reproduce
1.
2.
3.

## System information
```
{system_info()}
```
{crash}"""


def write_report(path: str, story_path: str | None = None) -> str:
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(report_template(story_path))
    return path
