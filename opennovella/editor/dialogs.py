"""Dialog windows used by the editor."""

from __future__ import annotations

import copy
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk

from .. import __credits__, __version__
from ..expressions import ExpressionError, check_expression, parse_statements, parse_value
from ..story import COMMAND_TYPES, VARIABLE_NAME_RE, Story, new_option
from ..validate import ERROR, WARNING, validate
from .widgets import HELP_FG, AssetField, ColorField, SceneField, ToolTip, load_thumbnail


class Dialog(tk.Toplevel):
    """Modal dialog base: builds body(), adds OK / Cancel, returns self.result."""

    def __init__(self, parent, title, ok_text="OK"):
        super().__init__(parent)
        self.withdraw()
        self.title(title)
        self.transient(parent)
        self.result = None
        self.resizable(True, True)
        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)
        self.body_frame = ttk.Frame(outer)
        self.body_frame.pack(fill="both", expand=True)
        self.body(self.body_frame)
        buttons = ttk.Frame(outer)
        buttons.pack(fill="x", pady=(12, 0))
        ttk.Button(buttons, text="Cancel", command=self.cancel).pack(side="right")
        ttk.Button(buttons, text=ok_text, style="Accent.TButton", command=self.ok).pack(side="right", padx=6)
        self.bind("<Escape>", lambda e: self.cancel())
        self.protocol("WM_DELETE_WINDOW", self.cancel)
        self.update_idletasks()
        px, py = parent.winfo_rootx(), parent.winfo_rooty()
        pw, ph = parent.winfo_width(), parent.winfo_height()
        w, h = self.winfo_reqwidth(), self.winfo_reqheight()
        self.geometry(f"+{max(0, px + (pw - w) // 2)}+{max(0, py + (ph - h) // 3)}")
        self.deiconify()
        try:
            self.wait_visibility()
            self.grab_set()
        except tk.TclError:  # some window managers refuse grabs; the dialog still works
            pass
        self.focus_set()

    def body(self, frame):
        pass

    def apply(self):
        """Validate and set self.result. Return False to keep the dialog open."""
        return True

    def ok(self):
        if self.apply() is not False:
            self.destroy()

    def cancel(self):
        self.result = None
        self.destroy()

    def show(self):
        self.wait_window()
        return self.result


def help_label(parent, text, row, column=1):
    if text:
        ttk.Label(parent, text=text, foreground=HELP_FG, wraplength=420, justify="left").grid(
            row=row, column=column, sticky="w", pady=(0, 6))


# --------------------------------------------------------------------------
# Command editor
# --------------------------------------------------------------------------

