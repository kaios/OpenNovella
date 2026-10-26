import pytest

from opennovella.engine import Engine, EngineError
from opennovella.story import Story, new_command as c, new_option as o


def make_story():
    s = Story("Test")
    s.variables = {"gold": 0}
    s.characters = {"amy": {"name": "Amy", "color": "#ff0000", "images": {"default": "", "happy": ""}}}
    s.scenes = {
        "start": {"commands": [
            c("background", color="#112233"),
            c("show", character="amy"),
            c("say", character="amy", text="Hello! Gold: {gold}"),
            c("choice", options=[o("Take gold", "rich", effects="gold += 10"),
                                 o("Leave", "poor"),
                                 o("Secret", "rich", condition="gold > 100")]),
        ]},
        "rich": {"commands": [
            c("say", character="amy", expression="happy", text="You have {gold} gold."),
            c("if", condition="gold >= 10", then_scene="good_end", else_scene="poor"),
        ]},
        "poor": {"commands": [c("say", text="Nothing."), c("end", text="Bad", ending="bad")]},
        "good_end": {"commands": [c("end", text="Yay", ending="good")]},
    }
    return s


def run_to_block(engine):
    while True:
        ev = engine.step()
        if ev.type in ("say", "choice", "end", "wait"):
            return ev


def test_full_branch():
    e = Engine(make_story())
    e.start()
    ev = run_to_block(e)
    assert ev.type == "say" and ev["name"] == "Amy" and ev["text"] == "Hello! Gold: 0"
    assert e.background["color"] == "#112233" and "amy" in e.shown
    ev = run_to_block(e)
    assert ev.type == "choice"
    assert [opt["text"] for opt in ev["options"]] == ["Take gold", "Leave"]  # secret hidden
    e.choose(0)
    ev = run_to_block(e)
    assert ev["text"] == "You have 10 gold."
    assert e.shown["amy"]["expression"] == "happy"
    ev = run_to_block(e)
    assert ev.type == "end" and ev["ending"] == "good"


def test_other_branch():
    e = Engine(make_story())
    e.start()
    run_to_block(e)
    run_to_block(e)
    e.choose(1)
    assert run_to_block(e)["text"] == "Nothing."
    assert run_to_block(e)["ending"] == "bad"


def test_save_and_restore_reruns_current_line_without_duplicating_history():
    story = make_story()
    e = Engine(story)
    e.start()
    run_to_block(e)
    run_to_block(e)
    e.choose(0)
    run_to_block(e)  # "You have 10 gold."
    snap = e.snapshot()
    history_len = len(e.history)

    e2 = Engine(story)
    e2.restore(snap)
    ev = run_to_block(e2)
    assert ev["text"] == "You have 10 gold."
    assert e2.variables["gold"] == 10
    assert len(e2.history) == history_len
    assert e2.shown["amy"]["expression"] == "happy"


def test_restore_at_choice():
    story = make_story()
    e = Engine(story)
    e.start()
    run_to_block(e)
    run_to_block(e)  # at the choice
    e2 = Engine(story)
    e2.restore(e.snapshot())
    assert run_to_block(e2).type == "choice"


def test_infinite_jump_loop_is_detected():
    s = Story()
    s.scenes = {"start": {"commands": [c("jump", scene="b")]}, "b": {"commands": [c("jump", scene="start")]}}
    e = Engine(s)
    e.start()
    with pytest.raises(EngineError):
        e.step()


def test_missing_scene_ends_gracefully():
    s = Story()
    s.scenes = {"start": {"commands": [c("jump", scene="nowhere")]}}
    e = Engine(s)
    e.start()
    assert e.step().type == "end"
    assert e.warnings


def test_choice_with_no_visible_options_is_skipped():
    s = Story()
    s.scenes = {"start": {"commands": [
        c("choice", options=[o("Hidden", "", condition="false")]),
        c("say", text="after"),
    ]}}
    e = Engine(s)
    e.start()
    assert run_to_block(e)["text"] == "after"


def test_set_operations():
    s = Story()
    s.scenes = {"start": {"commands": [
        c("set", variable="x", operation="=", value="5"),
        c("set", variable="x", operation="*=", value="2"),
        c("set", variable="name", operation="=", value="Sam"),
        c("say", text="{name} {x}"),
    ]}}
    e = Engine(s)
    e.start()
    assert run_to_block(e)["text"] == "Sam 10"
