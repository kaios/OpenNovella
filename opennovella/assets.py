"""Loading images, animations, fonts and sounds for the pygame player.

Supported images:

* Still images: PNG, JPG, BMP, WebP, ... (anything pygame can read)
* Animated GIF / WebP / APNG (needs Pillow, which is installed with OpenNovella)
* A folder of frames, e.g. ``images/rain/0001.png, 0002.png ...`` - played in
  name order. Put a ``fps.txt`` containing a number in the folder to set the
  speed, otherwise the command's FPS (default 12) is used.
* A sprite sheet named like ``explosion_strip8.png`` (8 frames side by side).

Missing files never crash the game; a labelled placeholder is drawn instead
so you can write your whole story before any art exists.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re

import pygame

log = logging.getLogger("opennovella")

IMAGE_EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp", ".tga", ".tif", ".tiff")
_STRIP_RE = re.compile(r"_strip(\d+)\.\w+$", re.I)

try:
    from PIL import Image as PILImage, ImageSequence
except ImportError:  # pragma: no cover - Pillow is optional at runtime
    PILImage = None


def hex_color(value: str, default=(0, 0, 0)) -> tuple:
    """'#rrggbb' or '#rrggbbaa' -> tuple. Bad values give ``default``."""
    if isinstance(value, (tuple, list)):
        return tuple(value)
    try:
        v = (value or "").strip().lstrip("#")
        if len(v) == 3:
            v = "".join(ch * 2 for ch in v)
        if len(v) not in (6, 8):
            return default
        return tuple(int(v[i:i + 2], 16) for i in range(0, len(v), 2))
    except (ValueError, AttributeError):
        return default


class Animation:
    """A still image or a sequence of frames with per-frame durations."""

    def __init__(self, frames: list[pygame.Surface], durations: list[float] | None = None):
        self.frames = frames or [pygame.Surface((1, 1), pygame.SRCALPHA)]
        if durations is None or len(durations) != len(self.frames):
            durations = [1 / 12] * len(self.frames)
        self.durations = [max(d, 0.01) for d in durations]
        self.total = sum(self.durations)
        self.placeholder = False

    @property
    def animated(self) -> bool:
        return len(self.frames) > 1

    def size(self) -> tuple[int, int]:
        return self.frames[0].get_size()

    def frame(self, t: float, loop: bool = True) -> pygame.Surface:
        if not self.animated:
            return self.frames[0]
        if loop:
            t %= self.total
        elif t >= self.total:
            return self.frames[-1]
        for surf, d in zip(self.frames, self.durations):
            if t < d:
                return surf
            t -= d
        return self.frames[-1]

    def scaled(self, size: tuple[int, int]) -> "Animation":
        size = (max(1, int(size[0])), max(1, int(size[1])))
        anim = Animation([pygame.transform.smoothscale(f, size) for f in self.frames],
                         self.durations)
        anim.placeholder = self.placeholder
        return anim


class AssetManager:
    def __init__(self, story, screen_size: tuple[int, int]):
        self.story = story
        self.screen_size = screen_size
        self._cache: dict[tuple, Animation] = {}
        self._fonts: dict[tuple, pygame.font.Font] = {}
        self._sounds: dict[str, object] = {}
        self.audio_ok = pygame.mixer.get_init() is not None

    # ----- images --------------------------------------------------------
    def image(self, rel: str, fps: float = 12, kind: str = "sprite", label: str = "",
              color: str = "") -> Animation:
        key = (rel, fps, kind, label, color)
        if key not in self._cache:
            anim = self._load(rel, fps) if rel else None
            if anim is None:
                anim = self._placeholder(kind, label or os.path.basename(rel) or "?", color)
            elif kind in ("background", "overlay_full"):
                anim = anim.scaled(self.screen_size)
            elif kind in ("sprite", "overlay"):
                w, h = anim.size()
                max_h = self.screen_size[1] * 0.92
                if h > max_h:  # big character art: fit to screen height
                    anim = anim.scaled((w * max_h / h, max_h))
            self._cache[key] = anim
        return self._cache[key]

    def _load(self, rel: str, fps: float) -> Animation | None:
        path = self.story.resolve(rel)
        try:
            if os.path.isdir(path):
                return self._load_folder(path, fps)
            if not os.path.isfile(path):
                log.warning("Image not found: %s", rel)
                return None
            m = _STRIP_RE.search(path)
            if m:
                return self._load_strip(path, int(m.group(1)), fps)
            if PILImage is not None and path.lower().endswith((".gif", ".webp", ".png")):
                anim = self._load_pil_animation(path)
                if anim is not None:
                    return anim
            return Animation([pygame.image.load(path).convert_alpha()])
        except Exception as exc:  # corrupt files etc. must not crash the game
            log.warning("Could not load image %s: %s", rel, exc)
            return None

    def _load_folder(self, path: str, fps: float) -> Animation | None:
        names = sorted(n for n in os.listdir(path) if n.lower().endswith(IMAGE_EXTS))
        if not names:
            log.warning("Animation folder has no images: %s", path)
            return None
        fps_file = os.path.join(path, "fps.txt")
        if os.path.isfile(fps_file):
            try:
                with open(fps_file, encoding="utf-8") as fh:
                    fps = float(fh.read().strip())
            except ValueError:
                pass
        fps = max(float(fps or 12), 0.1)
        frames = [pygame.image.load(os.path.join(path, n)).convert_alpha() for n in names]
        return Animation(frames, [1 / fps] * len(frames))

    def _load_strip(self, path: str, count: int, fps: float) -> Animation:
        sheet = pygame.image.load(path).convert_alpha()
        count = max(1, count)
        w = sheet.get_width() // count
        frames = [sheet.subsurface((i * w, 0, w, sheet.get_height())).copy() for i in range(count)]
        fps = max(float(fps or 12), 0.1)
        return Animation(frames, [1 / fps] * count)

    def _load_pil_animation(self, path: str) -> Animation | None:
        with PILImage.open(path) as img:
            if getattr(img, "n_frames", 1) <= 1:
                return None
            frames, durations = [], []
            for frame in ImageSequence.Iterator(img):
                rgba = frame.convert("RGBA")
                surf = pygame.image.frombytes(rgba.tobytes(), rgba.size, "RGBA") \
                    if hasattr(pygame.image, "frombytes") else \
                    pygame.image.fromstring(rgba.tobytes(), rgba.size, "RGBA")
                frames.append(surf.convert_alpha())
                durations.append((frame.info.get("duration") or 100) / 1000)
            return Animation(frames, durations)

    def _placeholder(self, kind: str, label: str, color: str) -> Animation:
        if kind.startswith("overlay"):  # a missing effect simply isn't drawn
            anim = Animation([pygame.Surface((1, 1), pygame.SRCALPHA)])
            anim.placeholder = True
            return anim
        sw, sh = self.screen_size
        seed = int(hashlib.md5(label.encode("utf-8")).hexdigest()[:6], 16)
        base = hex_color(color, None) if color else None
        if base is None:
            base = (60 + seed % 140, 60 + (seed >> 8) % 140, 60 + (seed >> 16) % 140)
        font = self.font("", 30)
        if kind == "background":
            surf = pygame.Surface((sw, sh))
            top = tuple(min(255, c + 30) for c in base[:3])
            bottom = tuple(max(0, c - 40) for c in base[:3])
            for y in range(sh):
                k = y / sh
                pygame.draw.line(surf, [int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)],
                                 (0, y), (sw, y))
            anim = Animation([surf])
        else:
            w, h = int(sh * 0.32), int(sh * 0.72)
            surf = pygame.Surface((w, h), pygame.SRCALPHA)
            body = (*base[:3], 230)
            pygame.draw.circle(surf, body, (w // 2, int(h * 0.17)), int(w * 0.26))
            pygame.draw.rect(surf, body, (int(w * 0.12), int(h * 0.36), int(w * 0.76), int(h * 0.64)),
                             border_radius=int(w * 0.2))
            text = font.render(label, True, (255, 255, 255))
            if text.get_width() > w - 10:
                text = pygame.transform.smoothscale(
                    text, (w - 10, max(1, int(text.get_height() * (w - 10) / text.get_width()))))
            surf.blit(text, ((w - text.get_width()) // 2, int(h * 0.62)))
            anim = Animation([surf])
        anim.placeholder = True
        return anim

    # ----- fonts ---------------------------------------------------------
    def font(self, rel: str, size: int, bold: bool = False) -> pygame.font.Font:
        key = (rel, size, bold)
        if key not in self._fonts:
            f = None
            if rel:
                try:
                    f = pygame.font.Font(self.story.resolve(rel), size)
                except (OSError, FileNotFoundError) as exc:
                    log.warning("Could not load font %s: %s", rel, exc)
            if f is None:
                try:
                    f = pygame.font.Font(None, int(size * 1.15))  # default font runs small
                except (OSError, FileNotFoundError):  # distro pygame without its bundled font
                    f = pygame.font.SysFont("dejavusans,freesans,arial,sans", size)
            f.set_bold(bold)
            self._fonts[key] = f
        return self._fonts[key]

    # ----- audio ---------------------------------------------------------
    def sound(self, rel: str):
        if not self.audio_ok or not rel:
            return None
        if rel not in self._sounds:
            try:
                self._sounds[rel] = pygame.mixer.Sound(self.story.resolve(rel))
            except (pygame.error, FileNotFoundError) as exc:
                log.warning("Could not load sound %s: %s", rel, exc)
                self._sounds[rel] = None
        return self._sounds[rel]