class CommandDialog(Dialog):
    def __init__(self, parent, story: Story, cmd: dict, is_new=False):
        self.story = story
        self.cmd = copy.deepcopy(cmd)
        self.spec = COMMAND_TYPES[cmd["type"]]
        self.widgets = {}
        super().__init__(parent, ("Add " if is_new else "Edit ") + self.spec.label)

    def body(self, frame):
        ttk.Label(frame, text=self.spec.label, style="Heading.TLabel").grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(frame, text=self.spec.description, foreground=HELP_FG, wraplength=520, justify="left").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))
        row = 2
        first = None
        for f in self.spec.fields:
            ttk.Label(frame, text=f.label + ("" if not f.required else " *")).grid(
                row=row, column=0, sticky="nw", padx=(0, 10), pady=3)
            w = self.make_widget(frame, f, self.cmd.get(f.name, f.default))
            w.grid(row=row, column=1, sticky="ew", pady=3)
            first = first or w
            self.widgets[f.name] = (f, w)
            row += 1
            if f.help:
                help_label(frame, f.help, row)
                row += 1
        frame.columnconfigure(1, weight=1)
        self.link_character_expression()
        target = first.text if isinstance(first, tk.Text) else first
        try:
            target.focus_set()
        except (AttributeError, tk.TclError):
            pass
        if self.cmd["type"] == "say":
            self.bind("<Control-Return>", lambda e: self.ok())
            ttk.Label(frame, text="Tip: press Ctrl+Enter to save.", foreground=HELP_FG).grid(
                row=row, column=1, sticky="w")

    def make_widget(self, parent, f, value):
        story = self.story
        if f.kind == "multiline":
            box = ttk.Frame(parent)
            text = tk.Text(box, width=52, height=5, wrap="word", font=("TkDefaultFont", 11), undo=True)
            text.insert("1.0", value or "")
            text.pack(fill="both", expand=True)
            box.text = text
            box.get = lambda: text.get("1.0", "end-1c")
            return box
        if f.kind == "bool":
            var = tk.BooleanVar(value=bool(value))
            cb = ttk.Checkbutton(parent, variable=var)
            cb.get = var.get
            return cb
        if f.kind == "choice":
            combo = ttk.Combobox(parent, values=f.options, state="readonly", width=20)
            combo.set(value if value in f.options else f.default)
            return combo
        if f.kind == "scene":
            blank = "" if f.required else "(continue)"
            field = SceneField(parent, story, value, allow_blank=not f.required, blank_label=blank)
            field.get_value = field.value
            return field
        if f.kind == "character":
            values = [""] + list(story.characters)
            combo = ttk.Combobox(parent, values=values, width=30)
            combo.set(value or "")
            return combo
        if f.kind == "expression":
            combo = ttk.Combobox(parent, values=["default"], width=30)
            combo.set(value or "")
            return combo
        if f.kind == "variable":
            combo = ttk.Combobox(parent, values=story.variable_names(), width=30)
            combo.set(value or "")
            return combo
        if f.kind in ("image", "animation", "audio"):
            return AssetField(parent, story, f.kind, value)
        if f.kind == "color":
            return ColorField(parent, value)
        if f.kind == "condition":
            box = ttk.Frame(parent)
            var = tk.StringVar(value=value or "")
            ttk.Entry(box, textvariable=var, width=44).pack(fill="x")
            status = ttk.Label(box, text="")
            status.pack(anchor="w")

            def check(*_):
                err = check_expression(var.get()) if var.get().strip() else None
                status.configure(text=("✗ " + err) if err else ("✓ Looks good" if var.get().strip() else ""),
                                 foreground="#b3261e" if err else "#2e7d32")
            var.trace_add("write", check)
            check()
            vars_ = story.variable_names()
            if vars_:
                ttk.Label(box, text="Variables: " + ", ".join(vars_), foreground=HELP_FG,
                          wraplength=420).pack(anchor="w")
            box.get = var.get
            return box
        if f.kind == "options":
            return OptionsEditor(parent, story, value or [])
        # text / number
        var = tk.StringVar(value="" if value is None else str(value))
        entry = ttk.Entry(parent, textvariable=var, width=44 if f.kind == "text" else 10)
        entry.get = var.get
        return entry

    def link_character_expression(self):
        """Fill the expression list from the chosen character's images."""
        if "character" not in self.widgets or "expression" not in self.widgets:
            return
        char_w = self.widgets["character"][1]
        expr_w = self.widgets["expression"][1]

        def update(*_):
            char = self.story.characters.get(char_w.get(), {})
            exprs = list((char.get("images") or {}).keys()) or ["default"]
            if self.cmd["type"] == "say":
                exprs = [""] + exprs
            expr_w["values"] = exprs
        char_w.bind("<<ComboboxSelected>>", update)
        char_w.bind("<FocusOut>", update)
        update()

    def apply(self):
        new = {"type": self.cmd["type"]}
        for name, (f, w) in self.widgets.items():
            if f.kind == "scene":
                v = w.get_value()
            elif f.kind == "options":
                v = w.options
            else:
                v = w.get()
            if f.kind == "number":
                try:
                    v = float(str(v).strip() or 0)
                    if v.is_integer() and name in ("loops", "fps"):
                        v = int(v)
                except ValueError:
                    messagebox.showerror("Not a number", f"“{f.label}” must be a number.", parent=self)
                    return False
            elif isinstance(v, str) and f.kind != "multiline":
                v = v.strip()
            if f.required and f.kind != "options" and not str(v).strip():
                messagebox.showerror("Missing value", f"Please fill in “{f.label}”.", parent=self)
                return False
            new[name] = v
        if new["type"] == "choice" and not new.get("options"):
            messagebox.showerror("No options", "Add at least one option for the player to pick.", parent=self)
            return False
        if new["type"] == "if":
            err = check_expression(new.get("condition", ""))
            if err:
                messagebox.showerror("Condition problem", err, parent=self)
                return False
        if new["type"] == "set" and not VARIABLE_NAME_RE.match(new.get("variable", "")):
            messagebox.showerror("Variable name",
                                 "Variable names use letters, numbers and _ and can't start with a number "
                                 "(e.g. courage, met_alice, gold2).", parent=self)
            return False
        # keep any extra keys hand-written in story.json
        for k, v in self.cmd.items():
            new.setdefault(k, v)
        self.result = new
        return True


