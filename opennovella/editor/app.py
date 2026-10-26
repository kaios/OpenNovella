"""The OpenNovella editor main window."""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk

from .. import __version__
from ..bugreport import report_template
from ..story import (CATEGORIES, COMMAND_TYPES, STORY_FILENAME, Story, StoryError,
                     create_project, new_command, summarize)
from ..validate import ERROR, validate
from .dialogs import (CharactersDialog, CommandDialog, SettingsDialog, ValidationWindow,
                      VariablesDialog, show_about)
from .story_map import StoryMapWindow
from .widgets import HELP_FG, ToolTip, ask_new_scene, suggest_scene_name

CONFIG_PATH = os.path.join(os.path.expanduser("~"), ".opennovella", "editor.json")
PACKAGE_PARENT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEMO_PATH = os.path.join(PACKAGE_PARENT, "examples", "demo")
NARRATOR = "(narrator)"
MAX_UNDO = 100

CATEGORY_COLORS = {"Story": "#1f1b2e", "Visuals": "#1d5fa8", "Audio": "#2e7d32", "Timing": "#8a5a00"}

QUICK_START = """Welcome to OpenNovella!

1. SCENES (left) are the chapters of your story. The ★ scene is where the game starts.
2. COMMANDS (middle) run from top to bottom: dialogue, backgrounds, characters, music…
   • Type a line in the “Quick dialogue” bar at the bottom and press Enter - the fastest way to write.
   • Use “Add command” for everything else. Double-click a command to edit it.
3. BRANCHING: add a Choice. Each option can go to a different scene - pick “+ New scene…” to create
   one on the spot. Use variables + If/Else to remember decisions and change the story later.
4. CHARACTERS: open Characters to add people, their name colors and expression images.
   No art yet? Placeholders are drawn automatically so you can write first.
5. PLAY: press F5 to play from the start, or Shift+F5 to play the selected scene.
6. CHECK: press F7 to find broken links, missing images and other mistakes.
7. MAP: press F8 to see your branching paths as a flowchart.

Images: PNG/JPG/WebP. Animations: animated GIF/WebP, a folder of numbered frames,
or a sprite sheet named like  name_strip8.png .  Audio: OGG/MP3/WAV.
"""

SHORTCUTS = """Ctrl+N  New project          Ctrl+O  Open project        Ctrl+S  Save
Ctrl+Z  Undo                 Ctrl+Y  Redo
Enter   Edit command         Delete  Delete command(s)   Ctrl+D  Duplicate
Ctrl+C / Ctrl+V  Copy / paste commands
Alt+Up / Alt+Down  Move command up / down
F5  Play from start   Shift+F5  Play this scene   F7  Check story   F8  Story map
"""


def load_config() -> dict:
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return {}


def save_config(cfg: dict) -> None:
    try:
        os.makedirs(os.path.dirname(CONFIG_PATH), exist_ok=True)
        with open(CONFIG_PATH, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=1)
    except OSError:
        pass


