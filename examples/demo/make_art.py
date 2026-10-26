"""Generates simple artwork and sounds for the demo story.

The demo plays fine without this (OpenNovella draws placeholders for missing
art), but running it shows off images, animated frame folders, sprite sheets
and sound effects:

    python examples/demo/make_art.py

Everything is drawn with code, so no image files need to live in git.
"""

import math
import os
import random
import struct
import wave

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
import pygame  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
IMG = os.path.join(HERE, "images")
AUD = os.path.join(HERE, "audio")
W, H = 1280, 720


def gradient(top, bottom, size=(W, H)):
    surf = pygame.Surface(size)
    for y in range(size[1]):
        k = y / size[1]
        pygame.draw.line(surf, [int(top[i] + (bottom[i] - top[i]) * k) for i in range(3)], (0, y), (size[0], y))
    return surf


def hills(surf, color, base, amp, freq, seed):
    rnd = random.Random(seed)
    phase = rnd.random() * 6
    pts = [(0, H)]
    for x in range(0, W + 20, 20):
        pts.append((x, base + math.sin(x * freq + phase) * amp + math.sin(x * freq * 2.7) * amp * 0.3))
    pts.append((W, H))
    pygame.draw.polygon(surf, color, pts)


def stars(surf, n, seed):
    rnd = random.Random(seed)
    for _ in range(n):
        x, y = rnd.randrange(W), rnd.randrange(int(H * 0.6))
        c = rnd.randrange(150, 255)
        surf.set_at((x, y), (c, c, c))
        if rnd.random() < 0.1:
            pygame.draw.circle(surf, (c, c, c), (x, y), 2)


def glow(surf, color, pos, radius):
    layer = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
    for r in range(radius, 0, -3):
        a = int(90 * (1 - r / radius) ** 2)
        pygame.draw.circle(layer, (*color, a), (radius, radius), r)
    surf.blit(layer, (pos[0] - radius, pos[1] - radius))