class OptionsEditor(ttk.Frame):
    """Edits the list of options for a Choice command."""

    def __init__(self, master, story: Story, options):
        super().__init__(master)
        self.story = story
        self.options = copy.deepcopy(options)
        cols = ("text", "target", "condition", "effects")
        self.tree = ttk.Treeview(self, columns=cols, show="headings", height=5, selectmode="browse")
        for c, label, w in zip(cols, ("Button text", "Goes to", "Only if", "Changes"), (220, 120, 120, 140)):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<Double-1>", lambda e: self.edit())
        bar = ttk.Frame(self)
        bar.grid(row=0, column=1, sticky="n", padx=(6, 0))
        for text, cmd in (("Add…", self.add), ("Edit…", self.edit), ("Remove", self.remove),
                          ("▲", lambda: self.move(-1)), ("▼", lambda: self.move(1))):
            ttk.Button(bar, text=text, command=cmd, width=8).pack(fill="x", pady=1)
        self.columnconfigure(0, weight=1)
        self.refresh()
        if not self.options:
            self.after(50, self.add)

    def refresh(self, select=None):
        self.tree.delete(*self.tree.get_children())
        for i, o in enumerate(self.options):
            self.tree.insert("", "end", iid=str(i), values=(o.get("text", ""), o.get("target") or "(continue)",
                                                             o.get("condition", ""), o.get("effects", "")))
        if select is not None and 0 <= select < len(self.options):
            self.tree.selection_set(str(select))

    def selected(self):
        sel = self.tree.selection()
        return int(sel[0]) if sel else None

    def add(self):
        res = OptionDialog(self.winfo_toplevel(), self.story, new_option()).show()
        if res:
            self.options.append(res)
            self.refresh(len(self.options) - 1)

    def edit(self):
        i = self.selected()
        if i is None:
            return
        res = OptionDialog(self.winfo_toplevel(), self.story, self.options[i]).show()
        if res:
            self.options[i] = res
            self.refresh(i)

    def remove(self):
        i = self.selected()
        if i is not None:
            del self.options[i]
            self.refresh(min(i, len(self.options) - 1))

    def move(self, d):
        i = self.selected()
        if i is None or not 0 <= i + d < len(self.options):
            return
        self.options[i], self.options[i + d] = self.options[i + d], self.options[i]
        self.refresh(i + d)


