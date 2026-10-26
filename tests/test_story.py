import json
import os

import pytest

from opennovella.story import (COMMAND_TYPES, Story, StoryError, create_project, load_story,
                               new_command as c, new_option as o, summarize)
from opennovella.validate import ERROR, validate

DEMO = os.path.join(os.path.dirname(__file__), "..", "examples", "demo")


def test_new_project_round_trip(tmp_path):
    story = create_project(tmp_path / "proj", title="Round Trip", author="Me")
    assert (tmp_path / "proj" / "story.json").exists()
    for sub in ("images", "audio", "fonts"):
        assert (tmp_path / "proj" / sub).is_dir()
    loaded = load_story(str(tmp_path / "proj"))
    assert loaded.title == "Round Trip" and loaded.author == "Me"
    assert loaded.to_dict() == story.to_dict()
    assert not [i for i in validate(loaded) if i.level == ERROR]
    with pytest.raises(StoryError):
        create_project(tmp_path / "proj")


def test_bad_json_gives_friendly_error(tmp_path):
    (tmp_path / "story.json").write_text("{ not json")
    with pytest.raises(StoryError, match="not valid JSON"):
        load_story(str(tmp_path))


def test_newer_format_is_refused(tmp_path):
    (tmp_path / "story.json").write_text(json.dumps({"format": 999, "scenes": {}}))
    with pytest.raises(StoryError, match="newer version"):
        load_story(str(tmp_path))


def test_rename_scene_updates_every_link():
    s = Story()
    s.scenes = {
        "start": {"commands": [c("choice", options=[o("Go", "old")]), c("jump", scene="old")]},
        "old": {"commands": [c("if", condition="true", then_scene="old", else_scene="start")]},
    }
    s.start_scene = "old"
    s.rename_scene("old", "new")
    assert s.start_scene == "new"
    assert s.scenes["start"]["commands"][0]["options"][0]["target"] == "new"
    assert s.scenes["start"]["commands"][1]["scene"] == "new"
    assert s.scenes["new"]["commands"][0]["then_scene"] == "new"
    with pytest.raises(StoryError):
        s.rename_scene("new", "start")


def test_add_scene_after_keeps_order():
    s = Story()
    s.add_scene("c")
    s.add_scene("b", after="start")
    assert s.scene_names() == ["start", "b", "c"]
    with pytest.raises(StoryError):
        s.add_scene("bad/name")


def test_validator_finds_problems():
    s = Story()
    s.scenes = {"start": {"commands": [
        c("jump", scene="missing"),
        c("if", condition="gold >=", then_scene="start"),
        c("choice", options=[o("", "start", effects="gold == 1")]),
        c("show", character="ghost", position="upside_down"),
    ]}, "orphan": {"commands": [c("say", text="hi"), c("end")]}}
    messages = [str(i) for i in validate(s)]
    text = "\n".join(messages)
    assert "doesn't exist" in text
    assert "Could not understand" in text
    assert "has no text" in text
    assert "Unknown position" in text
    assert "never see it" in text


def test_every_command_type_has_summary_and_defaults():
    s = Story()
    for t in COMMAND_TYPES:
        cmd = c(t)
        assert cmd["type"] == t
        assert isinstance(summarize(cmd, s), str)


def test_demo_story_is_valid():
    story = load_story(DEMO)
    errors = [i for i in validate(story) if i.level == ERROR]
    assert not errors, errors
    # every ending is reachable
    assert {"ending_best", "ending_good", "ending_rain"} <= story.reachable_scenes()
