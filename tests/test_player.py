"""Runs the real pygame player off-screen and clicks through the demo."""

import os
import shutil

import pytest

os.environ["SDL_VIDEODRIVER"] = "dummy"
os.environ["SDL_AUDIODRIVER"] = "dummy"
os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "1"
pygame = pytest.importorskip("pygame")

from opennovella.player import Player  # noqa: E402
from opennovella.story import load_story  # noqa: E402

DEMO = os.path.join(os.path.dirname(__file__), "..", "examples", "demo")


@pytest.fixture
def demo(tmp_path):
    dest = tmp_path / "demo"
    shutil.copytree(DEMO, dest, ignore=shutil.ignore_patterns("saves"))
    return load_story(str(dest))


def frames(p, n, events=()):
    for i in range(n):
        p.tick(1 / 60, events if i == 0 else ())


def click(p):
    frames(p, 1, [pygame.event.Event(pygame.MOUSEBUTTONUP, button=1, pos=(640, 300))])


def play_through(p, picks):
    picks = list(picks)
    for _ in range(300):
        frames(p, 80)
        g = p.game
        if g.mode == "ending":
            return g.ending["ending"]
        assert g.mode != "error", g.error
        if g.mode == "choice":
            g.pick(picks.pop(0))
        else:
            click(p)
    raise AssertionError("never reached an ending")


@pytest.mark.parametrize("picks,ending", [((0, 0), "Good Ending"), ((1, 1), "Rainy Ending"),
                                          ((1, 2), "Best Ending")])
def test_demo_endings(demo, picks, ending):
    p = Player(demo, headless=True)
    p.new_game()
    assert play_through(p, picks) == ending
    pygame.quit()


def test_save_and_load(demo):
    p = Player(demo, start_scene="hill", headless=True)
    for _ in range(20):  # click until the rain has started
        frames(p, 60)
        if p.game.say and "Rain" in p.game.say["text"]:
            break
        click(p)
    text = p.game.say["text"]
    assert "Rain" in text
    p.save_slot("1")
    p.return_to_title()
    p.load_slot("1")
    frames(p, 30)
    assert p.game.say["text"] == text
    assert [o.id for o in p.game.overlays] == ["rain"]
    pygame.quit()