class OptionDialog(Dialog):
    def __init__(self, parent, story, option):
        self.story = story
        self.option = dict(option)
        super().__init__(parent, "Choice option")

    def body(self, f):
        ttk.Label(f, text="Button text *").grid(row=0, column=0, sticky="w", pady=3)
        self.text = tk.StringVar(value=self.option.get("text", ""))
        e = ttk.Entry(f, textvariable=self.text, width=46)
        e.grid(row=0, column=1, sticky="ew", pady=3)
        e.focus_set()
        help_label(f, "What the player sees on the button.", 1)

        ttk.Label(f, text="Goes to scene").grid(row=2, column=0, sticky="w", pady=3)
        self.target = SceneField(f, self.story, self.option.get("target", ""), blank_label="(continue)")
        self.target.grid(row=2, column=1, sticky="w", pady=3)
        help_label(f, "Pick “+ New scene…” to create the branch right now. "
                      "(continue) keeps going in the current scene.", 3)

        ttk.Label(f, text="Only show if").grid(row=4, column=0, sticky="w", pady=3)
        self.condition = tk.StringVar(value=self.option.get("condition", ""))
        ttk.Entry(f, textvariable=self.condition, width=46).grid(row=4, column=1, sticky="ew", pady=3)
        help_label(f, "Optional condition, e.g.  courage >= 2   or   has_key", 5)

        ttk.Label(f, text="Changes").grid(row=6, column=0, sticky="w", pady=3)
        self.effects = tk.StringVar(value=self.option.get("effects", ""))
        ttk.Entry(f, textvariable=self.effects, width=46).grid(row=6, column=1, sticky="ew", pady=3)
        help_label(f, "Optional variable changes when picked, separated by ;\n"
                      "e.g.  courage += 1; met_alice = true", 7)
        f.columnconfigure(1, weight=1)
        self.bind("<Return>", lambda e: self.ok())

    def apply(self):
        if not self.text.get().strip():
            messagebox.showerror("Missing text", "The option needs some button text.", parent=self)
            return False
        cond = self.condition.get().strip()
        err = check_expression(cond) if cond else None
        if err:
            messagebox.showerror("Condition problem", err, parent=self)
            return False
        try:
            parse_statements(self.effects.get())
        except ExpressionError as exc:
            messagebox.showerror("Changes problem", str(exc), parent=self)
            return False
        self.result = {"text": self.text.get().strip(), "target": self.target.value(),
                       "condition": cond, "effects": self.effects.get().strip()}
        return True


# --------------------------------------------------------------------------
# Characters
# --------------------------------------------------------------------------

