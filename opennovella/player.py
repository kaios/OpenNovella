"""The game window: plays an OpenNovella story with pygame.

Controls (also listed in the README):

    Click / Space / Enter / Scroll down   next line
    Esc / Right click                     game menu
    H / Scroll up                         dialogue history
    A                                     auto mode on/off
    Ctrl (hold) / Tab (toggle)            skip
    V / Middle click                      hide the text box
    F5 / F9                               quick save / quick load
    F11 / Alt+Enter                       fullscreen
    1-9                                   pick a choice
"""

from __future__ import annotations

import json
import logging
import math
import os
import random
import sys
import time
import traceback

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
import pygame  # noqa: E402

from . import __version__  # noqa: E402
from .assets import AssetManager, hex_color  # noqa: E402
from .engine import Engine, EngineError, Event  # noqa: E402
from .story import POSITIONS, Story  # noqa: E402

log = logging.getLogger("opennovella")

SLOTS_PER_PAGE = 6
SAVE_PAGES = 5
CREDIT_LINE = "Made with OpenNovella  •  engine by Shawn Rapaz & Claude Code"


# --------------------------------------------------------------------------
# Small helpers
# --------------------------------------------------------------------------

def ease_out(k: float) -> float:
    return 1 - (1 - k) ** 3


def ease_in_out(k: float) -> float:
    return 4 * k ** 3 if k < 0.5 else 1 - (-2 * k + 2) ** 3 / 2


def linear(k: float) -> float:
    return k


class Tween:
    """Animates a number from ``a`` to ``b`` over ``dur`` seconds."""

    def __init__(self, a: float, b: float, start: float = 0.0, dur: float = 0.0, ease=ease_out):
        self.a, self.b, self.start, self.dur, self.ease = a, b, start, max(dur, 0.0), ease

    def value(self, now: float) -> float:
        if self.dur <= 0 or now >= self.start + self.dur:
            return self.b
        if now <= self.start:
            return self.a
        return self.a + (self.b - self.a) * self.ease((now - self.start) / self.dur)

    def done(self, now: float) -> bool:
        return self.dur <= 0 or now >= self.start + self.dur

    def finish(self) -> None:
        self.dur = 0


def wrap_text(text: str, font: pygame.font.Font, width: int) -> list[str]:
    lines: list[str] = []
    for para in text.split("\n"):
        words = para.split(" ")
        line = ""
        for word in words:
            test = f"{line} {word}" if line else word
            if font.size(test)[0] <= width or not line:
                # very long single words are split by character
                while font.size(test)[0] > width and len(test) > 1 and not line:
                    cut = len(test)
                    while cut > 1 and font.size(test[:cut])[0] > width:
                        cut -= 1
                    lines.append(test[:cut])
                    test = test[cut:]
                line = test
            else:
                lines.append(line)
                line = word
        lines.append(line)
    return lines


def draw_panel(surf, rect, color=(20, 20, 30), alpha=210, radius=14, border=None):
    panel = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(panel, (*color[:3], alpha), panel.get_rect(), border_radius=radius)
    if border:
        pygame.draw.rect(panel, border, panel.get_rect(), width=2, border_radius=radius)
    surf.blit(panel, rect.topleft)


def text_shadow(surf, font, text, color, pos, center=False, shadow=(0, 0, 0)):
    img = font.render(text, True, color)
    sh = font.render(text, True, shadow)
    r = img.get_rect()
    if center:
        r.center = pos
    else:
        r.topleft = pos
    surf.blit(sh, (r.x + 2, r.y + 2))
    surf.blit(img, r)
    return r


# --------------------------------------------------------------------------
# Widgets
# --------------------------------------------------------------------------

class Button:
    def __init__(self, rect, text, callback, enabled=True, small=False):
        self.rect = pygame.Rect(rect)
        self.text = text
        self.callback = callback
        self.enabled = enabled
        self.small = small
        self.hover = False

    def handle(self, event, mouse) -> bool:
        if event.type == pygame.MOUSEMOTION:
            self.hover = self.rect.collidepoint(mouse)
        elif event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            if self.enabled and self.rect.collidepoint(mouse):
                self.callback()
                return True
        return False

    def draw(self, surf, player):
        accent = player.accent
        if self.small:
            font = player.font(int(20 * player.ui))
            color = accent if self.hover and self.enabled else (200, 200, 215) if self.enabled else (110, 110, 120)
            img = font.render(self.text, True, color)
            surf.blit(img, img.get_rect(center=self.rect.center))
            return
        if not self.enabled:
            bg, fg = (40, 40, 50), (120, 120, 130)
        elif self.hover:
            bg, fg = accent, (20, 15, 30)
        else:
            bg, fg = (30, 28, 45), (235, 235, 245)
        draw_panel(surf, self.rect, bg, 230, radius=int(12 * player.ui),
                   border=(*accent[:3], 160) if self.enabled and not self.hover else None)
        font = player.font(int(26 * player.ui))
        img = font.render(self.text, True, fg)
        if img.get_width() > self.rect.width - 16:
            img = pygame.transform.smoothscale(
                img, (self.rect.width - 16, int(img.get_height() * (self.rect.width - 16) / img.get_width())))
        surf.blit(img, img.get_rect(center=self.rect.center))


class Slider:
    def __init__(self, rect, label, lo, hi, value, on_change, fmt="{:.0f}"):
        self.rect = pygame.Rect(rect)
        self.label, self.lo, self.hi, self.value = label, lo, hi, value
        self.on_change, self.fmt = on_change, fmt
        self.dragging = False

    def _set(self, x):
        k = min(1, max(0, (x - self.rect.x) / self.rect.width))
        self.value = self.lo + (self.hi - self.lo) * k
        self.on_change(self.value)

    def handle(self, event, mouse) -> bool:
        hit = self.rect.inflate(0, 24).collidepoint(mouse)
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1 and hit:
            self.dragging = True
            self._set(mouse[0])
            return True
        if event.type == pygame.MOUSEMOTION and self.dragging:
            self._set(mouse[0])
            return True
        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self.dragging = False
        return False

    def draw(self, surf, player):
        font = player.font(int(24 * player.ui))
        surf.blit(font.render(f"{self.label}: {self.fmt.format(self.value)}", True, (230, 230, 240)),
                  (self.rect.x, self.rect.y - int(34 * player.ui)))
        pygame.draw.rect(surf, (60, 60, 80), self.rect, border_radius=6)
        k = (self.value - self.lo) / (self.hi - self.lo) if self.hi != self.lo else 0
        fill = self.rect.copy()
        fill.width = int(self.rect.width * k)
        pygame.draw.rect(surf, player.accent, fill, border_radius=6)
        pygame.draw.circle(surf, (255, 255, 255), (self.rect.x + fill.width, self.rect.centery),
                           int(self.rect.height * 0.9))


# --------------------------------------------------------------------------
# Visual objects in the game scene
# --------------------------------------------------------------------------

