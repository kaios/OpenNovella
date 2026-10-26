"""Story data model: projects, scenes, characters and commands.

A project is a folder that contains a ``story.json`` file plus optional
``images/``, ``audio/`` and ``fonts/`` folders. All asset paths inside the
story are stored relative to the project folder so a project can be zipped
up and moved anywhere.

Commands are plain dictionaries (``{"type": "say", "character": "alice",
"text": "Hi!"}``) so the file stays readable and easy to edit by hand. The
``COMMAND_TYPES`` table below describes every command and its fields; the
editor builds its forms from it and the validator checks against it.
"""

from __future__ import annotations

import copy
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

FORMAT_VERSION = 1
STORY_FILENAME = "story.json"
ASSET_FOLDERS = ("images", "audio", "fonts")

# Horizontal anchor (fraction of screen width) for each named position.
POSITIONS = {
    "far_left": 0.12,
    "left": 0.27,
    "center": 0.5,
    "right": 0.73,
    "far_right": 0.88,
}

SCENE_NAME_RE = re.compile(r"^[A-Za-z0-9_\- ]+$")
VARIABLE_NAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")

DEFAULT_SETTINGS = {
    "text_speed": 45,            # characters per second (0 = instant)
    "font": "",                  # path to a .ttf/.otf font, blank = built-in
    "font_size": 28,
    "name_font_size": 30,
    "textbox_color": "#14141e",
    "textbox_opacity": 200,      # 0 (invisible) .. 255 (solid)
    "text_color": "#f4f4f8",
    "accent_color": "#c89bff",
    "title_background": "",
    "title_background_color": "#1b1430",
    "title_music": "",
    "auto_delay": 1.5,           # seconds to wait in auto mode after a line
}


# --------------------------------------------------------------------------
# Command schema
# --------------------------------------------------------------------------

@dataclass
class Field:
    """Describes one editable property of a command."""

    name: str
    kind: str          # text, multiline, number, bool, choice, scene, character,
                       # expression, image, audio, animation, color, variable,
                       # condition, options
    label: str
    default: Any = ""
    options: list = field(default_factory=list)
    help: str = ""
    required: bool = False


@dataclass
class CommandType:
    label: str
    category: str
    description: str
    fields: list


TRANSITIONS_BG = ["none", "fade", "dissolve", "slide_left", "slide_right"]
TRANSITIONS_IN = ["none", "fade", "slide_left", "slide_right", "slide_up", "zoom"]
TRANSITIONS_OUT = ["none", "fade", "slide_left", "slide_right", "slide_down", "zoom"]
SPRITE_EFFECTS = ["none", "bounce", "shake", "float", "pulse", "jump"]
SCREEN_EFFECTS = ["shake", "flash", "fade_out", "fade_in", "tint", "clear_tint"]
SET_OPERATIONS = ["=", "+=", "-=", "*=", "/="]