class CharactersDialog(Dialog):
    def __init__(self, parent, story: Story):
        self.story = story
        self.chars = copy.deepcopy(story.characters)
        self.renames: dict[str, str] = {}
        self.current = None
        super().__init__(parent, "Characters", ok_text="Save")

    def body(self, f):
        left = ttk.Frame(f)
        left.pack(side="left", fill="y")
        ttk.Label(left, text="Characters", style="Heading.TLabel").pack(anchor="w")
        self.listbox = tk.Listbox(left, width=22, height=16, exportselection=False, activestyle="none")
        self.listbox.pack(fill="y", expand=True, pady=4)
        self.listbox.bind("<<ListboxSelect>>", lambda e: self.select())
        bar = ttk.Frame(left)
        bar.pack(fill="x")
        ttk.Button(bar, text="+ Add", command=self.add).pack(side="left")
        ttk.Button(bar, text="Rename id", command=self.rename).pack(side="left", padx=2)
        ttk.Button(bar, text="Delete", command=self.delete).pack(side="left")

        self.right = ttk.Frame(f, padding=(16, 0, 0, 0))
        self.right.pack(side="left", fill="both", expand=True)
        r = self.right
        ttk.Label(r, text="Display name").grid(row=0, column=0, sticky="w", pady=3)
        self.name = tk.StringVar()
        ttk.Entry(r, textvariable=self.name, width=30).grid(row=0, column=1, sticky="w", pady=3)
        ttk.Label(r, text="Name color").grid(row=1, column=0, sticky="w", pady=3)
        self.color = ColorField(r)
        self.color.grid(row=1, column=1, sticky="w", pady=3)
        ttk.Label(r, text="Expressions / images").grid(row=2, column=0, sticky="nw", pady=(12, 3))
        img_box = ttk.Frame(r)
        img_box.grid(row=2, column=1, sticky="nsew", pady=(12, 3))
        self.images = ttk.Treeview(img_box, columns=("expr", "file"), show="headings", height=8,
                                   selectmode="browse")
        self.images.heading("expr", text="Expression")
        self.images.heading("file", text="Image file")
        self.images.column("expr", width=110)
        self.images.column("file", width=260)
        self.images.grid(row=0, column=0, sticky="nsew")
        self.images.bind("<<TreeviewSelect>>", lambda e: self.preview_image())
        self.images.bind("<Double-1>", lambda e: self.set_image())
        ib = ttk.Frame(img_box)
        ib.grid(row=0, column=1, sticky="n", padx=4)
        ttk.Button(ib, text="+ Expression", command=self.add_expression).pack(fill="x", pady=1)
        ttk.Button(ib, text="Set image…", command=self.set_image).pack(fill="x", pady=1)
        ttk.Button(ib, text="Remove", command=self.remove_expression).pack(fill="x", pady=1)
        self.preview = ttk.Label(img_box)
        self.preview.grid(row=1, column=0, sticky="w", pady=6)
        help_label(r, "Every character should have a “default” expression. Add more like happy, sad, "
                      "angry… and pick them in Say and Show commands. No image yet? A placeholder "
                      "silhouette is shown in the game.", 3)
        r.columnconfigure(1, weight=1)
        r.rowconfigure(2, weight=1)
        self.name.trace_add("write", lambda *_: self.store())
        self.color.var.trace_add("write", lambda *_: self.store())
        self.refresh_list()
        if self.chars:
            self.listbox.selection_set(0)
            self.select()
        else:
            self.set_editor_state(False)

    def set_editor_state(self, enabled):
        state = "!disabled" if enabled else "disabled"
        for child in self.right.winfo_children():
            try:
                child.state([state])
            except (AttributeError, tk.TclError):
                pass

    def refresh_list(self, select=None):
        self.listbox.delete(0, "end")
        for cid, c in self.chars.items():
            self.listbox.insert("end", f"{c.get('name') or cid}   ({cid})")
        if select in self.chars:
            idx = list(self.chars).index(select)
            self.listbox.selection_clear(0, "end")
            self.listbox.selection_set(idx)

    def select(self):
        sel = self.listbox.curselection()
        if not sel:
            return
        self.current = None  # don't store while loading fields
        cid = list(self.chars)[sel[0]]
        c = self.chars[cid]
        self.name.set(c.get("name", cid))
        self.color.var.set(c.get("color", "#ffffff"))
        self.current = cid
        self.set_editor_state(True)
        self.refresh_images()

    def store(self):
        if self.current and self.current in self.chars:
            self.chars[self.current]["name"] = self.name.get()
            self.chars[self.current]["color"] = self.color.get()
            sel = self.listbox.curselection()
            if sel:
                self.listbox.delete(sel[0])
                self.listbox.insert(sel[0], f"{self.name.get() or self.current}   ({self.current})")
                self.listbox.selection_set(sel[0])

    def refresh_images(self, select=None):
        self.images.delete(*self.images.get_children())
        if not self.current:
            return
        for expr, path in self.chars[self.current].get("images", {}).items():
            self.images.insert("", "end", iid=expr, values=(expr, path or "(none - placeholder)"))
        if select:
            self.images.selection_set(select)
        self.preview_image()

    def preview_image(self):
        sel = self.images.selection()
        img = None
        if sel and self.current:
            path = self.chars[self.current]["images"].get(sel[0], "")
            img = load_thumbnail(self.story.resolve(path), (180, 220)) if path else None
        self.preview.configure(image=img or "")
        self.preview.image = img

    def add(self):
        name = simpledialog.askstring("New character", "Character's name (as shown in the game):", parent=self)
        if not name or not name.strip():
            return
        base = "".join(ch for ch in name.lower().replace(" ", "_") if ch.isalnum() or ch == "_") or "character"
        cid, n = base, 2
        while cid in self.chars:
            cid = f"{base}{n}"
            n += 1
        self.chars[cid] = {"name": name.strip(), "color": "#ffffff", "images": {"default": ""}}
        self.refresh_list(cid)
        self.select()

    def rename(self):
        if not self.current:
            return
        new = simpledialog.askstring("Rename id", "New id (used inside the story, letters/numbers/_):",
                                     parent=self, initialvalue=self.current)
        if not new or new == self.current:
            return
        new = new.strip()
        if not VARIABLE_NAME_RE.match(new) or new in self.chars:
            messagebox.showerror("Rename id", "That id is invalid or already used.", parent=self)
            return
        self.chars = {(new if k == self.current else k): v for k, v in self.chars.items()}
        # chain renames so A->B->C still updates commands that say A
        for old, cur in list(self.renames.items()):
            if cur == self.current:
                self.renames[old] = new
        self.renames.setdefault(self.current, new)
        self.current = new
        self.refresh_list(new)
        self.select()

    def delete(self):
        if not self.current:
            return
        if not messagebox.askyesno("Delete character",
                                   f"Delete “{self.current}”? Commands that use them will keep the id.",
                                   parent=self):
            return
        del self.chars[self.current]
        self.current = None
        self.refresh_list()
        if self.chars:
            self.listbox.selection_set(0)
            self.select()
        else:
            self.images.delete(*self.images.get_children())
            self.set_editor_state(False)

    def add_expression(self):
        if not self.current:
            return
        expr = simpledialog.askstring("New expression", "Expression name (e.g. happy, sad, angry):", parent=self)
        if not expr or not expr.strip():
            return
        expr = expr.strip()
        self.chars[self.current].setdefault("images", {})[expr] = \
            self.chars[self.current]["images"].get(expr, "")
        self.refresh_images(expr)
        self.set_image()

    def set_image(self):
        sel = self.images.selection()
        if not sel or not self.current:
            return
        holder = AssetField(self, self.story, "image", preview=False)
        holder.browse()
        value = holder.get()
        holder.destroy()
        if value:
            self.chars[self.current]["images"][sel[0]] = value
            self.refresh_images(sel[0])

    def remove_expression(self):
        sel = self.images.selection()
        if sel and self.current:
            del self.chars[self.current]["images"][sel[0]]
            self.refresh_images()

    def apply(self):
        self.store()
        self.result = (self.chars, self.renames)
        return True


