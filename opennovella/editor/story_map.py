"""A visual map of how scenes connect - the "flowchart" of branching paths."""

from __future__ import annotations

import tkinter as tk
from collections import deque
from tkinter import ttk

from .widgets import HELP_FG

NODE_W, NODE_H = 170, 56
COL_GAP, ROW_GAP = 160, 34


def layout(story) -> dict[str, tuple[int, int]]:
    """Place scenes in columns by distance from the start scene."""
    depth: dict[str, int] = {}
    if story.start_scene in story.scenes:
        depth[story.start_scene] = 0
        q = deque([story.start_scene])
        while q:
            s = q.popleft()
            for target, _l, _i in story.links(s):
                if target in story.scenes and target not in depth:
                    depth[target] = depth[s] + 1
                    q.append(target)
    last = max(depth.values(), default=-1) + 1
    for s in story.scenes:  # unreachable scenes go in a final column
        depth.setdefault(s, last)
    columns: dict[int, list[str]] = {}
    for s in story.scenes:  # keep the scene list order inside each column
        columns.setdefault(depth[s], []).append(s)
    pos = {}
    for col, names in columns.items():
        for row, name in enumerate(names):
            pos[name] = (40 + col * (NODE_W + COL_GAP), 40 + row * (NODE_H + ROW_GAP))
    return pos


class StoryMapWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Story Map")
        self.geometry("1200x700")
        bar = ttk.Frame(self, padding=6)
        bar.pack(fill="x")
        ttk.Button(bar, text="Refresh", command=self.refresh).pack(side="left")
        ttk.Button(bar, text="Tidy layout", command=lambda: self.refresh(relayout=True)).pack(side="left", padx=4)
        ttk.Label(bar, foreground=HELP_FG,
                  text="Double-click a scene to edit it. Drag boxes to rearrange.   "
                       "Green = start   Red = has an ending   Grey = never reached").pack(side="left", padx=10)
        frame = ttk.Frame(self)
        frame.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(frame, background="#faf9fd", highlightthickness=0)
        xs = ttk.Scrollbar(frame, orient="horizontal", command=self.canvas.xview)
        ys = ttk.Scrollbar(frame, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=xs.set, yscrollcommand=ys.set)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        ys.grid(row=0, column=1, sticky="ns")
        xs.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.positions: dict[str, tuple[int, int]] = {}
        self.drag = None
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", lambda e: setattr(self, "drag", None))
        self.canvas.bind("<Double-1>", self.on_double)
        self.canvas.bind("<MouseWheel>", lambda e: self.canvas.yview_scroll(-1 * (e.delta // 120), "units"))
        self.canvas.bind("<Button-4>", lambda e: self.canvas.yview_scroll(-1, "units"))
        self.canvas.bind("<Button-5>", lambda e: self.canvas.yview_scroll(1, "units"))
        self.refresh(relayout=True)

    def refresh(self, relayout=False):
        story = self.app.story
        auto = layout(story)
        if relayout:
            self.positions = auto
        else:  # keep dragged positions, place new scenes automatically
            self.positions = {s: self.positions.get(s, auto[s]) for s in story.scenes}
        self.draw()

    def draw(self):
        c, story = self.canvas, self.app.story
        c.delete("all")
        reachable = story.reachable_scenes()
        # edges first so boxes sit on top
        for scene in story.scenes:
            sx, sy = self.positions[scene]
            targets = {}
            for target, label, _i in story.links(scene):
                if target in story.scenes:
                    targets.setdefault(target, []).append(label)
            for target, labels in targets.items():
                tx, ty = self.positions[target]
                x1, y1 = sx + NODE_W, sy + NODE_H / 2
                x2, y2 = tx, ty + NODE_H / 2
                color = "#7a5bd6" if any(l not in ("jump", "else") and not l.startswith("if ") for l in labels) \
                    else "#5c6b80"
                text = " / ".join(sorted(set(labels)))
                if len(text) > 24:
                    text = text[:23] + "…"
                if x2 > x1:
                    mx = (x1 + x2) / 2
                    c.create_line(x1, y1, mx, y1, mx, y2, x2, y2, smooth=True, arrow="last", width=2, fill=color)
                    # label just before the arrow head: every target has its own row, so no overlaps
                    c.create_text(x2 - 6, y2 - 9, text=text, fill=color, anchor="e", font=("TkDefaultFont", 8))
                else:  # going back (a loop) - curve underneath
                    low = max(sy, ty) + NODE_H + 24
                    c.create_line(x1, y1, x1 + 30, low, x2 - 30, low, x2, y2, smooth=True, arrow="last",
                                  width=2, fill=color, dash=(4, 3))
                    c.create_text((x1 + x2) / 2, low - 8, text=text, fill=color, font=("TkDefaultFont", 8))
        for scene in story.scenes:
            x, y = self.positions[scene]
            cmds = story.commands(scene)
            ends = any(cmd.get("type") == "end" for cmd in cmds)
            if scene == story.start_scene:
                outline, fill = "#2e7d32", "#e8f5e9"
            elif scene not in reachable:
                outline, fill = "#9e9e9e", "#eeeeee"
            elif ends:
                outline, fill = "#c62828", "#fdecea"
            else:
                outline, fill = "#7a5bd6", "#ffffff"
            tag = f"node:{scene}"
            c.create_rectangle(x, y, x + NODE_W, y + NODE_H, fill=fill, outline=outline, width=2, tags=(tag, "node"))
            c.create_text(x + NODE_W / 2, y + 20, text=scene if len(scene) < 22 else scene[:21] + "…",
                          font=("TkDefaultFont", 10, "bold"), tags=(tag, "node"))
            sub = f"{len(cmds)} commands" + ("  • START" if scene == story.start_scene else "") + \
                  ("  • END" if ends else "")
            c.create_text(x + NODE_W / 2, y + 40, text=sub, fill="#666", font=("TkDefaultFont", 8),
                          tags=(tag, "node"))
        bbox = c.bbox("all") or (0, 0, 100, 100)
        c.configure(scrollregion=(0, 0, bbox[2] + 80, bbox[3] + 80))

    def scene_at(self, event):
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        for item in reversed(self.canvas.find_overlapping(x, y, x, y)):
            for tag in self.canvas.gettags(item):
                if tag.startswith("node:"):
                    return tag[5:]
        return None

    def on_press(self, event):
        scene = self.scene_at(event)
        if scene:
            self.drag = (scene, self.canvas.canvasx(event.x), self.canvas.canvasy(event.y))

    def on_drag(self, event):
        if not self.drag:
            return
        scene, lx, ly = self.drag
        x, y = self.canvas.canvasx(event.x), self.canvas.canvasy(event.y)
        px, py = self.positions[scene]
        self.positions[scene] = (px + x - lx, py + y - ly)
        self.drag = (scene, x, y)
        self.draw()

    def on_double(self, event):
        scene = self.scene_at(event)
        if scene:
            self.app.select_scene(scene)
            self.app.root.lift()
