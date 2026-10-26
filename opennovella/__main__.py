"""Command line entry point.

    opennovella                       open the editor
    opennovella edit [PROJECT]        open the editor (optionally with a project)
    opennovella play PROJECT          play a story  (--scene NAME, --fullscreen)
    opennovella new FOLDER            create a new project (--title, --author)
    opennovella check PROJECT         look for mistakes in a story
    opennovella export PROJECT OUT    make a shareable game folder
    opennovella bugreport [PROJECT]   print system info for a bug report
"""

from __future__ import annotations

import argparse
import sys

from . import __credits__, __version__


def _cmd_edit(args) -> int:
    try:
        from .editor.app import run_editor
    except ImportError as exc:
        print("The editor needs tkinter, which is missing from this Python installation.\n"
              "  - Windows/macOS: reinstall Python from python.org (tkinter is included)\n"
              "  - Debian/Ubuntu: sudo apt install python3-tk\n"
              "  - Fedora:        sudo dnf install python3-tkinter\n"
              f"({exc})", file=sys.stderr)
        return 1
    return run_editor(args.project)


def _cmd_play(args) -> int:
    try:
        from .player import play
    except ImportError as exc:
        print(f"Playing needs pygame: python -m pip install pygame Pillow\n({exc})", file=sys.stderr)
        return 1
    return play(args.project, scene=args.scene, fullscreen=True if args.fullscreen else None)


def _cmd_new(args) -> int:
    from .story import StoryError, create_project
    try:
        story = create_project(args.folder, title=args.title, author=args.author,
                               template=not args.empty)
    except StoryError as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Created “{story.title}” in {story.path}")
    print(f"Play it with:  python -m opennovella play \"{story.path}\"")
    return 0


def _cmd_check(args) -> int:
    from .story import StoryError, load_story
    from .validate import ERROR, validate
    try:
        story = load_story(args.project)
    except StoryError as exc:
        print(exc, file=sys.stderr)
        return 1
    issues = validate(story)
    for issue in issues:
        print(issue)
    errors = sum(1 for i in issues if i.level == ERROR)
    print(f"\n{len(story.scenes)} scenes checked: {errors} error(s), {len(issues) - errors} other note(s).")
    return 1 if errors else 0


def _cmd_export(args) -> int:
    from .export import export_game
    from .story import StoryError, load_story
    try:
        out = export_game(load_story(args.project), args.out)
    except (StoryError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    print(f"Game exported to {out}\nPlayers run:  python play.py")
    return 0


def _cmd_bugreport(args) -> int:
    from .bugreport import report_template
    print(report_template(args.project))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="opennovella",
        description=f"OpenNovella {__version__} - make visual novels with branching paths. {__credits__}")
    parser.add_argument("--version", action="version", version=f"OpenNovella {__version__}")
    sub = parser.add_subparsers(dest="command")

    p = sub.add_parser("edit", help="open the visual editor")
    p.add_argument("project", nargs="?")
    p.set_defaults(func=_cmd_edit)

    p = sub.add_parser("play", help="play a story")
    p.add_argument("project")
    p.add_argument("--scene", help="start at this scene instead of the title screen")
    p.add_argument("--fullscreen", action="store_true")
    p.set_defaults(func=_cmd_play)

    p = sub.add_parser("new", help="create a new project")
    p.add_argument("folder")
    p.add_argument("--title", default="My Visual Novel")
    p.add_argument("--author", default="")
    p.add_argument("--empty", action="store_true", help="don't add the starter scenes")
    p.set_defaults(func=_cmd_new)

    p = sub.add_parser("check", aliases=["validate"], help="check a story for mistakes")
    p.add_argument("project")
    p.set_defaults(func=_cmd_check)

    p = sub.add_parser("export", help="make a shareable game folder")
    p.add_argument("project")
    p.add_argument("out")
    p.set_defaults(func=_cmd_export)

    p = sub.add_parser("bugreport", help="print information to include in a bug report")
    p.add_argument("project", nargs="?")
    p.set_defaults(func=_cmd_bugreport)

    args = parser.parse_args(argv)
    if not args.command:
        args.project = None
        return _cmd_edit(args)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