# --------------------------------------------------------------------------
# Variables
# --------------------------------------------------------------------------

def _fmt_value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, str):
        return f'"{v}"'
    return str(v)


class VariablesDialog(Dialog):
    def __init__(self, parent, story: Story):
        self.story = story
        self.vars = dict(story.variables)
        super().__init__(parent, "Variables", ok_text="Save")

    def body(self, f):
        ttk.Label(f, text="Variables", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(f, foreground=HELP_FG, wraplength=480, justify="left",
                  text="Variables remember things about the player's journey - numbers (courage = 3), "
                       "true/false flags (met_alice = true) or text (\"Sam\"). Set their starting values "
                       "here, change them with Set Variable or choice options, and test them with If / "
                       "Else or option conditions. Show one in dialogue with {name}.").pack(anchor="w", pady=(0, 8))
        box = ttk.Frame(f)
        box.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(box, columns=("name", "value", "used"), show="headings", height=10)
        for c, label, w in (("name", "Name", 160), ("value", "Starting value", 160), ("used", "Defined", 120)):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w)
        self.tree.pack(side="left", fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda e: self.edit())
        bar = ttk.Frame(box)
        bar.pack(side="left", fill="y", padx=6)
        ttk.Button(bar, text="+ Add", command=self.add).pack(fill="x", pady=1)
        ttk.Button(bar, text="Edit…", command=self.edit).pack(fill="x", pady=1)
        ttk.Button(bar, text="Remove", command=self.remove).pack(fill="x", pady=1)
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        names = sorted(set(self.vars) | set(self.story.variable_names()))
        for n in names:
            if n in self.vars:
                self.tree.insert("", "end", iid=n, values=(n, _fmt_value(self.vars[n]), "here"))
            else:
                self.tree.insert("", "end", iid=n, values=(n, "0 (not set)", "only in Set"))

    def ask(self, name="", value=""):
        name = simpledialog.askstring("Variable", "Variable name:", parent=self, initialvalue=name)
        if not name:
            return None
        name = name.strip()
        if not VARIABLE_NAME_RE.match(name):
            messagebox.showerror("Variable", "Use letters, numbers and _ (and don't start with a number).",
                                 parent=self)
            return None
        raw = simpledialog.askstring("Variable", f"Starting value for {name}\n"
                                     "(a number, true/false, or \"text in quotes\"):",
                                     parent=self, initialvalue=value)
        if raw is None:
            return None
        return name, parse_value(raw)

    def add(self):
        res = self.ask(value="0")
        if res:
            self.vars[res[0]] = res[1]
            self.refresh()

    def edit(self):
        sel = self.tree.selection()
        if not sel:
            return
        old = sel[0]
        res = self.ask(old, _fmt_value(self.vars.get(old, 0)))
        if res:
            self.vars.pop(old, None)
            self.vars[res[0]] = res[1]
            self.refresh()

    def remove(self):
        for n in self.tree.selection():
            self.vars.pop(n, None)
        self.refresh()

    def apply(self):
        self.result = self.vars
        return True