class SpriteView:
    def __init__(self, sid, anim, x, now):
        self.id = sid
        self.anim = anim
        self.t0 = now
        self.x = Tween(x, x)
        self.alpha = Tween(255, 255)
        self.dy = Tween(0, 0)
        self.scale = Tween(1, 1)
        self.effect = ""          # one-shot: bounce / shake / jump
        self.effect_t0 = 0.0
        self.effect_dur = 0.0
        self.loop_effect = "none"  # float / pulse
        self.removing = False

    def busy(self, now) -> bool:
        return not all(t.done(now) for t in (self.x, self.alpha, self.dy, self.scale))

    def finish(self):
        for t in (self.x, self.alpha, self.dy, self.scale):
            t.finish()
        self.effect = ""

    def draw(self, surf, now, scr_w, scr_h):
        frame = self.anim.frame(now - self.t0)
        scale = self.scale.value(now)
        ox, oy = 0.0, self.dy.value(now)
        if self.effect:
            k = (now - self.effect_t0) / max(self.effect_dur, 0.01)
            if k >= 1:
                self.effect = ""
            elif self.effect == "bounce":
                oy -= abs(math.sin(k * math.pi * 2)) * scr_h * 0.04 * (1 - k * 0.5)
            elif self.effect == "jump":
                oy -= math.sin(k * math.pi) * scr_h * 0.09
            elif self.effect == "shake":
                ox += math.sin(k * 60) * scr_w * 0.012 * (1 - k)
        if self.loop_effect == "float":
            oy += math.sin((now - self.t0) * 2.2) * scr_h * 0.012
        elif self.loop_effect == "pulse":
            scale *= 1 + 0.025 * math.sin((now - self.t0) * 3.5)
        if abs(scale - 1) > 0.001:
            w, h = frame.get_size()
            frame = pygame.transform.smoothscale(frame, (max(1, int(w * scale)), max(1, int(h * scale))))
        alpha = int(max(0, min(255, self.alpha.value(now))))
        if alpha <= 0:
            return
        frame.set_alpha(alpha)
        w, h = frame.get_size()
        cx = self.x.value(now) * scr_w + ox
        surf.blit(frame, (int(cx - w / 2), int(scr_h - h + oy)))
        frame.set_alpha(255)


class Overlay:
    def __init__(self, oid, anim, position, loops, now):
        self.id, self.anim, self.position, self.loops, self.t0 = oid, anim, position, loops, now

    def finished(self, now) -> bool:
        return self.loops > 0 and now - self.t0 >= self.anim.total * self.loops

    def draw(self, surf, now, scr_w, scr_h):
        loop = self.loops != 1
        frame = self.anim.frame(now - self.t0, loop=loop)
        if self.position == "fullscreen":
            surf.blit(frame, (0, 0))
        else:
            cx = POSITIONS.get(self.position, 0.5) * scr_w
            surf.blit(frame, frame.get_rect(center=(int(cx), int(scr_h * 0.45))))


# --------------------------------------------------------------------------
# The in-game view
# --------------------------------------------------------------------------