COMMAND_TYPES: dict[str, CommandType] = {
    "say": CommandType(
        "Say", "Story",
        "Shows a line of dialogue in the text box. Leave the character blank "
        "for narration.",
        [
            Field("character", "character", "Character", "",
                  help="Who is speaking. Blank = narrator."),
            Field("expression", "expression", "Expression", "",
                  help="Optional. Changes the speaker's image if they are on screen."),
            Field("text", "multiline", "Text", "", required=True,
                  help="What is said. Use {variable} to insert a variable's value."),
        ]),
    "choice": CommandType(
        "Choice", "Story",
        "Shows buttons the player can pick from. Each option can jump to a "
        "scene, change variables, and be hidden unless a condition is true.",
        [
            Field("prompt", "text", "Prompt", "",
                  help="Optional text shown above the buttons."),
            Field("options", "options", "Options", [], required=True),
        ]),
    "jump": CommandType(
        "Jump", "Story",
        "Goes to another scene.",
        [Field("scene", "scene", "Scene", "", required=True)]),
    "if": CommandType(
        "If / Else", "Story",
        "Checks a condition and jumps to a scene depending on the result. "
        "Leave a scene blank to simply continue.",
        [
            Field("condition", "condition", "Condition", "", required=True,
                  help='Examples: courage >= 3   |   met_alice and not angry   |   name == "Sam"'),
            Field("then_scene", "scene", "If true, go to", ""),
            Field("else_scene", "scene", "Otherwise, go to", ""),
        ]),
    "set": CommandType(
        "Set Variable", "Story",
        "Changes a variable. Variables remember the player's decisions.",
        [
            Field("variable", "variable", "Variable", "", required=True),
            Field("operation", "choice", "Operation", "=", SET_OPERATIONS),
            Field("value", "text", "Value", "0", required=True,
                  help='A number, true/false, "text in quotes", or an expression like courage + 1'),
        ]),
    "end": CommandType(
        "End", "Story",
        "Ends the story and returns to the title screen.",
        [
            Field("text", "text", "Ending text", "The End"),
            Field("ending", "text", "Ending name", "",
                  help="Optional name for this ending (e.g. 'Good Ending')."),
        ]),
    "note": CommandType(
        "Note", "Story",
        "A note for yourself. Players never see it.",
        [Field("text", "multiline", "Note", "")]),

    "background": CommandType(
        "Background", "Visuals",
        "Changes the background. Use an image (PNG, JPG, animated GIF/WebP, "
        "or a folder of frames) or just a color.",
        [
            Field("image", "animation", "Image", ""),
            Field("color", "color", "Color (if no image)", "#202030"),
            Field("transition", "choice", "Transition", "fade", TRANSITIONS_BG),
            Field("duration", "number", "Duration (seconds)", 0.8),
            Field("clear_characters", "bool", "Remove characters", False,
                  help="Hide everyone currently on screen."),
        ]),
    "show": CommandType(
        "Show Character", "Visuals",
        "Puts a character (or any image) on screen.",
        [
            Field("character", "character", "Character", "", required=True,
                  help="A character from the Characters list, or any name for a prop."),
            Field("expression", "expression", "Expression", "default"),
            Field("image", "animation", "Custom image", "",
                  help="Optional. Overrides the character's expression image."),
            Field("position", "choice", "Position", "center", list(POSITIONS)),
            Field("transition", "choice", "Transition", "fade", TRANSITIONS_IN),
            Field("effect", "choice", "Effect", "none", SPRITE_EFFECTS,
                  help="bounce/shake/jump play once; float/pulse keep going."),
            Field("duration", "number", "Duration (seconds)", 0.5),
        ]),
    "hide": CommandType(
        "Hide Character", "Visuals",
        "Removes a character from the screen.",
        [
            Field("character", "character", "Character", "", required=True),
            Field("transition", "choice", "Transition", "fade", TRANSITIONS_OUT),
            Field("duration", "number", "Duration (seconds)", 0.5),
        ]),
    "move": CommandType(
        "Move Character", "Visuals",
        "Smoothly slides a character on screen to a new position.",
        [
            Field("character", "character", "Character", "", required=True),
            Field("position", "choice", "New position", "left", list(POSITIONS)),
            Field("duration", "number", "Duration (seconds)", 0.6),
        ]),
    "effect": CommandType(
        "Screen Effect", "Visuals",
        "Shakes, flashes, tints or fades the whole screen.",
        [
            Field("effect", "choice", "Effect", "shake", SCREEN_EFFECTS),
            Field("color", "color", "Color", "#ffffff",
                  help="Used by flash, fade and tint."),
            Field("duration", "number", "Duration (seconds)", 0.5),
            Field("wait", "bool", "Wait until finished", True),
        ]),
    "animation": CommandType(
        "Play Animation", "Visuals",
        "Plays an animation (animated GIF/WebP or a folder of numbered "
        "frames) over the scene, e.g. rain, an explosion or a sparkle.",
        [
            Field("image", "animation", "Animation", "", required=True),
            Field("position", "choice", "Position", "fullscreen",
                  ["fullscreen"] + list(POSITIONS)),
            Field("loops", "number", "Times to play (0 = forever)", 1),
            Field("fps", "number", "Frames per second (frame folders)", 12),
            Field("wait", "bool", "Wait until finished", False),
            Field("id", "text", "Name (to stop it later)", "",
                  help="Optional. Use 'Stop Animation' with this name to remove a looping animation."),
        ]),
    "stop_animation": CommandType(
        "Stop Animation", "Visuals",
        "Stops a looping animation started with 'Play Animation'. "
        "Leave the name blank to stop all of them.",
        [Field("id", "text", "Name", "")]),

    "music": CommandType(
        "Play Music", "Audio",
        "Starts background music (OGG, MP3 or WAV).",
        [
            Field("file", "audio", "Music file", "", required=True),
            Field("loop", "bool", "Loop", True),
            Field("fade", "number", "Fade in (seconds)", 1.0),
        ]),
    "stop_music": CommandType(
        "Stop Music", "Audio",
        "Stops the background music.",
        [Field("fade", "number", "Fade out (seconds)", 1.0)]),
    "sound": CommandType(
        "Play Sound", "Audio",
        "Plays a sound effect once.",
        [Field("file", "audio", "Sound file", "", required=True)]),

    "wait": CommandType(
        "Wait", "Timing",
        "Pauses for a moment.",
        [Field("seconds", "number", "Seconds", 1.0)]),
}