# --------------------------------------------------------------------------
# Project settings
# --------------------------------------------------------------------------

RESOLUTIONS = ["1280x720", "1920x1080", "1600x900", "1024x768", "800x600"]


class SettingsDialog(Dialog):
    def __init__(self, parent, story: Story):
        self.story = story
        super().__init__(parent, "Project settings", ok_text="Save")

    def body(self, f):
        s, st = self.story, self.story.settings
        self.fields = {}
        rows = [
            ("title", "Title", "entry", s.title),
            ("author", "Author", "entry", s.author),
            ("resolution", "Screen size", "resolution", f"{s.resolution[0]}x{s.resolution[1]}"),
            ("text_speed", "Text speed (chars/sec, 0 = instant)", "entry", st.get("text_speed")),
            ("font", "Font file (.ttf/.otf)", "font", st.get("font")),
            ("font_size", "Text size", "entry", st.get("font_size")),
            ("name_font_size", "Name size", "entry", st.get("name_font_size")),
            ("text_color", "Text color", "color", st.get("text_color")),
            ("textbox_color", "Text box color", "color", st.get("textbox_color")),
            ("textbox_opacity", "Text box opacity (0-255)", "entry", st.get("textbox_opacity")),
            ("accent_color", "Accent color (buttons)", "color", st.get("accent_color")),
            ("title_background", "Title screen image", "image", st.get("title_background")),
            ("title_background_color", "Title screen color", "color", st.get("title_background_color")),
            ("title_music", "Title screen music", "audio", st.get("title_music")),
        ]
        for i, (key, label, kind, value) in enumerate(rows):
            ttk.Label(f, text=label).grid(row=i, column=0, sticky="w", padx=(0, 10), pady=3)
            if kind == "color":
                w = ColorField(f, value)
            elif kind in ("image", "audio", "font"):
                w = AssetField(f, s, kind, value, preview=False)
            elif kind == "resolution":
                w = ttk.Combobox(f, values=RESOLUTIONS, width=14)
                w.set(value)
            else:
                var = tk.StringVar(value="" if value is None else str(value))
                w = ttk.Entry(f, textvariable=var, width=40)
                w.get = var.get
            w.grid(row=i, column=1, sticky="ew", pady=3)
            self.fields[key] = w
        f.columnconfigure(1, weight=1)

    def apply(self):
        get = {k: w.get().strip() for k, w in self.fields.items()}
        try:
            res = [int(x) for x in get["resolution"].lower().replace(" ", "").split("x")]
            if len(res) != 2 or min(res) < 200:
                raise ValueError
            nums = {k: float(get[k]) for k in ("text_speed", "font_size", "name_font_size", "textbox_opacity")}
        except ValueError:
            messagebox.showerror("Settings", "Screen size must look like 1280x720 and the sizes, speed and "
                                             "opacity must be numbers.", parent=self)
            return False
        self.result = {"title": get["title"] or "Untitled Story", "author": get["author"], "resolution": res,
                       "settings": {**{k: get[k] for k in get if k not in ("title", "author", "resolution")},
                                    **{k: int(v) for k, v in nums.items()}}}
        return True


