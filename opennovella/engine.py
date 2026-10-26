"""The story interpreter.

``Engine`` walks through a story's commands and keeps track of everything
that matters for saving: the current position, variables, what is on screen
and what music is playing. It knows nothing about drawing - the pygame
player (``player.py``) asks it for the next *event* and renders it, which
also makes the engine easy to test without a window.

Typical use::

    engine = Engine(story)
    engine.start()
    while True:
        event = engine.step()
        ...  # draw it; for "say" wait for a click, for "choice" call choose()
"""

from __future__ import annotations

import copy
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from .expressions import (ExpressionError, apply_operation, evaluate,
                          interpolate, parse_value, run_statements)
from .story import Story

log = logging.getLogger("opennovella")

# Commands that wait for the player (or a timer) before the story continues.
BLOCKING = {"say", "choice", "wait", "end"}
MAX_STEPS_WITHOUT_BLOCK = 10000  # protects against jump loops with no dialogue


@dataclass
class Event:
    type: str
    cmd: dict
    scene: str
    index: int
    data: dict = field(default_factory=dict)

    def __getitem__(self, key):
        return self.data[key]

    def get(self, key, default=None):
        return self.data.get(key, default)


class EngineError(Exception):
    pass


class Engine:
    def __init__(self, story: Story):
        self.story = story
        self.reset()

    # ----- state ---------------------------------------------------------
    def reset(self) -> None:
        self.scene = self.story.start_scene
        self.index = 0
        self.variables: dict[str, Any] = copy.deepcopy(self.story.variables)
        self.background: dict[str, Any] = {"image": "", "color": "#000000"}
        self.shown: dict[str, dict] = {}       # id -> {character, expression, image, position, effect}
        self.animations: dict[str, dict] = {}  # looping overlays: id -> {image, position, fps}
        self.tint: str = ""                    # translucent color over the scene
        self.cover: str = ""                   # solid color after a fade_out
        self.music: dict[str, Any] | None = None
        self.history: list[dict] = []
        self.finished = False
        self.ending: str = ""
        self.pending_choice: Event | None = None
        self.last_block: tuple[str, int] = (self.scene, 0)
        self.block_history_len = 0
        self.warnings: list[str] = []

    def start(self, scene: str | None = None) -> None:
        self.reset()
        scene = scene or self.story.start_scene
        if scene not in self.story.scenes:
            raise EngineError(f"The story has no scene called “{scene}”.")
        self.scene = scene
        self.index = 0

    def snapshot(self) -> dict:
        """Everything needed to restore the game later (for save files)."""
        scene, index = self.last_block
        return {
            "scene": scene,
            "index": index,
            "variables": copy.deepcopy(self.variables),
            "background": dict(self.background),
            "shown": copy.deepcopy(self.shown),
            "animations": copy.deepcopy(self.animations),
            "tint": self.tint,
            "cover": self.cover,
            "music": copy.deepcopy(self.music),
            # The blocking command is re-run on load, so leave its line out.
            "history": self.history[:self.block_history_len][-200:],
            "time": time.time(),
        }

    def restore(self, snap: dict) -> None:
        self.reset()
        scene = snap.get("scene", self.story.start_scene)
        if scene not in self.story.scenes:
            raise EngineError(
                f"This save points to the scene “{scene}”, which no longer exists.")
        self.scene = scene
        self.index = min(int(snap.get("index", 0)), len(self.story.commands(scene)))
        self.variables.update(snap.get("variables") or {})
        self.background = dict(snap.get("background") or self.background)
        self.shown = copy.deepcopy(snap.get("shown") or {})
        self.animations = copy.deepcopy(snap.get("animations") or {})
        self.tint = snap.get("tint", "")
        self.cover = snap.get("cover", "")
        self.music = snap.get("music")
        self.history = list(snap.get("history") or [])
        self.last_block = (self.scene, self.index)
        self.block_history_len = len(self.history)

    # ----- helpers -------------------------------------------------------
    def _warn(self, msg: str) -> None:
        log.warning(msg)
        self.warnings.append(msg)

    def text(self, value: str) -> str:
        return interpolate(value or "", self.variables)

    def condition(self, expr: str) -> bool:
        if not expr or not str(expr).strip():
            return True
        try:
            return bool(evaluate(expr, self.variables))
        except ExpressionError as exc:
            self._warn(f"Condition “{expr}” in scene “{self.scene}”: {exc}")
            return False

    def goto(self, scene: str) -> None:
        if scene not in self.story.scenes:
            self._warn(f"Tried to go to missing scene “{scene}”; ending the story.")
            self.finished = True
            return
        self.scene = scene
        self.index = 0

    def speaker_name(self, cid: str) -> str:
        if not cid:
            return ""
        char = self.story.characters.get(cid)
        return (char or {}).get("name") or cid

    def speaker_color(self, cid: str) -> str:
        return (self.story.characters.get(cid) or {}).get("color") or "#ffffff"

    def sprite_image(self, entry: dict) -> str:
        return entry.get("image") or self.story.character_image(
            entry.get("character", ""), entry.get("expression", ""))

    # ----- running -------------------------------------------------------
    def step(self) -> Event:
        """Run commands until the next one the player needs to see.

        Visual/audio commands are returned too (so the player can animate
        them) but do not block. A pending choice must be answered with
        ``choose()`` before stepping again.
        """
        if self.pending_choice is not None:
            return self.pending_choice
        for _ in range(MAX_STEPS_WITHOUT_BLOCK):
            if self.finished:
                return Event("end", {"type": "end"}, self.scene, self.index,
                             {"text": "The End", "ending": self.ending})
            commands = self.story.commands(self.scene)
            if self.index >= len(commands):
                # Running off the end of a scene ends the story.
                self.finished = True
                continue
            pos = self.index
            cmd = commands[pos]
            self.index += 1
            history_mark = len(self.history)
            ev = self._execute(cmd, pos)
            if ev is not None:
                if ev.type in BLOCKING:
                    self.last_block = (ev.scene, ev.index)
                    self.block_history_len = history_mark
                return ev
        raise EngineError(
            f"The story seems stuck in a loop around scene “{self.scene}” "
            "(it keeps jumping without showing any dialogue).")

    def choose(self, option_index: int) -> None:
        ev = self.pending_choice
        if ev is None:
            raise EngineError("There is no choice to answer.")
        options = ev.data["options"]
        if not 0 <= option_index < len(options):
            raise EngineError("That option does not exist.")
        opt = options[option_index]["option"]
        self.pending_choice = None
        self.history.append({"speaker": "", "text": f"▶ {options[option_index]['text']}",
                             "choice": True})
        if opt.get("effects"):
            try:
                run_statements(opt["effects"], self.variables)
            except ExpressionError as exc:
                self._warn(f"Choice effects “{opt['effects']}”: {exc}")
        if opt.get("target"):
            self.goto(opt["target"])

    def _execute(self, cmd: dict, pos: int) -> Event | None:
        t = cmd.get("type")
        ev = lambda **data: Event(t, cmd, self.scene, pos, data)  # noqa: E731

        if t == "say":
            cid = cmd.get("character", "")
            if cmd.get("expression") and cid in self.shown:
                self.shown[cid]["expression"] = cmd["expression"]
                self.shown[cid]["image"] = ""
            text = self.text(cmd.get("text", ""))
            name = self.speaker_name(cid)
            self.history.append({"speaker": name, "text": text,
                                 "color": self.speaker_color(cid) if cid else ""})
            return ev(character=cid, name=name, color=self.speaker_color(cid), text=text)

        if t == "choice":
            visible = []
            for opt in cmd.get("options") or []:
                if self.condition(opt.get("condition", "")):
                    visible.append({"text": self.text(opt.get("text", "")), "option": opt})
            if not visible:
                self._warn(f"A choice in scene “{self.scene}” had no available options; skipping it.")
                return None
            event = ev(prompt=self.text(cmd.get("prompt", "")), options=visible)
            self.pending_choice = event
            return event

        if t == "jump":
            self.goto(cmd.get("scene", ""))
            return None

        if t == "if":
            target = cmd.get("then_scene") if self.condition(cmd.get("condition", "")) \
                else cmd.get("else_scene")
            if target:
                self.goto(target)
            return None

        if t == "set":
            name = cmd.get("variable", "").strip()
            if not name:
                return None
            try:
                value = parse_value(cmd.get("value", ""), self.variables)
                self.variables[name] = apply_operation(
                    self.variables.get(name), cmd.get("operation", "="), value)
            except ExpressionError as exc:
                self._warn(f"Set {name}: {exc}")
            return None

        if t == "end":
            self.finished = True
            self.ending = cmd.get("ending", "")
            return ev(text=self.text(cmd.get("text") or "The End"), ending=self.ending)

        if t == "note":
            return None

        if t == "background":
            self.background = {"image": cmd.get("image", ""),
                               "color": cmd.get("color") or "#000000"}
            if cmd.get("clear_characters"):
                self.shown.clear()
            return ev()

        if t == "show":
            cid = cmd.get("character", "") or cmd.get("image", "")
            if not cid:
                return None
            entry = {
                "character": cmd.get("character", ""),
                "expression": cmd.get("expression") or "default",
                "image": cmd.get("image", ""),
                "position": cmd.get("position") or "center",
                "effect": cmd.get("effect") if cmd.get("effect") in ("float", "pulse") else "none",
            }
            was_shown = cid in self.shown
            self.shown[cid] = entry
            return ev(id=cid, entry=dict(entry), was_shown=was_shown)

        if t == "hide":
            cid = cmd.get("character", "")
            entry = self.shown.pop(cid, None)
            if entry is None:
                return None
            return ev(id=cid, entry=entry)

        if t == "move":
            cid = cmd.get("character", "")
            if cid not in self.shown:
                self._warn(f"Can't move “{cid}” - they are not on screen.")
                return None
            self.shown[cid]["position"] = cmd.get("position") or "center"
            return ev(id=cid)

        if t == "effect":
            effect = cmd.get("effect", "shake")
            if effect == "tint":
                self.tint = cmd.get("color") or "#000000"
            elif effect == "clear_tint":
                self.tint = ""
            elif effect == "fade_out":
                self.cover = cmd.get("color") or "#000000"
            elif effect == "fade_in":
                self.cover = ""
            return ev()

        if t == "animation":
            loops = int(float(cmd.get("loops") or 0))
            if loops == 0 and cmd.get("image"):
                aid = cmd.get("id") or cmd["image"]
                self.animations[aid] = {"image": cmd["image"],
                                        "position": cmd.get("position", "fullscreen"),
                                        "fps": cmd.get("fps", 12)}
            return ev()

        if t == "stop_animation":
            aid = cmd.get("id", "")
            if aid:
                self.animations.pop(aid, None)
            else:
                self.animations.clear()
            return ev(id=aid)

        if t == "music":
            if cmd.get("file"):
                self.music = {"file": cmd["file"], "loop": bool(cmd.get("loop", True))}
            return ev()

        if t == "stop_music":
            self.music = None
            return ev()

        if t in ("sound", "wait"):
            return ev()

        self._warn(f"Unknown command type “{t}” in scene “{self.scene}”.")
        return None