def village():
    s = gradient((40, 50, 110), (240, 150, 120))
    stars(s, 80, 1)
    hills(s, (60, 60, 105), 470, 40, 0.004, 2)
    hills(s, (35, 38, 70), 540, 25, 0.007, 3)
    rnd = random.Random(4)
    for i in range(9):
        x = 80 + i * 135 + rnd.randrange(-20, 20)
        w, h = rnd.randrange(80, 120), rnd.randrange(70, 110)
        y = 600 - h
        pygame.draw.rect(s, (28, 26, 46), (x, y, w, h + 120))
        pygame.draw.polygon(s, (22, 20, 38), [(x - 10, y), (x + w // 2, y - 50), (x + w + 10, y)])
        for wx in range(x + 14, x + w - 20, 34):
            glow(s, (255, 200, 120), (wx + 9, y + 30), 26)
            pygame.draw.rect(s, (255, 214, 140), (wx, y + 20, 18, 22))
    return s


def festival():
    s = gradient((14, 12, 40), (90, 40, 90))
    stars(s, 220, 5)
    hills(s, (30, 20, 50), 560, 20, 0.005, 6)
    rnd = random.Random(7)
    for row, y0 in enumerate((180, 300)):
        pts = [(x, y0 + math.sin(x / 160 + row) * 40 + (x / W) * 60) for x in range(-20, W + 40, 10)]
        pygame.draw.lines(s, (70, 50, 70), False, pts, 2)
        for x in range(40 + row * 60, W, 120):
            y = y0 + math.sin(x / 160 + row) * 40 + (x / W) * 60
            color = rnd.choice([(255, 160, 80), (255, 110, 110), (255, 210, 110), (240, 140, 220)])
            glow(s, color, (x, int(y) + 24), 60)
            pygame.draw.ellipse(s, color, (x - 16, y + 6, 32, 40))
    for _ in range(25):  # floating sky lanterns
        x, y = rnd.randrange(W), rnd.randrange(30, 260)
        glow(s, (255, 180, 90), (x, y), 30)
        pygame.draw.rect(s, (255, 190, 110), (x - 5, y - 7, 10, 14), border_radius=3)
    return s


def hill_rain():
    s = gradient((20, 26, 46), (60, 70, 100))
    hills(s, (40, 46, 70), 420, 30, 0.003, 8)
    hills(s, (24, 28, 46), 520, 50, 0.004, 9)
    for x in range(100, W, 220):  # distant village lights
        glow(s, (255, 200, 120), (x, 450 + (x % 3) * 12), 14)
    return s


def character(hair, outfit, skin, expression, long_hair=True, beard=False):
    w, h = 380, 640
    s = pygame.Surface((w, h), pygame.SRCALPHA)
    cx = w // 2
    if long_hair:
        pygame.draw.ellipse(s, hair, (cx - 105, 70, 210, 300))
    pygame.draw.polygon(s, outfit, [(cx - 70, 300), (cx + 70, 300), (cx + 150, h), (cx - 150, h)])
    pygame.draw.rect(s, skin, (cx - 22, 250, 44, 60))
    pygame.draw.ellipse(s, skin, (cx - 85, 90, 170, 200))
    pygame.draw.ellipse(s, hair, (cx - 95, 70, 190, 100))
    if not long_hair:
        pygame.draw.rect(s, hair, (cx - 95, 110, 30, 70), border_radius=10)
        pygame.draw.rect(s, hair, (cx + 65, 110, 30, 70), border_radius=10)
    eye_y = 190
    for ex in (cx - 35, cx + 35):
        if expression == "happy":
            pygame.draw.arc(s, (40, 30, 40), (ex - 14, eye_y - 8, 28, 22), 0.2, math.pi - 0.2, 4)
        else:
            pygame.draw.ellipse(s, (40, 30, 40), (ex - 9, eye_y - 12, 18, 24))
            pygame.draw.circle(s, (255, 255, 255), (ex - 3, eye_y - 5), 4)
        if expression == "sad":
            pygame.draw.line(s, (40, 30, 40), (ex - 16, eye_y - 26 + (8 if ex < cx else 0)),
                             (ex + 16, eye_y - 26 + (0 if ex < cx else 8)), 4)
    if beard:
        pygame.draw.ellipse(s, (220, 220, 225), (cx - 70, 215, 140, 110))
    mouth = pygame.Rect(cx - 25, 228, 50, 26)
    if expression == "happy":
        pygame.draw.arc(s, (150, 50, 70), mouth, math.pi + 0.3, 2 * math.pi - 0.3, 5)
    elif expression == "sad":
        pygame.draw.arc(s, (150, 50, 70), mouth.move(0, 14), 0.4, math.pi - 0.4, 4)
    else:
        pygame.draw.line(s, (150, 50, 70), (cx - 14, 242), (cx + 14, 242), 4)
    pygame.draw.circle(s, (255, 170, 170, 120), (cx - 52, 222), 14)
    pygame.draw.circle(s, (255, 170, 170, 120), (cx + 52, 222), 14)
    return s


def rain_frames(folder, n=8):
    os.makedirs(folder, exist_ok=True)
    rnd = random.Random(11)
    drops = [(rnd.randrange(W), rnd.randrange(H), rnd.randrange(18, 34)) for _ in range(260)]
    for f in range(n):
        s = pygame.Surface((W, H), pygame.SRCALPHA)
        for x, y, ln in drops:
            yy = (y + f * H // n) % H
            xx = (x - f * 40 // n) % W
            pygame.draw.line(s, (190, 210, 255, 120), (xx, yy), (xx - 4, yy + ln), 2)
        pygame.image.save(s, os.path.join(folder, f"{f + 1:03d}.png"))
    with open(os.path.join(folder, "fps.txt"), "w") as fh:
        fh.write("16\n")


def sparkle_strip(path, n=8, size=160):
    sheet = pygame.Surface((size * n, size), pygame.SRCALPHA)
    rnd = random.Random(3)
    points = [(rnd.uniform(0, math.tau), rnd.uniform(0.3, 1.0)) for _ in range(14)]
    for f in range(n):
        k = (f + 1) / n
        ox = f * size + size // 2
        for ang, dist in points:
            r = dist * k * size * 0.45
            x, y = ox + math.cos(ang) * r, size / 2 + math.sin(ang) * r
            a = int(255 * (1 - k * 0.8))
            ln = 10 * (1 - k) + 3
            pygame.draw.line(sheet, (255, 240, 170, a), (x - ln, y), (x + ln, y), 2)
            pygame.draw.line(sheet, (255, 240, 170, a), (x, y - ln), (x, y + ln), 2)
    pygame.image.save(sheet, path)


def thunder(path, seconds=2.2, rate=22050):
    rnd = random.Random(1)
    value, frames = 0.0, bytearray()
    for i in range(int(seconds * rate)):
        t = i / rate
        value = value * 0.985 + rnd.uniform(-1, 1) * 0.15  # brown-ish noise
        env = min(1, t * 30) * math.exp(-t * 2.2) * (1 + 0.6 * math.sin(t * 9))
        frames += struct.pack("<h", int(max(-1, min(1, value * env * 2.2)) * 30000))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))


def main():
    pygame.display.init()
    pygame.display.set_mode((1, 1))
    os.makedirs(IMG, exist_ok=True)
    os.makedirs(AUD, exist_ok=True)
    pygame.image.save(village(), os.path.join(IMG, "bg_village.png"))
    pygame.image.save(festival(), os.path.join(IMG, "bg_festival.png"))
    pygame.image.save(hill_rain(), os.path.join(IMG, "bg_hill_rain.png"))
    for expr in ("default", "happy", "sad"):
        pygame.image.save(character((90, 50, 110), (230, 120, 160), (255, 224, 200), expr),
                          os.path.join(IMG, f"mira_{expr}.png"))
    pygame.image.save(character((200, 200, 205), (120, 90, 60), (235, 200, 170), "default",
                                long_hair=False, beard=True), os.path.join(IMG, "tomas_default.png"))
    rain_frames(os.path.join(IMG, "rain"))
    sparkle_strip(os.path.join(IMG, "sparkle_strip8.png"))
    thunder(os.path.join(AUD, "thunder.wav"))
    pygame.quit()
    print(f"Demo art written to {IMG} and {AUD}")


if __name__ == "__main__":
    main()
