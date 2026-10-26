"""Smoke-tests the tkinter editor. Skipped when there is no display
(run under xvfb-run on headless machines)."""

import os
import shutil

import pytest

tk = pytest.importorskip("tkinter")

DEMO = os.path.join(os.path.dirname(__file__), "..", "examples", "demo")


@pytest.fixture
def editor(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    from opennovella.editor import app as editor_app
    monkeypatch.setattr(editor_app, "CONFIG_PATH", str(tmp_path / "editor.json"))
    try:
        root = tk.Tk()
    except tk.TclError:
        pytest.skip("no display available")
    root.withdraw()
    project = tmp_path / "demo"
    shutil.copytree(DEMO, project, ignore=shutil.ignore_patterns("saves"))
    ed = editor_app.EditorApp(root, str(project))
    yield ed
    ed.dirty = False
    root.destroy()


def test_quick_add_undo_redo(editor):
    editor.select_scene("square")
    before = len(editor.story.commands("square"))
    editor.quick_char.set("mira")
    editor.quick_text.insert(0, "A new line")
    editor.quick_add()
    assert len(editor.story.commands("square")) == before + 1
    assert editor.dirty
    editor.undo()
    assert len(editor.story.commands("square")) == before
    editor.redo()
    assert len(editor.story.commands("square")) == before + 1


def test_reorder_duplicate_delete(editor):
    editor.select_scene("start", 1)
    cmds = editor.story.commands("start")
    second = dict(cmds[1])
    editor.move(-1)
    assert editor.story.commands("start")[0] == second
    editor.duplicate()
    assert editor.story.commands("start")[1] == second
    editor.delete_commands()
    assert editor.story.commands("start")[0] == second


def test_save_and_windows(editor):
    editor.story_map()
    editor.check_story()
    editor.root.update()
    assert editor.save()
    assert not editor.dirty