CATEGORIES = ["Story", "Visuals", "Audio", "Timing"]


def new_command(cmd_type: str, **values) -> dict:
    """Create a command dictionary filled with default values."""
    spec = COMMAND_TYPES[cmd_type]
    cmd: dict[str, Any] = {"type": cmd_type}
    for f in spec.fields:
        cmd[f.name] = copy.deepcopy(f.default)
    cmd.update(values)
    return cmd


def new_option(text: str = "", target: str = "", condition: str = "",
               effects: str = "") -> dict:
    return {"text": text, "target": target, "condition": condition,
            "effects": effects}


def _short(text: Any, limit: int = 60) -> str:
    text = " ".join(str(text).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def summarize(cmd: dict, story: "Story | None" = None) -> str:
    """One-line human friendly description of a command (used in the editor)."""
    t = cmd.get("type", "?")

    def char_name(cid: str) -> str:
        if not cid:
            return "Narrator"
        if story and cid in story.characters:
            return story.characters[cid].get("name") or cid
        return cid

    if t == "say":
        expr = f" ({cmd['expression']})" if cmd.get("expression") else ""
        return f"{char_name(cmd.get('character', ''))}{expr}: “{_short(cmd.get('text', ''))}”"
    if t == "choice":
        opts = cmd.get("options") or []
        parts = [f"{o.get('text', '?')} → {o.get('target') or 'continue'}" for o in opts]
        prompt = f"{_short(cmd['prompt'], 30)}  " if cmd.get("prompt") else ""
        return prompt + " | ".join(_short(p, 30) for p in parts) if parts else prompt + "(no options yet)"
    if t == "jump":
        return f"Go to scene “{cmd.get('scene', '')}”"
    if t == "if":
        then_s = cmd.get("then_scene") or "continue"
        else_s = cmd.get("else_scene") or "continue"
        return f"If {cmd.get('condition', '')} → {then_s}, else → {else_s}"
    if t == "set":
        return f"{cmd.get('variable', '')} {cmd.get('operation', '=')} {cmd.get('value', '')}"
    if t == "end":
        name = f" [{cmd['ending']}]" if cmd.get("ending") else ""
        return f"{cmd.get('text') or 'The End'}{name}"
    if t == "note":
        return f"# {_short(cmd.get('text', ''))}"
    if t == "background":
        what = os.path.basename(cmd.get("image", "")) or cmd.get("color", "")
        return f"{what}  ({cmd.get('transition', 'none')})"
    if t == "show":
        img = f" [{os.path.basename(cmd['image'])}]" if cmd.get("image") else ""
        eff = f", {cmd['effect']}" if cmd.get("effect") not in ("", "none", None) else ""
        return (f"{char_name(cmd.get('character', ''))} ({cmd.get('expression') or 'default'}){img}"
                f" at {cmd.get('position', 'center')}  ({cmd.get('transition', 'none')}{eff})")
    if t == "hide":
        return f"{char_name(cmd.get('character', ''))}  ({cmd.get('transition', 'none')})"
    if t == "move":
        return f"{char_name(cmd.get('character', ''))} → {cmd.get('position', '')}"
    if t == "effect":
        return f"{cmd.get('effect', '')} {cmd.get('duration', '')}s"
    if t == "animation":
        return f"{os.path.basename(str(cmd.get('image', '')))} at {cmd.get('position', '')}"
    if t == "stop_animation":
        return cmd.get("id") or "(all)"
    if t in ("music", "sound"):
        return os.path.basename(cmd.get("file", ""))
    if t == "stop_music":
        return f"fade {cmd.get('fade', 0)}s"
    if t == "wait":
        return f"{cmd.get('seconds', 0)} seconds"
    return str(cmd)


# --------------------------------------------------------------------------
# Story
# --------------------------------------------------------------------------

class StoryError(Exception):
    pass


class Story:
    """An entire visual novel: metadata, characters, variables and scenes."""

    def __init__(self, title: str = "Untitled Story"):
        self.title = title
        self.author = ""
        self.resolution = [1280, 720]
        self.start_scene = "start"
        self.settings: dict[str, Any] = dict(DEFAULT_SETTINGS)
        self.variables: dict[str, Any] = {}
        self.characters: dict[str, dict] = {}
        self.scenes: dict[str, dict] = {"start": {"commands": [], "notes": ""}}
        self.path: str | None = None  # project folder

    # ----- serialisation -------------------------------------------------
    def to_dict(self) -> dict:
        return {
            "format": FORMAT_VERSION,
            "engine": "OpenNovella",
            "title": self.title,
            "author": self.author,
            "resolution": list(self.resolution),
            "start_scene": self.start_scene,
            "settings": self.settings,
            "variables": self.variables,
            "characters": self.characters,
            "scenes": self.scenes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Story":
        if not isinstance(data, dict):
            raise StoryError("The story file does not contain a story.")
        fmt = data.get("format", FORMAT_VERSION)
        if isinstance(fmt, int) and fmt > FORMAT_VERSION:
            raise StoryError(
                f"This story was made with a newer version of OpenNovella "
                f"(format {fmt}). Please update OpenNovella.")
        s = cls(data.get("title", "Untitled Story"))
        s.author = data.get("author", "")
        res = data.get("resolution") or [1280, 720]
        s.resolution = [int(res[0]), int(res[1])]
        s.start_scene = data.get("start_scene", "start")
        s.settings = dict(DEFAULT_SETTINGS)
        s.settings.update(data.get("settings") or {})
        s.variables = dict(data.get("variables") or {})
        s.characters = {}
        for cid, c in (data.get("characters") or {}).items():
            s.characters[cid] = {
                "name": c.get("name", cid),
                "color": c.get("color", "#ffffff"),
                "images": dict(c.get("images") or {}),
            }
        s.scenes = {}
        for name, sc in (data.get("scenes") or {}).items():
            if isinstance(sc, list):  # allow the short form "scene": [commands]
                sc = {"commands": sc}
            s.scenes[name] = {
                "commands": [dict(c) for c in sc.get("commands", [])],
                "notes": sc.get("notes", ""),
            }
        if not s.scenes:
            s.scenes["start"] = {"commands": [], "notes": ""}
        return s

    @classmethod
    def load(cls, path: str) -> "Story":
        story_file, folder = resolve_story_path(path)
        try:
            with open(story_file, encoding="utf-8") as fh:
                data = json.load(fh)
        except FileNotFoundError:
            raise StoryError(f"No story found at {story_file}") from None
        except json.JSONDecodeError as exc:
            raise StoryError(
                f"{story_file} is not valid JSON (line {exc.lineno}, "
                f"column {exc.colno}): {exc.msg}") from None
        story = cls.from_dict(data)
        story.path = folder
        return story

    def save(self, path: str | None = None) -> str:
        if path is not None:
            _, self.path = resolve_story_path(path)
        if not self.path:
            raise StoryError("No project folder chosen to save into.")
        os.makedirs(self.path, exist_ok=True)
        story_file = os.path.join(self.path, STORY_FILENAME)
        tmp = story_file + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(self.to_dict(), fh, indent=2, ensure_ascii=False)
            fh.write("\n")
        os.replace(tmp, story_file)  # never leave a half-written story behind
        return story_file

    def copy(self) -> "Story":
        s = Story.from_dict(copy.deepcopy(self.to_dict()))
        s.path = self.path
        return s

    # ----- assets --------------------------------------------------------
    def resolve(self, rel_path: str) -> str:
        """Turn a project-relative asset path into an absolute path."""
        if not rel_path:
            return ""
        if os.path.isabs(rel_path):
            return rel_path
        return os.path.normpath(os.path.join(self.path or ".", rel_path))

    def relative(self, abs_path: str) -> str:
        """Turn an absolute path into one relative to the project, if inside it."""
        if not self.path:
            return abs_path
        try:
            rel = os.path.relpath(abs_path, self.path)
        except ValueError:  # different drive on Windows
            return abs_path
        if rel.startswith(".."):
            return abs_path
        return rel.replace(os.sep, "/")

    def character_image(self, cid: str, expression: str = "") -> str:
        char = self.characters.get(cid)
        if not char:
            return ""
        images = char.get("images") or {}
        return images.get(expression or "default") or images.get("default") or ""

    # ----- scenes --------------------------------------------------------
    def scene_names(self) -> list[str]:
        return list(self.scenes)

    def commands(self, scene: str) -> list[dict]:
        return self.scenes[scene]["commands"]

    def add_scene(self, name: str, after: str | None = None) -> str:
        name = name.strip()
        if not name:
            raise StoryError("A scene needs a name.")
        if not SCENE_NAME_RE.match(name):
            raise StoryError("Scene names may only use letters, numbers, spaces, - and _.")
        if name in self.scenes:
            raise StoryError(f"There is already a scene called “{name}”.")
        new = {"commands": [], "notes": ""}
        if after and after in self.scenes:
            items = list(self.scenes.items())
            idx = [k for k, _ in items].index(after) + 1
            items.insert(idx, (name, new))
            self.scenes = dict(items)
        else:
            self.scenes[name] = new
        return name

    def rename_scene(self, old: str, new: str) -> None:
        new = new.strip()
        if old == new:
            return
        if not SCENE_NAME_RE.match(new or "!"):
            raise StoryError("Scene names may only use letters, numbers, spaces, - and _.")
        if new in self.scenes:
            raise StoryError(f"There is already a scene called “{new}”.")
        self.scenes = {(new if k == old else k): v for k, v in self.scenes.items()}
        if self.start_scene == old:
            self.start_scene = new
        # Update every reference so links never break.
        for sc in self.scenes.values():
            for cmd in sc["commands"]:
                for key in ("scene", "then_scene", "else_scene"):
                    if cmd.get(key) == old:
                        cmd[key] = new
                for opt in cmd.get("options") or []:
                    if opt.get("target") == old:
                        opt["target"] = new

    def delete_scene(self, name: str) -> None:
        if len(self.scenes) <= 1:
            raise StoryError("A story needs at least one scene.")
        del self.scenes[name]
        if self.start_scene == name:
            self.start_scene = next(iter(self.scenes))

    def links(self, scene: str) -> list[tuple[str, str, int]]:
        """Outgoing links of a scene as (target, label, command index)."""
        out = []
        for i, cmd in enumerate(self.scenes.get(scene, {}).get("commands", [])):
            t = cmd.get("type")
            if t == "jump" and cmd.get("scene"):
                out.append((cmd["scene"], "jump", i))
            elif t == "if":
                if cmd.get("then_scene"):
                    out.append((cmd["then_scene"], f"if {cmd.get('condition', '')}", i))
                if cmd.get("else_scene"):
                    out.append((cmd["else_scene"], "else", i))
            elif t == "choice":
                for opt in cmd.get("options") or []:
                    if opt.get("target"):
                        out.append((opt["target"], opt.get("text", ""), i))
        return out

    def references_to(self, scene: str) -> list[tuple[str, int]]:
        refs = []
        for name in self.scenes:
            for target, _label, idx in self.links(name):
                if target == scene:
                    refs.append((name, idx))
        return refs

    def reachable_scenes(self) -> set[str]:
        seen: set[str] = set()
        todo = [self.start_scene]
        while todo:
            s = todo.pop()
            if s in seen or s not in self.scenes:
                continue
            seen.add(s)
            todo.extend(t for t, _l, _i in self.links(s))
        return seen

    def variable_names(self) -> list[str]:
        names = set(self.variables)
        for sc in self.scenes.values():
            for cmd in sc["commands"]:
                if cmd.get("type") == "set" and cmd.get("variable"):
                    names.add(cmd["variable"])
        return sorted(names)


def resolve_story_path(path: str) -> tuple[str, str]:
    """Accept a project folder or a story.json path; return (file, folder)."""
    path = os.path.abspath(os.path.expanduser(path))
    if os.path.isdir(path) or not path.lower().endswith(".json"):
        return os.path.join(path, STORY_FILENAME), path
    return path, os.path.dirname(path)


def load_story(path: str) -> Story:
    return Story.load(path)


def create_project(folder: str, title: str = "My Visual Novel",
                   author: str = "", template: bool = True) -> Story:
    """Create a new project folder with a small starter story."""
    folder = os.path.abspath(os.path.expanduser(folder))
    if os.path.exists(os.path.join(folder, STORY_FILENAME)):
        raise StoryError(f"There is already a story in {folder}")
    for sub in ASSET_FOLDERS:
        os.makedirs(os.path.join(folder, sub), exist_ok=True)

    story = Story(title)
    story.author = author
    story.path = folder
    if template:
        story.characters["guide"] = {"name": "Guide", "color": "#9ad0ff",
                                     "images": {"default": ""}}
        story.variables = {"curious": False}
        story.scenes = {
            "start": {"notes": "The first scene of your story.", "commands": [
                new_command("background", color="#2b2d5c", transition="fade"),
                new_command("say", text=f"Welcome to {title}!"),
                new_command("show", character="guide", position="center"),
                new_command("say", character="guide",
                            text="Hi! I'm a placeholder character. Give me an image in the Characters window."),
                new_command("choice", prompt="What would you like to do?", options=[
                    new_option("Tell me more", "learn_more", effects="curious = true"),
                    new_option("Let's begin!", "chapter_1"),
                ]),
            ]},
            "learn_more": {"notes": "", "commands": [
                new_command("say", character="guide",
                            text="Every scene is a list of commands. Choices and Jumps connect scenes into branching paths."),
                new_command("jump", scene="chapter_1"),
            ]},
            "chapter_1": {"notes": "", "commands": [
                new_command("background", color="#3d5c2b", transition="dissolve"),
                new_command("if", condition="curious", then_scene="", else_scene="chapter_1_rest"),
                new_command("say", character="guide", text="Since you were curious, here's a tip: press H to see the dialogue history."),
                new_command("jump", scene="chapter_1_rest"),
            ]},
            "chapter_1_rest": {"notes": "", "commands": [
                new_command("say", character="guide", text="Your adventure starts here. Good luck!"),
                new_command("end", text="To be continued..."),
            ]},
        }
    story.save()
    return story
