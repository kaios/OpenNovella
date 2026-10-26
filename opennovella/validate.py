"""Checks a story for mistakes before you play or share it."""

from __future__ import annotations

import os
from dataclasses import dataclass

from .expressions import ExpressionError, check_expression, names_in, parse_statements
from .story import COMMAND_TYPES, POSITIONS, Story

ERROR = "error"
WARNING = "warning"
INFO = "info"


@dataclass
class Issue:
    level: str
    message: str
    scene: str = ""
    index: int = -1

    def __str__(self) -> str:
        where = ""
        if self.scene:
            where = f"[{self.scene}" + (f" #{self.index + 1}" if self.index >= 0 else "") + "] "
        return f"{self.level.upper():7} {where}{self.message}"


def _asset_exists(story: Story, rel: str) -> bool:
    return os.path.exists(story.resolve(rel))


def validate(story: Story) -> list[Issue]:
    issues: list[Issue] = []
    add = lambda lvl, msg, scene="", idx=-1: issues.append(Issue(lvl, msg, scene, idx))  # noqa: E731

    if story.start_scene not in story.scenes:
        add(ERROR, f"The start scene “{story.start_scene}” does not exist.")

    known_vars = set(story.variable_names())
    for sc in story.scenes.values():
        for cmd in sc["commands"]:
            for opt in cmd.get("options") or []:
                try:
                    known_vars.update(n for n, _o, _v in parse_statements(opt.get("effects", "")))
                except ExpressionError:
                    pass

    def check_scene_ref(target, scene, idx, what):
        if target and target not in story.scenes:
            add(ERROR, f"{what} goes to the scene “{target}”, which doesn't exist.", scene, idx)

    def check_condition(expr, scene, idx, what="Condition"):
        if not expr:
            return
        err = check_expression(expr)
        if err:
            add(ERROR, f"{what}: {err}", scene, idx)
            return
        for name in sorted(names_in(expr) - known_vars):
            add(WARNING, f"{what} uses “{name}”, which is never set. It will count as 0/false.",
                scene, idx)

    def check_asset(rel, scene, idx, what):
        if rel and story.path and not _asset_exists(story, rel):
            add(WARNING, f"{what} file not found: {rel}", scene, idx)

    for cid, char in story.characters.items():
        for expr, img in (char.get("images") or {}).items():
            if img and story.path and not _asset_exists(story, img):
                add(WARNING, f"Character “{cid}” image for “{expr}” not found: {img}")
    for key in ("title_background", "title_music", "font"):
        check_asset(story.settings.get(key, ""), "", -1, f"Setting “{key}”")

    for scene, sc in story.scenes.items():
        cmds = sc["commands"]
        if not cmds:
            add(WARNING, "This scene is empty.", scene)
        for i, cmd in enumerate(cmds):
            t = cmd.get("type")
            spec = COMMAND_TYPES.get(t)
            if spec is None:
                add(ERROR, f"Unknown command type “{t}”.", scene, i)
                continue
            for f in spec.fields:
                if f.required and f.kind != "options" and not str(cmd.get(f.name, "")).strip():
                    add(ERROR, f"{spec.label}: “{f.label}” is empty.", scene, i)

            if t == "say" and cmd.get("character") and cmd["character"] not in story.characters:
                add(WARNING, f"Speaker “{cmd['character']}” is not in the Characters list; "
                             "their id will be shown as the name.", scene, i)
            elif t == "jump":
                check_scene_ref(cmd.get("scene"), scene, i, "Jump")
            elif t == "if":
                check_condition(cmd.get("condition"), scene, i)
                check_scene_ref(cmd.get("then_scene"), scene, i, "If")
                check_scene_ref(cmd.get("else_scene"), scene, i, "Else")
                if not cmd.get("then_scene") and not cmd.get("else_scene"):
                    add(WARNING, "This If has no scenes to go to, so it does nothing.", scene, i)
            elif t == "choice":
                opts = cmd.get("options") or []
                if not opts:
                    add(ERROR, "This choice has no options.", scene, i)
                for n, opt in enumerate(opts, 1):
                    if not opt.get("text", "").strip():
                        add(ERROR, f"Option {n} has no text.", scene, i)
                    check_scene_ref(opt.get("target"), scene, i, f"Option {n}")
                    check_condition(opt.get("condition"), scene, i, f"Option {n} condition")
                    try:
                        parse_statements(opt.get("effects", ""))
                    except ExpressionError as exc:
                        add(ERROR, f"Option {n} effects: {exc}", scene, i)
                if opts and all(o.get("condition") for o in opts):
                    add(INFO, "Every option has a condition; if none are true the choice is skipped.",
                        scene, i)
            elif t == "set":
                name = cmd.get("variable", "")
                if name and not name.isidentifier():
                    add(ERROR, f"“{name}” is not a valid variable name (use letters, numbers and _).",
                        scene, i)
                if cmd.get("operation") not in (None, "=", "+=", "-=", "*=", "/="):
                    add(ERROR, f"Unknown operation “{cmd.get('operation')}”.", scene, i)
            elif t in ("show", "move") and cmd.get("position") not in POSITIONS:
                add(ERROR, f"Unknown position “{cmd.get('position')}”.", scene, i)

            if t in ("background", "show", "animation"):
                check_asset(cmd.get("image", ""), scene, i, "Image")
            if t in ("music", "sound"):
                check_asset(cmd.get("file", ""), scene, i, "Audio")
            if t == "show" and cmd.get("character") in story.characters and not cmd.get("image"):
                chars = story.characters[cmd["character"]]
                expr = cmd.get("expression") or "default"
                if expr not in (chars.get("images") or {}):
                    add(WARNING, f"“{cmd['character']}” has no “{expr}” expression; "
                                 "the default image will be used.", scene, i)

        if cmds and cmds[-1].get("type") not in ("jump", "end", "choice"):
            last_if = cmds[-1].get("type") == "if"
            add(INFO if last_if else WARNING,
                "This scene doesn't end with a Jump, Choice or End, so the story "
                "will end here if it reaches the last command.", scene, len(cmds) - 1)

    reachable = story.reachable_scenes()
    for scene in story.scenes:
        if scene not in reachable:
            add(WARNING, "No choice or jump leads to this scene, so players can never see it.",
                scene)

    order = {ERROR: 0, WARNING: 1, INFO: 2}
    issues.sort(key=lambda i: order[i.level])
    return issues