class GameView:
    def __init__(self, player: "Player", engine: Engine):
        self.p = player
        self.engine = engine
        self.now = 0.0
        self.mode = "run"            # run, text, choice, timer, ending, error
        self.timer_end = 0.0
        self.bg = None               # (anim or None, color)
        self.bg_old = None
        self.bg_trans = ""
        self.bg_tween = Tween(1, 1)
        self.sprites: dict[str, SpriteView] = {}
        self.overlays: list[Overlay] = []
        self.shake = Tween(0, 0)
        self.flash = Tween(0, 0)
        self.flash_color = (255, 255, 255)
        self.cover = Tween(0, 0)
        self.cover_color = (0, 0, 0)
        self.tint = Tween(0, 0)
        self.tint_color = (0, 0, 0)
        self.say: Event | None = None
        self.say_lines: list[str] = []
        self.revealed = 0.0
        self.text_done_at = 0.0
        self.choice_buttons: list[Button] = []
        self.choice_prompt = ""
        self.ending: Event | None = None
        self.auto = False
        self.skip_toggle = False
        self.hide_ui = False
        self.error = ""
        self.quick_buttons = self._make_quick_buttons()
        self.sync_from_engine()

    # ----- setup ---------------------------------------------------------
    @property
    def skipping(self) -> bool:
        return self.skip_toggle or bool(pygame.key.get_mods() & pygame.KMOD_CTRL)

    def dur(self, seconds) -> float:
        try:
            seconds = float(seconds or 0)
        except (TypeError, ValueError):
            seconds = 0
        return 0.0 if self.skipping else max(0.0, seconds)

    def _make_quick_buttons(self):
        p = self.p
        labels = [("History", lambda: p.push(HistoryScreen(p))),
                  ("Auto", self.toggle_auto),
                  ("Skip", self.toggle_skip),
                  ("Save", lambda: p.push(SaveLoadScreen(p, "save"))),
                  ("Load", lambda: p.push(SaveLoadScreen(p, "load"))),
                  ("Menu", lambda: p.push(PauseMenu(p)))]
        w, h = int(78 * p.ui), int(28 * p.ui)
        x = p.W - len(labels) * w - int(40 * p.ui)
        y = p.H - h - int(4 * p.ui)
        return [Button((x + i * w, y, w, h), text, cb, small=True) for i, (text, cb) in enumerate(labels)]

    def toggle_auto(self):
        self.auto = not self.auto
        self.p.toast("Auto mode on" if self.auto else "Auto mode off")

    def toggle_skip(self):
        self.skip_toggle = not self.skip_toggle
        self.p.toast("Skipping" if self.skip_toggle else "Skip off")

    def bg_anim(self, image, color):
        if not image:
            return None
        return self.p.assets.image(image, kind="background", label=os.path.basename(image), color=color)

    def sprite_anim(self, entry):
        img = self.engine.sprite_image(entry)
        char = self.engine.story.characters.get(entry.get("character", ""), {})
        label = char.get("name") or entry.get("character") or os.path.basename(img)
        return self.p.assets.image(img, kind="sprite", label=label, color=char.get("color", ""))

    def sync_from_engine(self):
        """Rebuild everything on screen from the engine state (used after loading)."""
        e = self.engine
        self.bg = (self.bg_anim(e.background.get("image"), e.background.get("color")),
                   hex_color(e.background.get("color"), (0, 0, 0)))
        self.bg_old = None
        self.sprites.clear()
        for sid, entry in e.shown.items():
            sv = SpriteView(sid, self.sprite_anim(entry), POSITIONS.get(entry["position"], 0.5), self.now)
            sv.loop_effect = entry.get("effect", "none")
            self.sprites[sid] = sv
        self.overlays = [Overlay(aid, self.p.assets.image(a["image"], fps=float(a.get("fps") or 12),
                                                          kind=self._overlay_kind(a["position"])),
                                 a["position"], 0, self.now)
                         for aid, a in e.animations.items()]
        self.tint_color = hex_color(e.tint, (0, 0, 0)) if e.tint else (0, 0, 0)
        self.tint = Tween(110 if e.tint else 0, 110 if e.tint else 0)
        if len(self.tint_color) == 4:
            self.tint = Tween(self.tint_color[3], self.tint_color[3])
        self.cover_color = hex_color(e.cover, (0, 0, 0)) if e.cover else (0, 0, 0)
        self.cover = Tween(255 if e.cover else 0, 255 if e.cover else 0)
        self.p.play_music(e.music, fade=0.5)

    @staticmethod
    def _overlay_kind(position):
        return "overlay_full" if position == "fullscreen" else "overlay"

    # ----- story events --------------------------------------------------
    def advance(self):
        """Continue the story until something needs the player."""
        self.mode = "run"
        self.say = None
        self.choice_buttons = []
        try:
            while self.mode == "run":
                self.handle(self.engine.step())
        except EngineError as exc:
            self.show_error(str(exc))

    def show_error(self, msg):
        self.mode = "error"
        self.error = msg
        log.error(msg)

    def handle(self, ev: Event):
        cmd, t, now = ev.cmd, ev.type, self.now
        if t == "say":
            cid = ev["character"]
            if cmd.get("expression") and cid in self.sprites and cid in self.engine.shown:
                self.sprites[cid].anim = self.sprite_anim(self.engine.shown[cid])
            self.say = ev
            self.say_lines = []
            self.revealed = 0.0
            self.text_done_at = 0.0
            self.mode = "text"
            if self.p.text_speed <= 0 or self.skipping:
                self.revealed = len(ev["text"])
        elif t == "choice":
            self.skip_toggle = False
            self.make_choice(ev)
            self.mode = "choice"
        elif t == "wait":
            self.start_timer(self.dur(cmd.get("seconds", 1)))
        elif t == "end":
            self.ending = ev
            self.mode = "ending"
            self.skip_toggle = False
            self.auto = False
            self.p.record_ending(ev.get("ending") or ev.get("text"))
        elif t == "background":
            self.change_background(cmd)
        elif t == "show":
            self.show_sprite(ev)
        elif t == "hide":
            self.hide_sprite(ev)
        elif t == "move":
            sv = self.sprites.get(ev["id"])
            if sv:
                target = POSITIONS.get(cmd.get("position"), 0.5)
                sv.x = Tween(sv.x.value(now), target, now, self.dur(cmd.get("duration", 0.6)), ease_in_out)
        elif t == "effect":
            self.screen_effect(cmd)
        elif t == "animation":
            self.play_animation(cmd)
        elif t == "stop_animation":
            aid = ev.get("id")
            self.overlays = [o for o in self.overlays if aid and o.id != aid]
        elif t == "music":
            self.p.play_music(self.engine.music, fade=float(cmd.get("fade") or 0))
        elif t == "stop_music":
            self.p.play_music(None, fade=float(cmd.get("fade") or 0))
        elif t == "sound":
            self.p.play_sound(cmd.get("file"))

    def start_timer(self, seconds):
        if seconds > 0:
            self.mode = "timer"
            self.timer_end = self.now + seconds

    def change_background(self, cmd):
        new = (self.bg_anim(cmd.get("image"), cmd.get("color")), hex_color(cmd.get("color"), (0, 0, 0)))
        trans = cmd.get("transition") or "none"
        d = self.dur(cmd.get("duration", 0.8))
        if cmd.get("clear_characters"):
            for sv in self.sprites.values():
                sv.removing = True
                sv.alpha = Tween(sv.alpha.value(self.now), 0, self.now, d * 0.5 if trans != "none" else 0)
        if trans == "none" or d <= 0:
            self.bg, self.bg_old = new, None
            return
        self.bg_old, self.bg = self.bg, new
        self.bg_trans = trans
        self.bg_tween = Tween(0, 1, self.now, d, linear if trans in ("fade", "dissolve") else ease_in_out)
        self.start_timer(d)

    def show_sprite(self, ev):
        cmd, entry, now = ev.cmd, ev["entry"], self.now
        sid = ev["id"]
        anim = self.sprite_anim(entry)
        target = POSITIONS.get(entry["position"], 0.5)
        d = self.dur(cmd.get("duration", 0.5))
        trans = cmd.get("transition") or "none"
        sv = self.sprites.get(sid)
        if sv and not sv.removing:
            # Already on screen: swap the image (and slide if the position changed).
            sv.anim, sv.removing = anim, False
            if abs(sv.x.b - target) > 0.001:
                sv.x = Tween(sv.x.value(now), target, now, d, ease_in_out)
            sv.alpha = Tween(sv.alpha.value(now), 255, now, d * 0.5)
        else:
            sv = SpriteView(sid, anim, target, now)
            if trans == "fade":
                sv.alpha = Tween(0, 255, now, d)
            elif trans == "slide_left":
                sv.x = Tween(-0.25, target, now, d)
                sv.alpha = Tween(0, 255, now, d * 0.5)
            elif trans == "slide_right":
                sv.x = Tween(1.25, target, now, d)
                sv.alpha = Tween(0, 255, now, d * 0.5)
            elif trans == "slide_up":
                sv.dy = Tween(self.p.H * 0.4, 0, now, d)
                sv.alpha = Tween(0, 255, now, d * 0.6)
            elif trans == "zoom":
                sv.scale = Tween(0.6, 1, now, d)
                sv.alpha = Tween(0, 255, now, d)
            self.sprites[sid] = sv
        sv.loop_effect = entry.get("effect", "none")
        effect = cmd.get("effect") or "none"
        if effect in ("bounce", "shake", "jump") and not self.skipping:
            sv.effect, sv.effect_t0 = effect, now + (d if trans != "none" and not ev["was_shown"] else 0)
            sv.effect_dur = {"bounce": 0.7, "shake": 0.5, "jump": 0.45}[effect]

    def hide_sprite(self, ev):
        sv = self.sprites.get(ev["id"])
        if not sv:
            return
        cmd, now = ev.cmd, self.now
        d = self.dur(cmd.get("duration", 0.5))
        trans = cmd.get("transition") or "none"
        sv.removing = True
        if trans == "none" or d <= 0:
            del self.sprites[ev["id"]]
            return
        sv.alpha = Tween(sv.alpha.value(now), 0, now, d)
        if trans == "slide_left":
            sv.x = Tween(sv.x.value(now), -0.3, now, d, ease_in_out)
        elif trans == "slide_right":
            sv.x = Tween(sv.x.value(now), 1.3, now, d, ease_in_out)
        elif trans == "slide_down":
            sv.dy = Tween(0, self.p.H * 0.4, now, d, ease_in_out)
        elif trans == "zoom":
            sv.scale = Tween(1, 1.3, now, d)

    def screen_effect(self, cmd):
        effect = cmd.get("effect", "shake")
        d = self.dur(cmd.get("duration", 0.5))
        color = hex_color(cmd.get("color"), (255, 255, 255))
        now = self.now
        if effect == "shake":
            self.shake = Tween(1, 0, now, d, linear)
        elif effect == "flash":
            self.flash_color = color[:3]
            self.flash = Tween(255, 0, now, d, ease_out)
        elif effect == "fade_out":
            self.cover_color = color[:3]
            self.cover = Tween(self.cover.value(now), 255, now, d, linear)
        elif effect == "fade_in":
            self.cover = Tween(self.cover.value(now), 0, now, d, linear)
        elif effect == "tint":
            self.tint_color = color[:3]
            self.tint = Tween(self.tint.value(now), color[3] if len(color) == 4 else 110, now, d)
        elif effect == "clear_tint":
            self.tint = Tween(self.tint.value(now), 0, now, d)
        if cmd.get("wait", True):
            self.start_timer(d)

    def play_animation(self, cmd):
        image = cmd.get("image")
        if not image:
            return
        position = cmd.get("position") or "fullscreen"
        try:
            loops = max(0, int(float(cmd.get("loops") or 0)))
        except ValueError:
            loops = 1
        try:
            fps = float(cmd.get("fps") or 12)
        except ValueError:
            fps = 12
        anim = self.p.assets.image(image, fps=fps, kind=self._overlay_kind(position))
        oid = cmd.get("id") or image
        self.overlays = [o for o in self.overlays if o.id != oid]
        if self.skipping and loops > 0:
            return
        self.overlays.append(Overlay(oid, anim, position, loops, self.now))
        if cmd.get("wait") and loops > 0:
            self.start_timer(anim.total * loops)

    def make_choice(self, ev):
        p = self.p
        opts = ev["options"]
        self.choice_prompt = ev.get("prompt", "")
        w = int(p.W * 0.55)
        h = int(56 * p.ui)
        gap = int(16 * p.ui)
        total = len(opts) * h + (len(opts) - 1) * gap
        y = int(p.H * 0.42 - total / 2)
        self.choice_buttons = []
        for i, opt in enumerate(opts):
            label = f"{opt['text']}"
            self.choice_buttons.append(Button(((p.W - w) // 2, y + i * (h + gap), w, h), label,
                                              lambda i=i: self.pick(i)))

    def pick(self, i):
        try:
            self.engine.choose(i)
        except EngineError as exc:
            self.show_error(str(exc))
            return
        self.p.play_ui_sound()
        self.advance()

    # ----- input ---------------------------------------------------------
    def click(self):
        """Primary action: finish the current animation/text or go on."""
        if self.hide_ui:
            self.hide_ui = False
            return
        if self.mode == "text":
            if self.revealed < len(self.say["text"]):
                self.revealed = len(self.say["text"])
            else:
                self.advance()
        elif self.mode == "timer":
            self.finish_animations()
            self.mode = "run"
            self.advance()
        elif self.mode == "ending":
            self.p.return_to_title()
        elif self.mode == "error":
            self.p.return_to_title()

    def finish_animations(self):
        self.bg_tween.finish()
        self.bg_old = None
        for sv in list(self.sprites.values()):
            sv.finish()
        for tw in (self.shake, self.flash, self.cover, self.tint):
            tw.finish()

    def handle_input(self, event, mouse) -> None:
        if self.mode == "choice" and not self.hide_ui:
            for b in self.choice_buttons:
                if b.handle(event, mouse):
                    return
        if not self.hide_ui and self.mode not in ("ending", "error"):
            for b in self.quick_buttons:
                if b.handle(event, mouse):
                    return
        if event.type == pygame.MOUSEBUTTONUP:
            if event.button == 1 and self.mode != "choice":
                self.click()
            elif event.button == 3:
                self.p.push(PauseMenu(self.p))
            elif event.button == 2:
                self.hide_ui = not self.hide_ui
        elif event.type == pygame.MOUSEWHEEL:
            if event.y > 0:
                self.p.push(HistoryScreen(self.p))
            elif event.y < 0 and self.mode != "choice":
                self.click()
        elif event.type == pygame.KEYDOWN:
            k = event.key
            if k in (pygame.K_SPACE, pygame.K_RETURN, pygame.K_KP_ENTER) and not (event.mod & pygame.KMOD_ALT):
                if self.mode != "choice":
                    self.click()
            elif k == pygame.K_ESCAPE:
                if self.hide_ui:
                    self.hide_ui = False
                elif self.mode in ("ending", "error"):
                    self.p.return_to_title()
                else:
                    self.p.push(PauseMenu(self.p))
            elif k == pygame.K_h:
                self.p.push(HistoryScreen(self.p))
            elif k == pygame.K_a:
                self.toggle_auto()
            elif k == pygame.K_TAB:
                self.toggle_skip()
            elif k == pygame.K_v:
                self.hide_ui = not self.hide_ui
            elif k == pygame.K_F5:
                self.p.save_slot("quick")
            elif k == pygame.K_F9:
                self.p.load_slot("quick")
            elif self.mode == "choice" and pygame.K_1 <= k <= pygame.K_9:
                i = k - pygame.K_1
                if i < len(self.choice_buttons):
                    self.pick(i)

    # ----- update / draw -------------------------------------------------
    def update(self, dt):
        self.now += dt
        now = self.now
        for sid in [s for s, sv in self.sprites.items() if sv.removing and not sv.busy(now)]:
            del self.sprites[sid]
        self.overlays = [o for o in self.overlays if not o.finished(now)]
        if self.bg_old is not None and self.bg_tween.done(now):
            self.bg_old = None

        if self.mode == "timer" and now >= self.timer_end:
            self.advance()
        elif self.mode == "text":
            total = len(self.say["text"])
            if self.revealed < total:
                self.revealed = min(total, self.revealed + dt * max(self.p.text_speed, 1))
                if self.p.text_speed <= 0:
                    self.revealed = total
                if self.revealed >= total:
                    self.text_done_at = now
            elif self.text_done_at == 0:
                self.text_done_at = now
            if self.skipping and not self.p.stack:
                self.finish_animations()
                self.advance()
            elif self.auto and self.revealed >= total and not self.p.stack:
                wait = self.p.prefs["auto_delay"] + total * 0.02
                if now - self.text_done_at >= wait:
                    self.advance()
        elif self.mode == "run":
            self.advance()

    def draw_background(self, surf, bg, alpha=255, offset=(0, 0)):
        anim, color = bg
        if alpha >= 255 and offset == (0, 0):
            if anim:
                surf.blit(anim.frame(self.now), (0, 0))
            else:
                surf.fill(color[:3])
            return
        layer = pygame.Surface(surf.get_size())
        if anim:
            layer.blit(anim.frame(self.now), (0, 0))
        else:
            layer.fill(color[:3])
        layer.set_alpha(int(alpha))
        surf.blit(layer, offset)

    def draw(self, surf):
        p, now = self.p, self.now
        W, H = p.W, p.H
        scene = p.scene_surface
        scene.fill((0, 0, 0))

        # Background (with transition)
        if self.bg_old is not None and not self.bg_tween.done(now):
            k = self.bg_tween.value(now)
            if self.bg_trans == "fade":
                if k < 0.5:
                    self.draw_background(scene, self.bg_old, 255 * (1 - k * 2))
                else:
                    self.draw_background(scene, self.bg, 255 * (k - 0.5) * 2)
            elif self.bg_trans in ("slide_left", "slide_right"):
                sign = -1 if self.bg_trans == "slide_left" else 1
                self.draw_background(scene, self.bg_old, 255, (int(sign * W * k), 0))
                self.draw_background(scene, self.bg, 255, (int(sign * W * (k - 1)), 0))
            else:  # dissolve
                self.draw_background(scene, self.bg_old)
                self.draw_background(scene, self.bg, 255 * k)
        elif self.bg:
            self.draw_background(scene, self.bg)

        for sv in self.sprites.values():
            sv.draw(scene, now, W, H)
        for ov in self.overlays:
            ov.draw(scene, now, W, H)

        tint = self.tint.value(now)
        if tint > 0:
            layer = pygame.Surface((W, H))
            layer.fill(self.tint_color[:3])
            layer.set_alpha(int(tint))
            scene.blit(layer, (0, 0))
        cover = self.cover.value(now)
        if cover > 0:
            layer = pygame.Surface((W, H))
            layer.fill(self.cover_color[:3])
            layer.set_alpha(int(cover))
            scene.blit(layer, (0, 0))

        shake = self.shake.value(now)
        if shake > 0:
            off = (int(random.uniform(-1, 1) * W * 0.015 * shake), int(random.uniform(-1, 1) * H * 0.015 * shake))
            surf.fill((0, 0, 0))
            surf.blit(scene, off)
        else:
            surf.blit(scene, (0, 0))

        flash = self.flash.value(now)
        if flash > 0:
            layer = pygame.Surface((W, H))
            layer.fill(self.flash_color)
            layer.set_alpha(int(flash))
            surf.blit(layer, (0, 0))

        if self.hide_ui:
            return
        if self.mode == "text" and self.say:
            self.draw_textbox(surf)
        elif self.mode == "choice":
            self.draw_choice(surf)
        elif self.mode == "ending":
            self.draw_ending(surf)
        elif self.mode == "error":
            self.draw_error(surf)
        if self.mode not in ("ending", "error"):
            for b in self.quick_buttons:
                b.draw(surf, p)
            flags = []
            if self.auto:
                flags.append("AUTO")
            if self.skipping:
                flags.append("SKIP ▶▶")
            if flags:
                f = p.font(int(22 * p.ui), bold=True)
                text_shadow(surf, f, "  ".join(flags), p.accent, (int(20 * p.ui), int(14 * p.ui)))

    def textbox_rect(self):
        p = self.p
        m = int(36 * p.ui)
        h = int(p.H * 0.26)
        return pygame.Rect(m, p.H - h - int(34 * p.ui), p.W - m * 2, h)

    def draw_textbox(self, surf):
        p, ev = self.p, self.say
        box = self.textbox_rect()
        st = p.story.settings
        draw_panel(surf, box, hex_color(st.get("textbox_color"), (20, 20, 30)),
                   int(st.get("textbox_opacity", 200)), radius=int(16 * p.ui))
        pad = int(28 * p.ui)
        font = p.text_font
        if not self.say_lines:
            self.say_lines = wrap_text(ev["text"], font, box.width - pad * 2)
        if ev["name"]:
            nfont = p.name_font
            name_img = nfont.render(ev["name"], True, hex_color(ev["color"], (255, 255, 255))[:3])
            tag = pygame.Rect(box.x + pad - int(10 * p.ui), box.y - name_img.get_height() - int(14 * p.ui),
                              name_img.get_width() + int(32 * p.ui), name_img.get_height() + int(16 * p.ui))
            draw_panel(surf, tag, hex_color(st.get("textbox_color"), (20, 20, 30)),
                       min(255, int(st.get("textbox_opacity", 200)) + 30), radius=int(12 * p.ui))
            surf.blit(name_img, (tag.x + int(16 * p.ui), tag.y + int(8 * p.ui)))
        remaining = int(self.revealed)
        color = hex_color(st.get("text_color"), (244, 244, 248))[:3]
        y = box.y + pad
        line_h = font.get_linesize() + int(4 * p.ui)
        last_end = (box.x + pad, y)
        for line in self.say_lines:
            if remaining <= 0:
                break
            part = line[:remaining]
            remaining -= len(line) + 1   # +1 for the space/newline the wrap removed
            img = font.render(part, True, color)
            surf.blit(img, (box.x + pad, y))
            last_end = (box.x + pad + img.get_width(), y)
            y += line_h
            if y > box.bottom - line_h * 0.6:
                break
        if self.revealed >= len(ev["text"]):
            # blinking "continue" indicator
            if int(self.now * 2.5) % 2 == 0:
                x, yy = last_end[0] + int(12 * p.ui), last_end[1] + font.get_height() // 2
                s = int(7 * p.ui)
                pygame.draw.polygon(surf, p.accent, [(x, yy - s // 2), (x + s * 2, yy - s // 2), (x + s, yy + s)])

    def draw_choice(self, surf):
        p = self.p
        if self.choice_prompt:
            box = self.textbox_rect()
            draw_panel(surf, box, hex_color(p.story.settings.get("textbox_color"), (20, 20, 30)),
                       int(p.story.settings.get("textbox_opacity", 200)), radius=int(16 * p.ui))
            pad = int(28 * p.ui)
            y = box.y + pad
            for line in wrap_text(self.choice_prompt, p.text_font, box.width - pad * 2):
                surf.blit(p.text_font.render(line, True, (240, 240, 250)), (box.x + pad, y))
                y += p.text_font.get_linesize() + 4
        for b in self.choice_buttons:
            b.draw(surf, p)

    def draw_ending(self, surf):
        p = self.p
        dim = pygame.Surface((p.W, p.H), pygame.SRCALPHA)
        dim.fill((0, 0, 0, 170))
        surf.blit(dim, (0, 0))
        text_shadow(surf, p.font(int(64 * p.ui), bold=True), self.ending["text"], (255, 255, 255),
                    (p.W // 2, int(p.H * 0.42)), center=True)
        if self.ending.get("ending"):
            text_shadow(surf, p.font(int(30 * p.ui)), self.ending["ending"], p.accent,
                        (p.W // 2, int(p.H * 0.53)), center=True)
        text_shadow(surf, p.font(int(22 * p.ui)), "Click to return to the title screen",
                    (190, 190, 200), (p.W // 2, int(p.H * 0.66)), center=True)

    def draw_error(self, surf):
        p = self.p
        box = pygame.Rect(p.W * 0.12, p.H * 0.25, p.W * 0.76, p.H * 0.45)
        draw_panel(surf, box, (60, 15, 25), 240, border=(255, 120, 140))
        y = box.y + 24
        f = p.font(int(30 * p.ui), bold=True)
        surf.blit(f.render("Oops - the story hit a problem", True, (255, 220, 225)), (box.x + 24, y))
        y += f.get_linesize() + 10
        for line in wrap_text(self.error + "\n\nOpen the story in the OpenNovella editor and use "
                              "Tools → Check Story to find the problem. Click to return to the title.",
                              p.font(int(24 * p.ui)), box.width - 48):
            surf.blit(p.font(int(24 * p.ui)).render(line, True, (250, 240, 240)), (box.x + 24, y))
            y += p.font(int(24 * p.ui)).get_linesize()


# --------------------------------------------------------------------------
# Menu screens
# --------------------------------------------------------------------------

class Screen:
    """Base class for menus drawn on top of the game / title."""
    opaque = False

    def __init__(self, player: "Player"):
        self.p = player
        self.buttons: list = []

    def handle(self, event, mouse):
        for b in list(self.buttons):
            if b.handle(event, mouse):
                return
        if (event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE) or \
                (event.type == pygame.MOUSEBUTTONUP and event.button == 3):
            self.close()

    def close(self):
        self.p.pop(self)

    def update(self, dt):
        pass

    def dim(self, surf, alpha=170):
        layer = pygame.Surface(surf.get_size(), pygame.SRCALPHA)
        layer.fill((8, 6, 16, alpha))
        surf.blit(layer, (0, 0))

    def title(self, surf, text, y=None):
        p = self.p
        text_shadow(surf, p.font(int(46 * p.ui), bold=True), text, (255, 255, 255),
                    (p.W // 2, y or int(p.H * 0.12)), center=True)

    def draw(self, surf):
        for b in self.buttons:
            b.draw(surf, self.p)


def column_buttons(player, items, top_frac=0.32, width_frac=0.3):
    w = int(player.W * width_frac)
    h = int(54 * player.ui)
    gap = int(14 * player.ui)
    y = int(player.H * top_frac)
    out = []
    for i, item in enumerate(items):
        text, cb = item[0], item[1]
        enabled = item[2] if len(item) > 2 else True
        out.append(Button(((player.W - w) // 2, y + i * (h + gap), w, h), text, cb, enabled))
    return out


class TitleScreen(Screen):
    opaque = True

    def __init__(self, player):
        super().__init__(player)
        self.t = 0.0
        p = player
        st = p.story.settings
        self.bg = p.assets.image(st.get("title_background"), kind="background", label=p.story.title,
                                 color=st.get("title_background_color")) if st.get("title_background") else None
        has_saves = p.latest_save() is not None
        self.buttons = column_buttons(p, [
            ("Start", p.new_game),
            ("Continue", p.continue_game, has_saves),
            ("Load", lambda: p.push(SaveLoadScreen(p, "load"))),
            ("Settings", lambda: p.push(SettingsScreen(p))),
            ("Quit", p.quit),
        ], top_frac=0.45, width_frac=0.26)
        p.play_music({"file": st["title_music"], "loop": True} if st.get("title_music") else None, fade=1.0)

    def handle(self, event, mouse):
        for b in self.buttons:
            if b.handle(event, mouse):
                return
        if event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
            self.p.new_game()

    def update(self, dt):
        self.t += dt

    def draw(self, surf):
        p = self.p
        if self.bg:
            surf.blit(self.bg.frame(self.t), (0, 0))
        else:
            base = hex_color(p.story.settings.get("title_background_color"), (27, 20, 48))
            for y in range(0, p.H, 4):
                k = y / p.H
                c = [int(base[i] * (1.25 - k * 0.6)) for i in range(3)]
                pygame.draw.rect(surf, [max(0, min(255, v)) for v in c], (0, y, p.W, 4))
            # gentle drifting light motes so the default title doesn't feel static
            for i in range(24):
                x = (i * 137 + self.t * (8 + i % 5) * 3) % p.W
                y = (i * 89 + math.sin(self.t * 0.5 + i) * 30) % p.H
                pygame.draw.circle(surf, (*p.accent[:3],), (int(x), int(y)), 2 + i % 3)
        title_font = p.font(int(76 * p.ui), bold=True)
        text_shadow(surf, title_font, p.story.title, (255, 255, 255), (p.W // 2, int(p.H * 0.22)), center=True)
        if p.story.author:
            text_shadow(surf, p.font(int(28 * p.ui)), f"by {p.story.author}", p.accent,
                        (p.W // 2, int(p.H * 0.32)), center=True)
        found = len(p.persistent.get("endings", []))
        if found:
            text_shadow(surf, p.font(int(22 * p.ui)), f"Endings found: {found}", (210, 210, 220),
                        (int(p.W * 0.86), int(p.H * 0.04)), center=True)
        super().draw(surf)
        text_shadow(surf, p.font(int(18 * p.ui)), CREDIT_LINE + f"  •  v{__version__}", (190, 190, 205),
                    (p.W // 2, p.H - int(22 * p.ui)), center=True)


class PauseMenu(Screen):
    def __init__(self, player):
        super().__init__(player)
        p = player
        self.buttons = column_buttons(p, [
            ("Resume", self.close),
            ("Save", lambda: p.push(SaveLoadScreen(p, "save"))),
            ("Load", lambda: p.push(SaveLoadScreen(p, "load"))),
            ("History", lambda: p.push(HistoryScreen(p))),
            ("Settings", lambda: p.push(SettingsScreen(p))),
            ("Main Menu", p.return_to_title),
            ("Quit", p.quit),
        ], top_frac=0.2)

    def draw(self, surf):
        self.dim(surf)
        self.title(surf, "Paused")
        super().draw(surf)


class SaveLoadScreen(Screen):
    def __init__(self, player, mode):
        super().__init__(player)
        self.mode = mode
        self.page = player.prefs.get("save_page", 0)
        self.thumbs: dict[str, pygame.Surface | None] = {}
        self.build()

    def slot_rects(self):
        p = self.p
        cols, rows = 3, 2
        w, h = int(p.W * 0.27), int(p.H * 0.3)
        gx, gy = int(p.W * 0.03), int(p.H * 0.04)
        x0 = (p.W - (cols * w + (cols - 1) * gx)) // 2
        y0 = int(p.H * 0.2)
        return [pygame.Rect(x0 + c * (w + gx), y0 + r * (h + gy), w, h) for r in range(rows) for c in range(cols)]

    def build(self):
        p = self.p
        self.buttons = []
        self.infos = []
        for i, rect in enumerate(self.slot_rects()):
            slot = str(self.page * SLOTS_PER_PAGE + i + 1)
            info = p.slot_info(slot)
            self.infos.append((slot, rect, info))
            enabled = self.mode == "save" or info is not None
            self.buttons.append(Button(rect, "", lambda s=slot: self.choose(s), enabled))
        bw, bh = int(60 * p.ui), int(44 * p.ui)
        y = int(p.H * 0.88)
        self.buttons.append(Button((p.W // 2 - bw * 3, y, bw, bh), "<", lambda: self.turn(-1), self.page > 0))
        self.buttons.append(Button((p.W // 2 + bw * 2, y, bw, bh), ">", lambda: self.turn(1),
                                   self.page < SAVE_PAGES - 1))
        self.buttons.append(Button((int(p.W * 0.82), y, int(150 * p.ui), bh), "Back", self.close))

    def turn(self, d):
        self.page = max(0, min(SAVE_PAGES - 1, self.page + d))
        self.p.prefs["save_page"] = self.page
        self.build()

    def choose(self, slot):
        if self.mode == "save":
            self.p.save_slot(slot)
            self.thumbs.pop(slot, None)
            self.build()
        else:
            self.p.load_slot(slot)

    def thumb(self, slot, size):
        if slot not in self.thumbs:
            path = self.p.slot_path(slot, ".png")
            img = None
            if os.path.isfile(path):
                try:
                    img = pygame.transform.smoothscale(pygame.image.load(path).convert(), size)
                except pygame.error:
                    img = None
            self.thumbs[slot] = img
        return self.thumbs[slot]

    def draw(self, surf):
        p = self.p
        self.dim(surf, 215)
        self.title(surf, "Save Game" if self.mode == "save" else "Load Game", int(p.H * 0.1))
        small = p.font(int(20 * p.ui))
        for b, (slot, rect, info) in zip(self.buttons, self.infos):
            b.draw(surf, p)
            inner = rect.inflate(-int(16 * p.ui), -int(16 * p.ui))
            th_h = int(inner.height * 0.62)
            th_rect = pygame.Rect(inner.x, inner.y, inner.width, th_h)
            if info:
                img = self.thumb(slot, th_rect.size)
                if img:
                    surf.blit(img, th_rect)
                else:
                    pygame.draw.rect(surf, (50, 50, 70), th_rect)
                lines = [time.strftime("%Y-%m-%d %H:%M", time.localtime(info.get("time", 0))),
                         info.get("preview", "")[:48]]
            else:
                pygame.draw.rect(surf, (35, 35, 50), th_rect, border_radius=6)
                lines = [f"Slot {slot}", "Empty"]
            fg = (20, 15, 30) if b.hover and b.enabled else (225, 225, 235)
            y = th_rect.bottom + int(6 * p.ui)
            for line in lines:
                surf.blit(small.render(line, True, fg), (inner.x, y))
                y += small.get_linesize()
        for b in self.buttons[len(self.infos):]:
            b.draw(surf, p)
        text_shadow(surf, p.font(int(24 * p.ui)), f"Page {self.page + 1} / {SAVE_PAGES}", (220, 220, 230),
                    (p.W // 2, int(p.H * 0.88) + int(22 * p.ui)), center=True)


class HistoryScreen(Screen):
    def __init__(self, player):
        super().__init__(player)
        p = player
        self.scroll = 0
        self.buttons = [Button((int(p.W * 0.82), int(p.H * 0.88), int(150 * p.ui), int(44 * p.ui)),
                               "Back", self.close)]
        game = p.game
        self.entries = list(game.engine.history) if game else []
        self.layout()
        self.scroll = max(0, self.content_h - self.view_h)

    def layout(self):
        p = self.p
        font = p.font(int(24 * p.ui))
        width = int(p.W * 0.66)
        self.rows = []
        y = 0
        for e in self.entries:
            name = e.get("speaker", "")
            lines = wrap_text(e.get("text", ""), font, width)
            self.rows.append((y, name, e.get("color") or "", lines, e.get("choice")))
            y += (font.get_linesize() * (len(lines) + (1 if name else 0))) + int(16 * p.ui)
        self.content_h = y
        self.view_h = int(p.H * 0.68)

    def handle(self, event, mouse):
        if event.type == pygame.MOUSEWHEEL:
            self.scroll -= event.y * 40
        elif event.type == pygame.KEYDOWN and event.key in (pygame.K_UP, pygame.K_DOWN, pygame.K_PAGEUP,
                                                             pygame.K_PAGEDOWN):
            step = {pygame.K_UP: -40, pygame.K_DOWN: 40, pygame.K_PAGEUP: -400, pygame.K_PAGEDOWN: 400}
            self.scroll += step[event.key]
        elif event.type == pygame.KEYDOWN and event.key == pygame.K_h:
            self.close()
            return
        else:
            super().handle(event, mouse)
        self.scroll = max(0, min(self.scroll, max(0, self.content_h - self.view_h)))

    def draw(self, surf):
        p = self.p
        self.dim(surf, 225)
        self.title(surf, "History", int(p.H * 0.08))
        font = p.font(int(24 * p.ui))
        nfont = p.font(int(24 * p.ui), bold=True)
        x = int(p.W * 0.17)
        top = int(p.H * 0.16)
        clip = surf.get_clip()
        surf.set_clip(pygame.Rect(0, top, p.W, self.view_h))
        if not self.entries:
            text_shadow(surf, font, "Nothing has been said yet.", (200, 200, 210), (p.W // 2, top + 40), center=True)
        for y, name, color, lines, is_choice in self.rows:
            yy = top + y - self.scroll
            if yy > top + self.view_h or yy + 200 < top:
                continue
            if name:
                surf.blit(nfont.render(name, True, hex_color(color, (255, 255, 255))[:3]), (x, yy))
                yy += font.get_linesize()
            for line in lines:
                surf.blit(font.render(line, True, p.accent if is_choice else (235, 235, 240)), (x, yy))
                yy += font.get_linesize()
        surf.set_clip(clip)
        super().draw(surf)


class SettingsScreen(Screen):
    def __init__(self, player):
        super().__init__(player)
        p = player
        w, h = int(p.W * 0.4), int(10 * p.ui)
        x = (p.W - w) // 2
        y0, gap = int(p.H * 0.27), int(p.H * 0.12)
        pr = p.prefs

        def setter(key):
            def fn(v):
                pr[key] = v
                p.apply_volume()
            return fn

        self.buttons = [
            Slider((x, y0, w, h), "Text speed (characters/sec, 0 = instant)", 0, 150, pr["text_speed"],
                   setter("text_speed")),
            Slider((x, y0 + gap, w, h), "Auto mode delay (seconds)", 0.3, 5, pr["auto_delay"],
                   setter("auto_delay"), "{:.1f}"),
            Slider((x, y0 + gap * 2, w, h), "Music volume", 0, 100, pr["music_volume"], setter("music_volume")),
            Slider((x, y0 + gap * 3, w, h), "Sound volume", 0, 100, pr["sound_volume"], setter("sound_volume")),
        ]
        bw, bh = int(260 * p.ui), int(48 * p.ui)
        self.fs_button = Button(((p.W - bw) // 2, y0 + gap * 4 - int(20 * p.ui), bw, bh), "", p.toggle_fullscreen)
        self.buttons.append(self.fs_button)
        self.buttons.append(Button((int(p.W * 0.82), int(p.H * 0.88), int(150 * p.ui), bh), "Back", self.close))

    def close(self):
        self.p.save_prefs()
        super().close()

    def draw(self, surf):
        self.dim(surf, 225)
        self.title(surf, "Settings")
        self.fs_button.text = "Windowed" if self.p.fullscreen else "Fullscreen"
        super().draw(surf)


# --------------------------------------------------------------------------
# The application
# --------------------------------------------------------------------------

class Player:
    def __init__(self, story: Story, start_scene: str | None = None, fullscreen: bool | None = None,
                 window_size: tuple[int, int] | None = None, headless: bool = False):
        self.story = story
        self.W, self.H = story.resolution
        self.ui = self.H / 720
        self.headless = headless
        self.running = True
        self.stack: list[Screen] = []
        self.game: GameView | None = None
        self.toasts: list[tuple[str, float]] = []
        self.clock_time = 0.0
        self.current_music = None
        self.start_scene = start_scene

        self.save_dir = self._find_save_dir()
        self.prefs = {"text_speed": story.settings.get("text_speed", 45),
                      "auto_delay": story.settings.get("auto_delay", 1.5),
                      "music_volume": 70, "sound_volume": 80, "fullscreen": False, "save_page": 0}
        self.prefs.update(self._read_json("settings.json") or {})
        self.persistent = self._read_json("persistent.json") or {"endings": []}

        pygame.init()
        try:
            pygame.mixer.init()
        except pygame.error as exc:
            log.warning("Audio disabled: %s", exc)
        pygame.display.set_caption(story.title)
        self.fullscreen = self.prefs.get("fullscreen", False) if fullscreen is None else fullscreen
        self.window_size = window_size or self._default_window_size()
        self._make_window()

        self.canvas = pygame.Surface((self.W, self.H)).convert()
        self.scene_surface = pygame.Surface((self.W, self.H)).convert()
        self.assets = AssetManager(story, (self.W, self.H))
        self.accent = hex_color(story.settings.get("accent_color"), (200, 155, 255))[:3]
        self.apply_volume()
        self._ui_click = None

        if start_scene:
            self.new_game(start_scene)
        else:
            self.stack = [TitleScreen(self)]

    # ----- setup ---------------------------------------------------------
    def _find_save_dir(self) -> str:
        candidates = []
        if self.story.path:
            candidates.append(os.path.join(self.story.path, "saves"))
        safe = "".join(ch for ch in self.story.title if ch.isalnum() or ch in " _-").strip() or "story"
        candidates.append(os.path.join(os.path.expanduser("~"), ".opennovella", "saves", safe))
        for c in candidates:
            try:
                os.makedirs(c, exist_ok=True)
                test = os.path.join(c, ".write_test")
                with open(test, "w") as fh:
                    fh.write("ok")
                os.remove(test)
                return c
            except OSError:
                continue
        return candidates[-1]

    def _default_window_size(self):
        try:
            dw, dh = pygame.display.get_desktop_sizes()[0]
        except (AttributeError, IndexError, pygame.error):
            dw, dh = 1920, 1080
        k = min(1.0, dw * 0.9 / self.W, dh * 0.85 / self.H)
        return int(self.W * k), int(self.H * k)

    def _make_window(self):
        if self.fullscreen:
            self.window = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        else:
            self.window = pygame.display.set_mode(self.window_size, pygame.RESIZABLE)

    def toggle_fullscreen(self):
        self.fullscreen = not self.fullscreen
        self.prefs["fullscreen"] = self.fullscreen
        self._make_window()

    # ----- fonts ---------------------------------------------------------
    def font(self, size, bold=False):
        return self.assets.font(self.story.settings.get("font", ""), max(8, int(size)), bold)

    @property
    def text_font(self):
        return self.font(self.story.settings.get("font_size", 28) * self.ui)

    @property
    def name_font(self):
        return self.font(self.story.settings.get("name_font_size", 30) * self.ui, bold=True)

    @property
    def text_speed(self):
        return float(self.prefs.get("text_speed", 45))

    # ----- screens -------------------------------------------------------
    def push(self, screen: Screen):
        self.stack.append(screen)

    def pop(self, screen: Screen | None = None):
        if screen is None and self.stack:
            self.stack.pop()
        elif screen in self.stack:
            self.stack.remove(screen)

    def new_game(self, scene: str | None = None):
        engine = Engine(self.story)
        try:
            engine.start(scene)
        except EngineError as exc:
            self.toast(str(exc))
            return
        self.stack = []
        self.game = GameView(self, engine)
        self.game.advance()

    def continue_game(self):
        slot = self.latest_save()
        if slot:
            self.load_slot(slot)

    def return_to_title(self):
        self.game = None
        self.stack = [TitleScreen(self)]

    def quit(self):
        self.running = False

    def toast(self, text):
        self.toasts.append((text, self.clock_time + 2.0))

    # ----- persistence ---------------------------------------------------
    def _read_json(self, name):
        try:
            with open(os.path.join(self.save_dir, name), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _write_json(self, name, data):
        try:
            path = os.path.join(self.save_dir, name)
            with open(path + ".tmp", "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1)
            os.replace(path + ".tmp", path)
            return True
        except OSError as exc:
            log.error("Could not write %s: %s", name, exc)
            return False

    def save_prefs(self):
        self._write_json("settings.json", self.prefs)

    def record_ending(self, name):
        endings = self.persistent.setdefault("endings", [])
        if name and name not in endings:
            endings.append(name)
            self._write_json("persistent.json", self.persistent)

    def slot_path(self, slot, ext=".json"):
        return os.path.join(self.save_dir, f"slot_{slot}{ext}")

    def slot_info(self, slot):
        return self._read_json(f"slot_{slot}.json")

    def latest_save(self):
        best, best_t = None, -1
        try:
            names = os.listdir(self.save_dir)
        except OSError:
            return None
        for name in names:
            if name.startswith("slot_") and name.endswith(".json"):
                info = self._read_json(name)
                if info and info.get("time", 0) > best_t:
                    best, best_t = name[5:-5], info.get("time", 0)
        return best

    def save_slot(self, slot):
        if not self.game or self.game.mode in ("ending", "error"):
            self.toast("Nothing to save right now")
            return
        snap = self.game.engine.snapshot()
        preview = ""
        if self.game.say:
            preview = (f"{self.game.say['name']}: " if self.game.say["name"] else "") + self.game.say["text"]
        elif self.game.mode == "choice":
            preview = self.game.choice_prompt or "Making a choice..."
        data = {"story": self.story.title, "time": time.time(), "scene": snap["scene"],
                "preview": " ".join(preview.split()), "state": snap, "version": __version__}
        if self._write_json(f"slot_{slot}.json", data):
            try:
                thumb = pygame.transform.smoothscale(self.scene_surface, (self.W // 4, self.H // 4))
                pygame.image.save(thumb, self.slot_path(slot, ".png"))
            except pygame.error:
                pass
            self.toast("Quick saved" if slot == "quick" else f"Saved to slot {slot}")
        else:
            self.toast("Saving failed!")

    def load_slot(self, slot):
        info = self.slot_info(slot)
        if not info:
            self.toast("That save is empty")
            return
        engine = Engine(self.story)
        try:
            engine.restore(info["state"])
        except (EngineError, KeyError, TypeError, ValueError) as exc:
            self.toast(f"Could not load: {exc}")
            return
        self.stack = []
        self.game = GameView(self, engine)
        self.game.advance()
        self.toast("Loaded")

    # ----- audio ---------------------------------------------------------
    def apply_volume(self):
        if pygame.mixer.get_init():
            pygame.mixer.music.set_volume(self.prefs["music_volume"] / 100)

    def play_music(self, music, fade=0.0):
        if not pygame.mixer.get_init():
            return
        fade_ms = int(max(0, fade) * 1000)
        if not music or not music.get("file"):
            if self.current_music:
                pygame.mixer.music.fadeout(fade_ms) if fade_ms else pygame.mixer.music.stop()
            self.current_music = None
            return
        if self.current_music == music.get("file"):
            return
        try:
            pygame.mixer.music.load(self.story.resolve(music["file"]))
            pygame.mixer.music.play(-1 if music.get("loop", True) else 0, fade_ms=fade_ms)
            self.current_music = music["file"]
            self.apply_volume()
        except pygame.error as exc:
            log.warning("Could not play music %s: %s", music.get("file"), exc)

    def play_sound(self, rel):
        snd = self.assets.sound(rel)
        if snd:
            snd.set_volume(self.prefs["sound_volume"] / 100)
            snd.play()

    def play_ui_sound(self):
        pass  # hook for a future click sound setting

    # ----- main loop -----------------------------------------------------
    def to_canvas(self, pos):
        ww, wh = self.window.get_size()
        k = min(ww / self.W, wh / self.H)
        ox, oy = (ww - self.W * k) / 2, (wh - self.H * k) / 2
        return int((pos[0] - ox) / k), int((pos[1] - oy) / k)

    def process(self, event):
        if event.type == pygame.QUIT:
            self.quit()
            return
        if event.type == pygame.VIDEORESIZE and not self.fullscreen:
            self.window_size = (max(320, event.w), max(180, event.h))
            return
        if event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F11 or (event.key == pygame.K_RETURN and event.mod & pygame.KMOD_ALT):
                self.toggle_fullscreen()
                return
        mouse = self.to_canvas(pygame.mouse.get_pos()) if not hasattr(event, "pos") else self.to_canvas(event.pos)
        if self.stack:
            self.stack[-1].handle(event, mouse)
        elif self.game:
            self.game.handle_input(event, mouse)

    def tick(self, dt, events=()):
        self.clock_time += dt
        for event in events:
            self.process(event)
            if not self.running:
                return
        if self.game and not self.stack:  # menus pause the game
            self.game.update(dt)
        for s in list(self.stack):
            s.update(dt)
        self.draw()

    def draw(self):
        c = self.canvas
        base_opaque = any(s.opaque for s in self.stack)
        if self.game and not base_opaque:
            self.game.draw(c)
        elif not self.stack:
            c.fill((0, 0, 0))
        start = max([i for i, s in enumerate(self.stack) if s.opaque] or [0])
        for s in self.stack[start:]:
            s.draw(c)
        self.toasts = [(t, until) for t, until in self.toasts if until > self.clock_time]
        y = int(16 * self.ui)
        for text, until in self.toasts:
            f = self.font(int(22 * self.ui))
            img = f.render(text, True, (255, 255, 255))
            r = pygame.Rect(0, y, img.get_width() + 28, img.get_height() + 14)
            r.right = self.W - int(16 * self.ui)
            draw_panel(c, r, (20, 20, 30), 220, radius=10)
            c.blit(img, (r.x + 14, r.y + 7))
            y += r.height + 8
        if self.headless:
            return
        ww, wh = self.window.get_size()
        if (ww, wh) == (self.W, self.H):
            self.window.blit(c, (0, 0))
        else:
            k = min(ww / self.W, wh / self.H)
            size = (max(1, int(self.W * k)), max(1, int(self.H * k)))
            self.window.fill((0, 0, 0))
            self.window.blit(pygame.transform.smoothscale(c, size), ((ww - size[0]) // 2, (wh - size[1]) // 2))
        pygame.display.flip()

    def run(self):
        clock = pygame.time.Clock()
        while self.running:
            dt = min(clock.tick(60) / 1000.0, 0.1)
            self.tick(dt, pygame.event.get())
        self.save_prefs()
        pygame.quit()


def write_crash_log(story_path: str | None, exc_text: str) -> str:
    folder = os.path.join(story_path, "saves") if story_path else os.getcwd()
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "crash.log")
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"OpenNovella {__version__} crash report\n")
            fh.write(f"Python {sys.version}\npygame {pygame.version.ver}\n\n{exc_text}\n")
        return path
    except OSError:
        return ""


def play(path: str, scene: str | None = None, fullscreen: bool | None = None) -> int:
    """Open a window and play the story at ``path`` (project folder or story.json)."""
    from .story import StoryError, load_story
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        story = load_story(path)
    except StoryError as exc:
        print(f"Could not open the story: {exc}", file=sys.stderr)
        return 1
    try:
        Player(story, start_scene=scene, fullscreen=fullscreen).run()
    except Exception:
        text = traceback.format_exc()
        log_path = write_crash_log(story.path, text)
        print(text, file=sys.stderr)
        print(f"\nOpenNovella crashed. A crash log was written to: {log_path or '(could not write log)'}\n"
              "Please report this using BUG_REPORT.md so it can be fixed.", file=sys.stderr)
        pygame.quit()
        return 2
    return 0