class EditorApp:
    def __init__(self, root: tk.Tk, project: str | None = None):
        self.root = root
        self.story: Story | None = None
        self.scene: str | None = None
        self.dirty = False
        self.undo_stack: list = []
        self.redo_stack: list = []
        self.clipboard: list[dict] = []
        self.config = load_config()
        self.map_window: StoryMapWindow | None = None
        self.check_window: ValidationWindow | None = None
        self._loading_notes = False

        root.title("OpenNovella")
        root.geometry(self.config.get("geometry", "1280x780"))
        root.minsize(900, 560)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.setup_style()
        self.build_menu()
        self.build_toolbar()
        self.container = ttk.Frame(root)
        self.container.pack(fill="both", expand=True)
        self.status = ttk.Label(root, text="", padding=(8, 3), style="Status.TLabel")
        self.status.pack(fill="x", side="bottom")
        self.build_welcome()
        self.build_workspace()
        self.bind_keys()

        if project:
            self.open_project(project)
        else:
            self.show_welcome()

    # ------------------------------------------------------------------ UI
    def setup_style(self):
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        bg, accent = "#f5f3fa", "#7a5bd6"
        self.root.configure(background=bg)
        style.configure(".", background=bg)
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg)
        style.configure("TCheckbutton", background=bg)
        style.configure("Toolbar.TFrame", background="#ebe7f5")
        style.configure("Toolbar.TButton", padding=(8, 4))
        style.configure("Heading.TLabel", font=("TkDefaultFont", 11, "bold"))
        style.configure("Title.TLabel", font=("TkDefaultFont", 22, "bold"), foreground=accent)
        style.configure("Big.TButton", font=("TkDefaultFont", 12), padding=(18, 10))
        style.configure("Accent.TButton", foreground="white", background=accent)
        style.map("Accent.TButton", background=[("active", "#6446c4"), ("disabled", "#b9acd9")])
        style.configure("Status.TLabel", background="#ebe7f5", foreground="#444")
        style.configure("Treeview", rowheight=26)
        style.configure("Treeview.Heading", font=("TkDefaultFont", 9, "bold"))

    def build_menu(self):
        m = tk.Menu(self.root)
        self.root.config(menu=m)
        fm = tk.Menu(m, tearoff=False)
        fm.add_command(label="New Project…", accelerator="Ctrl+N", command=self.new_project)
        fm.add_command(label="Open Project…", accelerator="Ctrl+O", command=self.open_dialog)
        self.recent_menu = tk.Menu(fm, tearoff=False)
        fm.add_cascade(label="Open Recent", menu=self.recent_menu)
        fm.add_command(label="Save", accelerator="Ctrl+S", command=self.save)
        fm.add_separator()
        fm.add_command(label="Open Project Folder", command=self.open_folder)
        fm.add_command(label="Export Game…", command=self.export_game)
        fm.add_separator()
        fm.add_command(label="Exit", command=self.quit)
        m.add_cascade(label="File", menu=fm)

        em = tk.Menu(m, tearoff=False)
        em.add_command(label="Undo", accelerator="Ctrl+Z", command=self.undo)
        em.add_command(label="Redo", accelerator="Ctrl+Y", command=self.redo)
        em.add_separator()
        em.add_cascade(label="Add Command", menu=self.make_add_menu(em))
        em.add_command(label="Edit Command", accelerator="Enter", command=self.edit_selected)
        em.add_command(label="Duplicate", accelerator="Ctrl+D", command=self.duplicate)
        em.add_command(label="Copy", accelerator="Ctrl+C", command=self.copy_commands)
        em.add_command(label="Paste", accelerator="Ctrl+V", command=self.paste_commands)
        em.add_command(label="Delete", accelerator="Del", command=self.delete_commands)
        em.add_command(label="Move Up", accelerator="Alt+Up", command=lambda: self.move(-1))
        em.add_command(label="Move Down", accelerator="Alt+Down", command=lambda: self.move(1))
        m.add_cascade(label="Edit", menu=em)

        sm = tk.Menu(m, tearoff=False)
        sm.add_command(label="Add Scene…", command=self.add_scene)
        sm.add_command(label="Rename Scene…", command=self.rename_scene)
        sm.add_command(label="Duplicate Scene", command=self.duplicate_scene)
        sm.add_command(label="Delete Scene", command=self.delete_scene)
        sm.add_command(label="Set as Start Scene", command=self.set_start)
        sm.add_separator()
        sm.add_command(label="Characters…", command=self.edit_characters)
        sm.add_command(label="Variables…", command=self.edit_variables)
        sm.add_command(label="Project Settings…", command=self.edit_settings)
        m.add_cascade(label="Story", menu=sm)

        tm = tk.Menu(m, tearoff=False)
        tm.add_command(label="Play from Start", accelerator="F5", command=self.play)
        tm.add_command(label="Play This Scene", accelerator="Shift+F5", command=lambda: self.play(self.scene))
        tm.add_separator()
        tm.add_command(label="Check Story", accelerator="F7", command=self.check_story)
        tm.add_command(label="Story Map", accelerator="F8", command=self.story_map)
        m.add_cascade(label="Tools", menu=tm)

        hm = tk.Menu(m, tearoff=False)
        hm.add_command(label="Quick Start Guide", command=lambda: self.info_window("Quick Start", QUICK_START))
        hm.add_command(label="Keyboard Shortcuts", command=lambda: self.info_window("Shortcuts", SHORTCUTS))
        hm.add_command(label="Open README", command=self.open_readme)
        hm.add_separator()
        hm.add_command(label="Report a Bug…", command=self.bug_report)
        hm.add_command(label="About OpenNovella", command=lambda: show_about(self.root))
        m.add_cascade(label="Help", menu=hm)
        self.refresh_recent()

    def make_add_menu(self, parent):
        menu = tk.Menu(parent, tearoff=False)
        for cat in CATEGORIES:
            sub = tk.Menu(menu, tearoff=False)
            for t, spec in COMMAND_TYPES.items():
                if spec.category == cat:
                    sub.add_command(label=spec.label,
                                    command=lambda t=t: self.add_command(t))
            menu.add_cascade(label=cat, menu=sub)
        return menu

    def build_toolbar(self):
        bar = ttk.Frame(self.root, style="Toolbar.TFrame", padding=(6, 4))
        bar.pack(fill="x")
        self.toolbar_buttons = []

        def btn(text, cmd, tip, accent=False):
            b = ttk.Button(bar, text=text, command=cmd, style="Accent.TButton" if accent else "Toolbar.TButton")
            b.pack(side="left", padx=2)
            ToolTip(b, tip)
            self.toolbar_buttons.append(b)
            return b

        def sep():
            ttk.Separator(bar, orient="vertical").pack(side="left", fill="y", padx=6)

        btn("New", self.new_project, "Create a new visual novel project (Ctrl+N)")
        btn("Open", self.open_dialog, "Open an existing project (Ctrl+O)")
        btn("Save", self.save, "Save your story (Ctrl+S)")
        sep()
        btn("▶ Play", self.play, "Play the story from the title screen (F5)", accent=True)
        btn("▶ Play Scene", lambda: self.play(self.scene), "Play starting at the selected scene (Shift+F5)")
        sep()
        btn("Characters", self.edit_characters, "Add characters, name colors and expression images")
        btn("Variables", self.edit_variables, "Variables remember the player's choices")
        btn("Story Map", self.story_map, "See how your scenes branch and connect (F8)")
        btn("✔ Check Story", self.check_story, "Find broken links, missing files and other mistakes (F7)")
        btn("⚙ Settings", self.edit_settings, "Title, screen size, fonts, colors and title screen")

    def build_welcome(self):
        w = self.welcome = ttk.Frame(self.container, padding=40)
        ttk.Label(w, text="OpenNovella", style="Title.TLabel").pack(pady=(30, 4))
        ttk.Label(w, text="Create visual novels with branching paths - no programming needed.",
                  font=("TkDefaultFont", 12)).pack()
        ttk.Label(w, text="by Shawn Rapaz & Claude Code", foreground=HELP_FG).pack(pady=(2, 26))
        row = ttk.Frame(w)
        row.pack()
        ttk.Button(row, text="New Project", style="Big.TButton", command=self.new_project).pack(side="left", padx=8)
        ttk.Button(row, text="Open Project", style="Big.TButton", command=self.open_dialog).pack(side="left", padx=8)
        if os.path.isfile(os.path.join(DEMO_PATH, STORY_FILENAME)):
            ttk.Button(row, text="Open the Demo", style="Big.TButton",
                       command=self.open_demo).pack(side="left", padx=8)
        self.recent_frame = ttk.Frame(w)
        self.recent_frame.pack(pady=26)
        ttk.Label(w, text=QUICK_START, foreground="#4a4760", justify="left").pack(pady=(10, 0))

    def refresh_welcome_recent(self):
        for child in self.recent_frame.winfo_children():
            child.destroy()
        recent = [p for p in self.config.get("recent", []) if os.path.isfile(os.path.join(p, STORY_FILENAME))]
        if recent:
            ttk.Label(self.recent_frame, text="Recent projects", style="Heading.TLabel").pack(anchor="w")
            for p in recent[:6]:
                ttk.Button(self.recent_frame, text=p, command=lambda p=p: self.open_project(p)).pack(fill="x", pady=1)

    def build_workspace(self):
        ws = self.workspace = ttk.PanedWindow(self.container, orient="horizontal")

        # --- scenes ---------------------------------------------------------
        left = ttk.Frame(ws, padding=8)
        ttk.Label(left, text="Scenes", style="Heading.TLabel").pack(anchor="w")
        lb_frame = ttk.Frame(left)
        lb_frame.pack(fill="both", expand=True, pady=4)
        self.scene_list = tk.Listbox(lb_frame, exportselection=False, activestyle="none", font=("TkDefaultFont", 11),
                                     selectbackground="#7a5bd6", selectforeground="white", borderwidth=1,
                                     relief="solid", highlightthickness=0)
        sb = ttk.Scrollbar(lb_frame, orient="vertical", command=self.scene_list.yview)
        self.scene_list.configure(yscrollcommand=sb.set)
        self.scene_list.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.scene_list.bind("<<ListboxSelect>>", lambda e: self.on_scene_select())
        self.scene_list.bind("<Double-1>", lambda e: self.rename_scene())
        bar = ttk.Frame(left)
        bar.pack(fill="x")
        for n, (text, cmd, tip) in enumerate((
                ("+ Add", self.add_scene, "Add a new scene"),
                ("Rename", self.rename_scene, "Rename the selected scene (links are updated)"),
                ("Delete", self.delete_scene, "Delete the selected scene"),
                ("★ Set start", self.set_start, "Make this the first scene of the story"))):
            b = ttk.Button(bar, text=text, command=cmd)
            b.grid(row=n // 2, column=n % 2, sticky="ew", padx=1, pady=1)
            ToolTip(b, tip)
        bar.columnconfigure((0, 1), weight=1)
        ttk.Label(left, text="Scene notes (only you see these)", foreground=HELP_FG).pack(anchor="w", pady=(10, 2))
        self.notes = tk.Text(left, height=6, width=26, wrap="word", font=("TkDefaultFont", 10), relief="solid",
                             borderwidth=1)
        self.notes.pack(fill="x")
        self.notes.bind("<<Modified>>", self.on_notes_changed)
        self.links_label = ttk.Label(left, text="", foreground=HELP_FG, wraplength=230, justify="left")
        self.links_label.pack(anchor="w", pady=(8, 0))
        ws.add(left, weight=1)

        # --- commands -------------------------------------------------------
        mid = ttk.Frame(ws, padding=8)
        head = ttk.Frame(mid)
        head.pack(fill="x")
        self.scene_title = ttk.Label(head, text="", style="Heading.TLabel")
        self.scene_title.pack(side="left")
        tree_frame = ttk.Frame(mid)
        tree_frame.pack(fill="both", expand=True, pady=4)
        self.tree = ttk.Treeview(tree_frame, columns=("n", "type", "details"), show="headings", selectmode="extended")
        self.tree.heading("n", text="#")
        self.tree.heading("type", text="Command")
        self.tree.heading("details", text="Details")
        self.tree.column("n", width=40, stretch=False, anchor="e")
        self.tree.column("type", width=150, stretch=False)
        self.tree.column("details", width=520, stretch=True)
        tsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=tsb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        tsb.pack(side="right", fill="y")
        for cat, color in CATEGORY_COLORS.items():
            self.tree.tag_configure(cat, foreground=color)
        self.tree.tag_configure("note", foreground="#8a8799")
        self.tree.tag_configure("branch", background="#f1ecff")
        self.tree.tag_configure("problem", background="#fdecea")
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        self.tree.bind("<Return>", lambda e: self.edit_selected())
        self.tree.bind("<Delete>", lambda e: self.delete_commands())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.update_help())
        self.tree.bind("<Button-3>", self.tree_context_menu)

        cbar = ttk.Frame(mid)
        cbar.pack(fill="x")
        add_btn = ttk.Menubutton(cbar, text="+ Add command", style="Accent.TButton")
        add_btn["menu"] = self.make_add_menu(add_btn)
        add_btn.pack(side="left")
        quick = [("Say", "say"), ("Choice", "choice"), ("Background", "background"),
                 ("Show", "show"), ("Jump", "jump")]
        for text, t in quick:
            b = ttk.Button(cbar, text=text, command=lambda t=t: self.add_command(t))
            b.pack(side="left", padx=1)
            ToolTip(b, COMMAND_TYPES[t].description)
        ebar = ttk.Frame(mid)
        ebar.pack(fill="x", pady=(3, 0))
        for text, cmd, tip in (("Edit…", self.edit_selected, "Edit the selected command (Enter / double-click)"),
                               ("Duplicate", self.duplicate, "Copy the selected command(s) (Ctrl+D)"),
                               ("Delete", self.delete_commands, "Delete the selected command(s) (Del)"),
                               ("▲ Up", lambda: self.move(-1), "Move up (Alt+Up)"),
                               ("▼ Down", lambda: self.move(1), "Move down (Alt+Down)"),
                               ("Undo", self.undo, "Undo (Ctrl+Z)")):
            b = ttk.Button(ebar, text=text, command=cmd)
            b.pack(side="left", padx=1)
            ToolTip(b, tip)

        qd = ttk.LabelFrame(mid, text="Quick dialogue - type a line and press Enter", padding=6)
        qd.pack(fill="x", pady=(8, 0))
        self.quick_char = ttk.Combobox(qd, width=16, state="readonly")
        self.quick_char.pack(side="left")
        ToolTip(self.quick_char, "Who is speaking")
        self.quick_expr = ttk.Combobox(qd, width=10)
        self.quick_expr.pack(side="left", padx=4)
        ToolTip(self.quick_expr, "Expression (optional)")
        self.quick_char.bind("<<ComboboxSelected>>", lambda e: self.update_quick_expressions())
        self.quick_text = ttk.Entry(qd)
        self.quick_text.pack(side="left", fill="x", expand=True, padx=4)
        self.quick_text.bind("<Return>", lambda e: self.quick_add())
        ttk.Button(qd, text="Add line", command=self.quick_add).pack(side="left")
        ws.add(mid, weight=4)

        # --- help -----------------------------------------------------------
        right = ttk.Frame(ws, padding=10)
        ttk.Label(right, text="Help", style="Heading.TLabel").pack(anchor="w")
        self.help_title = ttk.Label(right, text="", font=("TkDefaultFont", 10, "bold"))
        self.help_title.pack(anchor="w", pady=(6, 2))
        self.help_text = ttk.Label(right, text="", wraplength=230, justify="left")
        self.help_text.pack(anchor="w")
        ttk.Separator(right).pack(fill="x", pady=10)
        ttk.Label(right, wraplength=230, justify="left", foreground=HELP_FG, text=(
            "Tips\n\n• Use {variable} in dialogue to show a variable's value.\n\n"
            "• Choices branch your story. Give each option its own scene, then Jump back to a shared "
            "scene to merge paths.\n\n"
            "• Missing art? The game draws placeholders, so write first and add images later.\n\n"
            "• Press F7 often to catch mistakes early.")).pack(anchor="w")
        ws.add(right, weight=1)

    def bind_keys(self):
        r = self.root

        def in_text(e):
            return isinstance(e.widget, (tk.Text, tk.Entry, ttk.Entry, ttk.Combobox))

        r.bind("<Control-n>", lambda e: self.new_project())
        r.bind("<Control-o>", lambda e: self.open_dialog())
        r.bind("<Control-s>", lambda e: self.save())
        r.bind("<Control-z>", lambda e: None if in_text(e) else self.undo())
        r.bind("<Control-y>", lambda e: None if in_text(e) else self.redo())
        r.bind("<Control-Z>", lambda e: None if in_text(e) else self.redo())
        r.bind("<Control-d>", lambda e: None if in_text(e) else self.duplicate())
        r.bind("<Control-c>", lambda e: None if in_text(e) else self.copy_commands())
        r.bind("<Control-v>", lambda e: None if in_text(e) else self.paste_commands())
        r.bind("<Alt-Up>", lambda e: self.move(-1))
        r.bind("<Alt-Down>", lambda e: self.move(1))
        r.bind("<F5>", lambda e: self.play())
        r.bind("<Shift-F5>", lambda e: self.play(self.scene))
        r.bind("<F7>", lambda e: self.check_story())
        r.bind("<F8>", lambda e: self.story_map())

    def info_window(self, title, text):
        win = tk.Toplevel(self.root)
        win.title(title)
        win.transient(self.root)
        t = tk.Text(win, width=100, height=min(30, text.count("\n") + 2), wrap="word", padx=12, pady=12,
                    font=("TkFixedFont", 10), relief="flat")
        t.insert("1.0", text)
        t.configure(state="disabled")
        t.pack(fill="both", expand=True)
        ttk.Button(win, text="Close", command=win.destroy).pack(pady=6)
        return win

    def set_status(self, text):
        self.status.configure(text=text)

    # ------------------------------------------------------------ projects
    def show_welcome(self):
        self.workspace.pack_forget()
        self.refresh_welcome_recent()
        self.welcome.pack(fill="both", expand=True)
        self.update_title()

    def show_workspace(self):
        self.welcome.pack_forget()
        self.workspace.pack(fill="both", expand=True)
        self.root.after(50, self.place_sashes)

    def place_sashes(self):
        self.root.update_idletasks()
        width = self.workspace.winfo_width()
        if width > 700:
            self.workspace.sashpos(0, 270)
            self.workspace.sashpos(1, width - 270)

    def require_project(self) -> bool:
        if self.story is None:
            self.set_status("Create or open a project first.")
            return False
        return True

    def confirm_discard(self) -> bool:
        if not self.dirty:
            return True
        ans = messagebox.askyesnocancel("Unsaved changes", "Save your changes first?", parent=self.root)
        if ans is None:
            return False
        if ans:
            return self.save()
        return True

    def new_project(self):
        if not self.confirm_discard():
            return
        title = simpledialog.askstring("New project", "What is your visual novel called?", parent=self.root,
                                       initialvalue="My Visual Novel")
        if not title:
            return
        parent = filedialog.askdirectory(parent=self.root, title="Choose where to create the project folder",
                                         initialdir=os.path.expanduser("~"))
        if not parent:
            return
        safe = "".join(ch for ch in title if ch.isalnum() or ch in " _-").strip() or "MyVisualNovel"
        folder = os.path.join(parent, safe)
        try:
            create_project(folder, title=title)
        except (StoryError, OSError) as exc:
            messagebox.showerror("New project", str(exc), parent=self.root)
            return
        self.open_project(folder, skip_confirm=True)
        self.set_status(f"Created {folder}. Edit the starter scenes, or delete them and write your own!")

    def open_dialog(self):
        if not self.confirm_discard():
            return
        path = filedialog.askopenfilename(parent=self.root, title="Open story.json",
                                          filetypes=[("OpenNovella story", "story.json"), ("JSON", "*.json")])
        if path:
            self.open_project(path, skip_confirm=True)

    def open_project(self, path, skip_confirm=False):
        if not skip_confirm and not self.confirm_discard():
            return
        try:
            story = Story.load(path)
        except StoryError as exc:
            messagebox.showerror("Open project", str(exc), parent=self.root)
            return
        self.story = story
        self.dirty = False
        self.undo_stack.clear()
        self.redo_stack.clear()
        self.scene = None
        recent = [p for p in self.config.get("recent", []) if p != story.path]
        self.config["recent"] = [story.path] + recent[:9]
        save_config(self.config)
        self.refresh_recent()
        self.show_workspace()
        self.refresh_all()
        self.select_scene(story.start_scene if story.start_scene in story.scenes else next(iter(story.scenes)))
        self.set_status(f"Opened {story.path}")

    def open_demo(self):
        """Open the demo; copy it to the home folder first if it's installed read-only (e.g. from the .deb)."""
        path = DEMO_PATH
        if not os.access(path, os.W_OK):
            path = os.path.join(os.path.expanduser("~"), "OpenNovella", "The Lantern Festival")
            if not os.path.isfile(os.path.join(path, STORY_FILENAME)):
                try:
                    shutil.copytree(DEMO_PATH, path, dirs_exist_ok=True, copy_function=shutil.copyfile,
                                    ignore=shutil.ignore_patterns("saves", "__pycache__"))
                    for folder, _dirs, _files in os.walk(path):  # the source may be read-only
                        os.chmod(folder, 0o755)
                except OSError as exc:
                    messagebox.showerror("Demo", f"Could not copy the demo to {path}: {exc}", parent=self.root)
                    return
                self.set_status(f"Copied the demo to {path} so you can edit it.")
        self.open_project(path)

    def refresh_recent(self):
        self.recent_menu.delete(0, "end")
        recent = self.config.get("recent", [])
        for p in recent:
            self.recent_menu.add_command(label=p, command=lambda p=p: self.open_project(p))
        if not recent:
            self.recent_menu.add_command(label="(none)", state="disabled")

    def save(self) -> bool:
        if not self.require_project():
            return False
        try:
            self.story.save()
        except (OSError, StoryError) as exc:
            messagebox.showerror("Save", f"Could not save: {exc}", parent=self.root)
            return False
        self.dirty = False
        self.update_title()
        self.set_status(f"Saved {os.path.join(self.story.path, STORY_FILENAME)}")
        return True

    def open_folder(self):
        if not self.require_project():
            return
        path = self.story.path
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa: S606 - opening the user's own folder
            elif sys.platform == "darwin":
                subprocess.Popen(["open", path])
            else:
                subprocess.Popen(["xdg-open", path])
        except OSError as exc:
            messagebox.showinfo("Project folder", f"{path}\n\n({exc})", parent=self.root)

    def export_game(self):
        if not self.require_project() or not self.save():
            return
        from ..export import export_game
        parent = filedialog.askdirectory(parent=self.root, title="Choose where to put the exported game")
        if not parent:
            return
        safe = "".join(ch for ch in self.story.title if ch.isalnum() or ch in " _-").strip() or "game"
        out = os.path.join(parent, safe + " (game)")
        try:
            export_game(self.story, out)
        except (ValueError, OSError) as exc:
            messagebox.showerror("Export", str(exc), parent=self.root)
            return
        messagebox.showinfo("Export", f"Your game was exported to:\n{out}\n\nPlayers run play.py "
                                      "(see README.txt in that folder).", parent=self.root)

    def quit(self):
        if not self.confirm_discard():
            return
        self.config["geometry"] = self.root.geometry()
        save_config(self.config)
        self.root.destroy()

    def update_title(self):
        if self.story:
            self.root.title(f"{'*' if self.dirty else ''}{self.story.title} - OpenNovella {__version__}")
        else:
            self.root.title(f"OpenNovella {__version__}")

    # ----------------------------------------------------------- undo/redo
    def checkpoint(self):
        """Call before every change so it can be undone."""
        self.undo_stack.append((copy.deepcopy(self.story.to_dict()), self.scene))
        del self.undo_stack[:-MAX_UNDO]
        self.redo_stack.clear()

    def changed(self, select_index=None):
        self.dirty = True
        self.update_title()
        self.refresh_all(select_index)

    def _restore(self, src, dst):
        if not self.story or not src:
            return
        dst.append((copy.deepcopy(self.story.to_dict()), self.scene))
        data, scene = src.pop()
        path = self.story.path
        self.story = Story.from_dict(data)
        self.story.path = path
        self.scene = scene if scene in self.story.scenes else next(iter(self.story.scenes))
        self.dirty = True
        self.update_title()
        self.refresh_all()

    def undo(self):
        if self.undo_stack:
            self._restore(self.undo_stack, self.redo_stack)
            self.set_status("Undone")

    def redo(self):
        if self.redo_stack:
            self._restore(self.redo_stack, self.undo_stack)
            self.set_status("Redone")

    # -------------------------------------------------------------- scenes
    def refresh_all(self, select_index=None):
        if not self.story:
            return
        self.refresh_scenes()
        self.refresh_commands(select_index)
        self.refresh_quick_bar()
        if self.map_window and self.map_window.winfo_exists():
            self.map_window.refresh()

    def refresh_scenes(self):
        self.scene_list.delete(0, "end")
        problems = {i.scene for i in validate(self.story) if i.level == ERROR}
        for name in self.story.scenes:
            mark = "★ " if name == self.story.start_scene else "    "
            self.scene_list.insert("end", f"{mark}{name}" + ("  ⚠" if name in problems else ""))
        if self.scene in self.story.scenes:
            idx = list(self.story.scenes).index(self.scene)
            self.scene_list.selection_set(idx)
            self.scene_list.see(idx)

    def on_scene_select(self):
        sel = self.scene_list.curselection()
        if not sel:
            return
        name = list(self.story.scenes)[sel[0]]
        if name != self.scene:
            self.scene = name
            self.refresh_commands()

    def select_scene(self, name, index=None):
        if not self.story or name not in self.story.scenes:
            return
        self.scene = name
        self.refresh_scenes()
        self.refresh_commands(index)

    def add_scene(self):
        if not self.require_project():
            return
        story_copy = self.story.copy()
        name = ask_new_scene(self.root, story_copy, suggest_scene_name(self.story))
        if not name:
            return
        self.checkpoint()
        self.story.add_scene(name, after=self.scene)
        self.scene = name
        self.changed()
        self.set_status(f"Added scene “{name}”. Connect it with a Choice or Jump.")

    def rename_scene(self):
        if not self.require_project() or not self.scene:
            return
        new = simpledialog.askstring("Rename scene", "New name:", parent=self.root, initialvalue=self.scene)
        if not new or new.strip() == self.scene:
            return
        trial = self.story.copy()
        try:
            trial.rename_scene(self.scene, new)
        except StoryError as exc:
            messagebox.showerror("Rename scene", str(exc), parent=self.root)
            return
        self.checkpoint()
        self.story.rename_scene(self.scene, new)
        self.scene = new.strip()
        self.changed()
        self.set_status("Scene renamed - every jump and choice pointing to it was updated.")

    def duplicate_scene(self):
        if not self.require_project() or not self.scene:
            return
        name = suggest_scene_name(self.story, self.scene + "_copy")
        self.checkpoint()
        self.story.add_scene(name, after=self.scene)
        self.story.scenes[name] = copy.deepcopy(self.story.scenes[self.scene])
        self.scene = name
        self.changed()

    def delete_scene(self):
        if not self.require_project() or not self.scene:
            return
        refs = self.story.references_to(self.scene)
        msg = f"Delete the scene “{self.scene}” and its {len(self.story.commands(self.scene))} commands?"
        if refs:
            msg += f"\n\n⚠ {len(refs)} jump(s)/choice(s) lead here and will become broken links."
        if not messagebox.askyesno("Delete scene", msg, parent=self.root):
            return
        try:
            self.checkpoint()
            self.story.delete_scene(self.scene)
        except StoryError as exc:
            self.undo_stack.pop()
            messagebox.showerror("Delete scene", str(exc), parent=self.root)
            return
        self.scene = next(iter(self.story.scenes))
        self.changed()

    def set_start(self):
        if not self.require_project() or not self.scene:
            return
        self.checkpoint()
        self.story.start_scene = self.scene
        self.changed()
        self.set_status(f"The story now starts at “{self.scene}”.")

    def on_notes_changed(self, _e=None):
        if not self.notes.edit_modified():
            return
        self.notes.edit_modified(False)
        if self._loading_notes or not self.story or not self.scene:
            return
        self.story.scenes[self.scene]["notes"] = self.notes.get("1.0", "end-1c")
        if not self.dirty:
            self.dirty = True
            self.update_title()

    # ------------------------------------------------------------ commands
    def refresh_commands(self, select_index=None):
        self.tree.delete(*self.tree.get_children())
        if not self.story or self.scene not in self.story.scenes:
            return
        problems = {i.index for i in validate(self.story) if i.scene == self.scene and i.level == ERROR}
        for i, cmd in enumerate(self.story.commands(self.scene)):
            t = cmd.get("type", "?")
            spec = COMMAND_TYPES.get(t)
            label = spec.label if spec else t
            tags = ["note"] if t == "note" else [spec.category if spec else "Story"]
            if t in ("choice", "jump", "if", "end"):
                tags.append("branch")
            if i in problems:
                tags.append("problem")
            self.tree.insert("", "end", iid=str(i), values=(i + 1, label, summarize(cmd, self.story)), tags=tags)
        if select_index is not None:
            items = self.tree.get_children()
            if items:
                idxs = select_index if isinstance(select_index, (list, tuple)) else [select_index]
                sel = [str(min(max(0, i), len(items) - 1)) for i in idxs]
                self.tree.selection_set(sel)
                self.tree.see(sel[-1])
                self.tree.focus(sel[-1])
        n = len(self.story.commands(self.scene))
        start = "  ★ start scene" if self.scene == self.story.start_scene else ""
        self.scene_title.configure(text=f"Scene: {self.scene}   ({n} commands){start}")
        self._loading_notes = True
        self.notes.delete("1.0", "end")
        self.notes.insert("1.0", self.story.scenes[self.scene].get("notes", ""))
        self.notes.edit_modified(False)
        self._loading_notes = False
        outs = sorted({t for t, _l, _i in self.story.links(self.scene)})
        ins = sorted({s for s, _i in self.story.references_to(self.scene)})
        self.links_label.configure(text=f"Leads to: {', '.join(outs) or '—'}\nReached from: {', '.join(ins) or '—'}")
        self.update_help()

    def selected_indices(self) -> list[int]:
        return sorted(int(i) for i in self.tree.selection())

    def insert_position(self) -> int:
        sel = self.selected_indices()
        return sel[-1] + 1 if sel else len(self.story.commands(self.scene))

    def add_command(self, cmd_type, values=None):
        if not self.require_project() or not self.scene:
            return
        cmd = new_command(cmd_type, **(values or {}))
        if cmd_type == "say" and self.quick_char.get() not in ("", NARRATOR):
            cmd["character"] = self.quick_char.get()
        before = self.story.copy()  # the dialog may create new scenes
        res = CommandDialog(self.root, self.story, cmd, is_new=True).show()
        if not res:
            self.record_new_scenes(before)
            return
        self.undo_stack.append((copy.deepcopy(before.to_dict()), self.scene))
        self.redo_stack.clear()
        pos = self.insert_position()
        self.story.commands(self.scene).insert(pos, res)
        self.changed(pos)
        self.tree.focus_set()

    def record_new_scenes(self, before: Story):
        """Scenes created inside a cancelled dialog are kept; make that undoable and refresh."""
        if set(before.scenes) != set(self.story.scenes):
            self.undo_stack.append((copy.deepcopy(before.to_dict()), self.scene))
            self.changed()

    def edit_selected(self):
        sel = self.selected_indices()
        if not self.story or not sel:
            return
        i = sel[0]
        cmd = self.story.commands(self.scene)[i]
        if cmd.get("type") not in COMMAND_TYPES:
            messagebox.showinfo("Edit", "This command type is unknown; edit it in story.json.", parent=self.root)
            return
        before = self.story.copy()
        res = CommandDialog(self.root, self.story, cmd).show()
        if res is None:
            self.record_new_scenes(before)
            return
        self.undo_stack.append((copy.deepcopy(before.to_dict()), self.scene))
        self.redo_stack.clear()
        self.story.commands(self.scene)[i] = res
        self.changed(i)
        self.tree.focus_set()

    def delete_commands(self):
        sel = self.selected_indices()
        if not self.story or not sel:
            return
        self.checkpoint()
        cmds = self.story.commands(self.scene)
        for i in reversed(sel):
            del cmds[i]
        self.changed(min(sel[0], len(cmds) - 1) if cmds else None)
        self.set_status(f"Deleted {len(sel)} command(s). Ctrl+Z to undo.")

    def duplicate(self):
        sel = self.selected_indices()
        if not self.story or not sel:
            return
        self.checkpoint()
        cmds = self.story.commands(self.scene)
        copies = [copy.deepcopy(cmds[i]) for i in sel]
        pos = sel[-1] + 1
        cmds[pos:pos] = copies
        self.changed(list(range(pos, pos + len(copies))))

    def copy_commands(self):
        sel = self.selected_indices()
        if self.story and sel:
            self.clipboard = [copy.deepcopy(self.story.commands(self.scene)[i]) for i in sel]
            self.set_status(f"Copied {len(sel)} command(s).")

    def paste_commands(self):
        if not self.story or not self.clipboard or not self.scene:
            return
        self.checkpoint()
        pos = self.insert_position()
        self.story.commands(self.scene)[pos:pos] = copy.deepcopy(self.clipboard)
        self.changed(list(range(pos, pos + len(self.clipboard))))

    def move(self, d):
        sel = self.selected_indices()
        if not self.story or not sel:
            return
        cmds = self.story.commands(self.scene)
        if sel[0] + d < 0 or sel[-1] + d >= len(cmds):
            return
        self.checkpoint()
        block = [cmds[i] for i in sel]
        for i in reversed(sel):
            del cmds[i]
        pos = sel[0] + d
        cmds[pos:pos] = block
        self.changed(list(range(pos, pos + len(block))))

    def tree_context_menu(self, event):
        row = self.tree.identify_row(event.y)
        if row and row not in self.tree.selection():
            self.tree.selection_set(row)
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="Edit…", command=self.edit_selected)
        menu.add_cascade(label="Add command after", menu=self.make_add_menu(menu))
        menu.add_command(label="Duplicate", command=self.duplicate)
        menu.add_command(label="Copy", command=self.copy_commands)
        menu.add_command(label="Paste", command=self.paste_commands)
        menu.add_separator()
        menu.add_command(label="Move up", command=lambda: self.move(-1))
        menu.add_command(label="Move down", command=lambda: self.move(1))
        menu.add_command(label="Delete", command=self.delete_commands)
        menu.add_separator()
        menu.add_command(label="▶ Play this scene", command=lambda: self.play(self.scene))
        menu.tk_popup(event.x_root, event.y_root)

    def update_help(self):
        sel = self.selected_indices()
        if self.story and sel and self.scene:
            t = self.story.commands(self.scene)[sel[0]].get("type")
            spec = COMMAND_TYPES.get(t)
            if spec:
                self.help_title.configure(text=spec.label)
                self.help_text.configure(text=spec.description)
                return
        self.help_title.configure(text="Nothing selected")
        self.help_text.configure(text="Select a command to see what it does, or add one with the buttons "
                                      "below the list.")

    # --------------------------------------------------------- quick bar
    def refresh_quick_bar(self):
        values = [NARRATOR] + list(self.story.characters)
        current = self.quick_char.get()
        self.quick_char["values"] = values
        self.quick_char.set(current if current in values else NARRATOR)
        self.update_quick_expressions()

    def update_quick_expressions(self):
        char = self.story.characters.get(self.quick_char.get(), {}) if self.story else {}
        self.quick_expr["values"] = [""] + list((char.get("images") or {}).keys())

    def quick_add(self):
        if not self.require_project() or not self.scene:
            return
        text = self.quick_text.get().strip()
        if not text:
            return
        char = self.quick_char.get()
        self.checkpoint()
        pos = self.insert_position()
        cmd = new_command("say", character="" if char == NARRATOR else char,
                          expression=self.quick_expr.get().strip(), text=text)
        self.story.commands(self.scene).insert(pos, cmd)
        self.quick_text.delete(0, "end")
        self.quick_expr.set("")
        self.changed(pos)
        self.quick_text.focus_set()

    # ------------------------------------------------------ story-level
    def edit_characters(self):
        if not self.require_project():
            return
        res = CharactersDialog(self.root, self.story).show()
        if not res:
            return
        chars, renames = res
        self.checkpoint()
        self.story.characters = chars
        if renames:
            for sc in self.story.scenes.values():
                for cmd in sc["commands"]:
                    if cmd.get("character") in renames:
                        cmd["character"] = renames[cmd["character"]]
        self.changed()

    def edit_variables(self):
        if not self.require_project():
            return
        res = VariablesDialog(self.root, self.story).show()
        if res is not None:
            self.checkpoint()
            self.story.variables = res
            self.changed()

    def edit_settings(self):
        if not self.require_project():
            return
        res = SettingsDialog(self.root, self.story).show()
        if res:
            self.checkpoint()
            self.story.title = res["title"]
            self.story.author = res["author"]
            self.story.resolution = res["resolution"]
            self.story.settings.update(res["settings"])
            self.changed()

    def check_story(self):
        if not self.require_project():
            return
        if self.check_window and self.check_window.winfo_exists():
            self.check_window.refresh()
            self.check_window.lift()
        else:
            self.check_window = ValidationWindow(self)

    def story_map(self):
        if not self.require_project():
            return
        if self.map_window and self.map_window.winfo_exists():
            self.map_window.refresh()
            self.map_window.lift()
        else:
            self.map_window = StoryMapWindow(self)

    def play(self, scene=None):
        if not self.require_project():
            return
        if importlib.util.find_spec("pygame") is None:
            messagebox.showerror("Play", "Playing needs pygame. Install it with:\n\n"
                                         f"{sys.executable} -m pip install pygame Pillow", parent=self.root)
            return
        if not self.save():
            return
        errors = [i for i in validate(self.story) if i.level == ERROR]
        if errors and not messagebox.askyesno(
                "Problems found", f"Your story has {len(errors)} error(s), e.g.:\n\n{errors[0]}\n\n"
                                  "Play anyway?", parent=self.root):
            self.check_story()
            return
        args = [sys.executable, "-m", "opennovella", "play", self.story.path]
        if scene:
            args += ["--scene", scene]
        env = dict(os.environ)
        env["PYTHONPATH"] = PACKAGE_PARENT + os.pathsep + env.get("PYTHONPATH", "")
        try:
            subprocess.Popen(args, env=env)
        except OSError as exc:
            messagebox.showerror("Play", f"Could not start the game: {exc}", parent=self.root)
            return
        self.set_status("Game started" + (f" at scene “{scene}”." if scene else "."))

    # ------------------------------------------------------------- help
    def open_readme(self):
        for path in (os.path.join(PACKAGE_PARENT, "README.md"), "/usr/share/doc/opennovella/README.md"):
            if os.path.isfile(path):
                webbrowser.open("file://" + path)
                return
        self.info_window("Quick Start", QUICK_START)

    def bug_report(self):
        text = report_template(self.story.path if self.story else None)
        win = self.info_window("Report a Bug", text)
        tk.Label(win, text="Copy this text into your bug report. See BUG_REPORT.md for how to submit it.",
                 foreground=HELP_FG).pack()

        def copy_text():
            self.root.clipboard_clear()
            self.root.clipboard_append(text)
            self.set_status("Bug report copied to the clipboard.")
        ttk.Button(win, text="Copy to clipboard", command=copy_text).pack(pady=(0, 8))


def run_editor(project: str | None = None) -> int:
    root = tk.Tk()
    EditorApp(root, project)
    root.mainloop()
    return 0