# --------------------------------------------------------------------------
# Story check results
# --------------------------------------------------------------------------

class ValidationWindow(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app.root)
        self.app = app
        self.title("Check Story")
        self.geometry("860x440")
        self.transient(app.root)
        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        self.summary = ttk.Label(top, text="", style="Heading.TLabel")
        self.summary.pack(side="left")
        ttk.Button(top, text="Check again", command=self.refresh).pack(side="right")
        frame = ttk.Frame(self, padding=(8, 0, 8, 8))
        frame.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(frame, columns=("level", "where", "message"), show="headings")
        for c, label, w in (("level", "", 100), ("where", "Where", 150), ("message", "Problem", 560)):
            self.tree.heading(c, text=label)
            self.tree.column(c, width=w, stretch=c == "message")
        sb = ttk.Scrollbar(frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=sb.set)
        self.tree.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")
        self.tree.tag_configure(ERROR, foreground="#b3261e")
        self.tree.tag_configure(WARNING, foreground="#8a5a00")
        self.tree.tag_configure("info", foreground="#44516b")
        self.tree.bind("<Double-1>", self.goto)
        self.tree.bind("<<TreeviewSelect>>", self.show_detail)
        self.detail = ttk.Label(self, text="Select a row to read it in full. Double-click to jump to it.",
                                foreground=HELP_FG, wraplength=780, justify="left")
        self.detail.pack(anchor="w", padx=8, pady=(0, 8))
        self.issues = []
        self.refresh()

    def refresh(self):
        self.issues = validate(self.app.story)
        self.tree.delete(*self.tree.get_children())
        icons = {ERROR: "✗ Error", WARNING: "⚠ Warning", "info": "ℹ Note"}
        for i, issue in enumerate(self.issues):
            where = issue.scene + (f"  #{issue.index + 1}" if issue.index >= 0 else "") if issue.scene else "Project"
            self.tree.insert("", "end", iid=str(i), values=(icons[issue.level], where, issue.message),
                             tags=(issue.level,))
        errors = sum(1 for i in self.issues if i.level == ERROR)
        warnings = sum(1 for i in self.issues if i.level == WARNING)
        if not self.issues:
            self.summary.configure(text="✓ No problems found - your story is ready to play!")
        else:
            self.summary.configure(text=f"{errors} error(s), {warnings} warning(s)")

    def show_detail(self, _e=None):
        sel = self.tree.selection()
        if sel:
            self.detail.configure(text=self.issues[int(sel[0])].message + "   (double-click to jump there)")

    def goto(self, _e=None):
        sel = self.tree.selection()
        if not sel:
            return
        issue = self.issues[int(sel[0])]
        if issue.scene in self.app.story.scenes:
            self.app.select_scene(issue.scene, issue.index if issue.index >= 0 else None)
            self.app.root.lift()


# --------------------------------------------------------------------------
# About
# --------------------------------------------------------------------------

def show_about(parent):
    win = tk.Toplevel(parent)
    win.title("About OpenNovella")
    win.transient(parent)
    win.resizable(False, False)
    f = ttk.Frame(win, padding=24)
    f.pack()
    ttk.Label(f, text="OpenNovella", style="Title.TLabel").pack()
    ttk.Label(f, text=f"Version {__version__}").pack(pady=(0, 10))
    ttk.Label(f, text="A friendly visual novel engine for writers of every level.",
              wraplength=360, justify="center").pack()
    ttk.Label(f, text="\nCreated by\nShawn Rapaz & Claude Code", justify="center",
              style="Heading.TLabel").pack()
    ttk.Label(f, text="\nReleased under the GNU General Public License v3.", foreground=HELP_FG).pack()
    ttk.Button(f, text="Close", command=win.destroy).pack(pady=(14, 0))
    ToolTip(f, __credits__)
    win.bind("<Escape>", lambda e: win.destroy())
