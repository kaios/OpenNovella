# OpenNovella

**A friendly visual novel engine for writers of every skill level.**

OpenNovella lets you make visual novels with branching paths, characters,
backgrounds, music, transitions and animations, using a point-and-click
editor. You don't need to write any code. Underneath, stories are saved as
plain, readable JSON, so experienced users can edit them by hand, keep them
in git, or generate them with scripts.

> **Created by Shawn Rapaz and Claude Code.**

---

## Contents

- [Features](#features)
- [Installing](#installing)
- [Your first visual novel in 5 minutes](#your-first-visual-novel-in-5-minutes)
- [How stories work](#how-stories-work)
- [Branching paths](#branching-paths)
- [Command reference](#command-reference)
- [Images and animations](#images-and-animations)
- [Audio](#audio)
- [Playing: controls for players](#playing-controls-for-players)
- [Sharing your game](#sharing-your-game)
  - [Building the .deb](#building-the-deb)
- [Command line](#command-line)
- [The story file format (advanced)](#the-story-file-format-advanced)
- [Project layout](#project-layout)
- [Troubleshooting](#troubleshooting)
- [Reporting bugs](#reporting-bugs)
- [Developing OpenNovella](#developing-opennovella)
- [Credits and license](#credits-and-license)

---

## Features

**For writers**
- A visual editor: scenes on the left, commands in the middle, and help text on the right
- A **Quick dialogue** bar: pick a speaker, type a line, press Enter, repeat
- **Choices** that branch the story. You can create the new branch scene straight from the option dialog
- **Variables** that remember decisions (`courage += 1`) and **conditions** (`courage >= 3`) that
  hide options or change the path
- A **Story Map** that draws your branching paths as a flowchart
- **Check Story** (F7) finds broken links, missing images, typos in conditions and scenes no one can reach
- Undo/redo, copy/paste, scene notes, and renaming that updates every link for you
- **Placeholders** for any missing art, so you can write the whole story before you have pictures

**For players**
- A polished title screen, typewriter text, name tags, a history log, auto mode and skip mode
- 30 save slots with thumbnails, plus quick save and quick load
- A settings screen with text speed, volume and fullscreen
- Tracks which endings the player has found

**Visuals and animation**
- Backgrounds: fade, dissolve and slide transitions
- Characters: fade, slide and zoom entrances, smooth movement between positions, and
  bounce/shake/jump/float/pulse effects
- Screen effects: shake, flash, fade to color, and tint (for night scenes or flashbacks)
- Animated GIF/WebP, folders of frames, and sprite sheets, usable as backgrounds, characters or overlays
  (rain, snow, sparkles, explosions)

**For sharing**
- A Debian/Ubuntu **.deb package** with a menu entry, icon and man page
- **Export Game** builds a folder anyone can play, with optional single-executable instructions
- Expressions are evaluated safely. A downloaded story can never run code on your computer

---

## Installing

OpenNovella needs **Python 3.9 or newer**.

### Windows and macOS

1. Install Python from <https://www.python.org/downloads/>. On Windows, tick **"Add Python to PATH"**.
2. Download or clone this folder, open a terminal in it, and run:

   ```bash
   python -m pip install -r requirements.txt
   ```

3. Start the editor by double-clicking **`start_editor.py`**, or run:

   ```bash
   python start_editor.py
   ```

### Debian / Ubuntu (.deb package)

Download or build `opennovella_0.1.0_all.deb` (see [Building the .deb](#building-the-deb)), then:

```bash
sudo apt install ./opennovella_0.1.0_all.deb
```

apt pulls in everything it needs (Python, pygame, Pillow, tkinter). OpenNovella then shows up in your
applications menu, and the `opennovella` command is available in the terminal (`man opennovella`).
The first time you open the demo from the welcome screen, it is copied to `~/OpenNovella/` so you can
edit it. To uninstall: `sudo apt remove opennovella`.

### Linux (from source)

The editor uses tkinter, which some Linux distributions package separately:

```bash
sudo apt install python3-tk          # Debian / Ubuntu / Mint
sudo dnf install python3-tkinter     # Fedora
python3 -m pip install -r requirements.txt
python3 start_editor.py
```

### Installing as a command (optional)

```bash
python -m pip install .
opennovella            # opens the editor
```

---

## Your first visual novel in 5 minutes

1. **Start the editor** and click **New Project**. Give the project a title and choose a folder.
   You'll get a small starter story to learn from.
2. Press **F5** (or click **▶ Play**) to see the starter story running.
3. Click the **start** scene on the left. Its commands appear in the middle and run from top to bottom.
4. In the **Quick dialogue** bar at the bottom, choose a speaker, type a line and press **Enter**.
   Keep typing; each Enter adds another line.
5. Click **Characters** to add your cast. Give each person a display name, a name color and images for
   their expressions, such as `default`, `happy` and `sad`.
6. Click **+ Add command → Story → Choice** to let the player decide something. For each option, pick
   **"+ New scene…"** under *Goes to scene* to create the branch.
7. Press **F7** to check for mistakes, then **F8** to see your story map.

Want to see a finished example? Click **Open the Demo** on the welcome screen. *The Lantern
Festival* is a short story with three endings that uses most of the features. To give the demo real
artwork instead of placeholders, run this once:

```bash
python examples/demo/make_art.py
```

---

## How stories work

| Concept | What it is |
|---|---|
| **Project** | A folder containing `story.json` and your `images/`, `audio/` and `fonts/` folders. |
| **Scene** | A named list of commands, like a chapter or a single moment. The ★ scene is where the game begins. |
| **Command** | One instruction: a line of dialogue, a background change, a choice, a sound, and so on. |
| **Character** | A speaker with a display name, a name color and a set of *expression* images. |
| **Variable** | A remembered value (number, true/false, or text) that tracks the player's journey. |

Commands run from top to bottom. A **Jump** or **Choice** moves to another scene. If a scene runs out of
commands, the story ends, and Check Story will warn you about it.

Variables can appear inside any dialogue: `"You have {gold} gold coins."`

---

## Branching paths

There are three ways to branch:

1. **Choice**: buttons for the player. Each option can:
   - **go to** a scene, or leave it blank to continue in the current scene
   - **change variables** when picked, e.g. `courage += 1; met_alice = true`
   - **appear only if** a condition is true, e.g. `friendship >= 2`
2. **If / Else**: jumps based on a condition, with no player input:
   `If  helped_tomas and friendship >= 3  → ending_best, else → ending_good`
3. **Jump**: always go to another scene. Use it to bring branches back together.

A common pattern is to **branch and merge**. Each option leads to a short scene of its own, and each of
those scenes ends with a Jump back to a shared scene. Variables carry the player's choices forward, and
an If at the end picks the ending.

### Conditions

| You write | Meaning |
|---|---|
| `courage >= 3` | at least 3 |
| `met_alice` | the flag is true |
| `not angry` or `!angry` | the flag is false |
| `gold > 10 and has_key` | both are true (`&&` works too) |
| `ending == "secret" or score > 99` | either one is true (`\|\|` works too) |
| `name == "Sam"` | text comparison (use quotes) |

You can also use `+ - * /`, `min()`, `max()`, `abs()`, `round()` and `len()`. A variable that has never
been set counts as `0` (false).

---

## Command reference

| Command | What it does | Main settings |
|---|---|---|
| **Say** | A line of dialogue. Leave the character blank for narration. | character, expression, text |
| **Choice** | Buttons that branch the story | prompt, options (text, goes to, only if, changes) |
| **Jump** | Go to another scene | scene |
| **If / Else** | Branch on a condition | condition, if-true scene, otherwise scene |
| **Set Variable** | Change a variable | variable, `=` `+=` `-=` `*=` `/=`, value |
| **End** | Finish the story and return to the title | ending text, ending name |
| **Note** | A comment for yourself. Players never see it. | text |
| **Background** | Change the background image or color | image, color, transition, duration, remove characters |
| **Show Character** | Put a character or prop on screen, or change their expression | character, expression, custom image, position, transition, effect |
| **Hide Character** | Remove someone from the screen | character, transition |
| **Move Character** | Slide a character to a new position | character, position, duration |
| **Screen Effect** | shake, flash, fade_out, fade_in, tint, clear_tint | color, duration, wait |
| **Play Animation** | Play an animation over the scene | image, position, times to play, fps, wait, name |
| **Stop Animation** | Stop a looping animation | name (blank = all) |
| **Play Music** | Start background music | file, loop, fade in |
| **Stop Music** | Stop the music | fade out |
| **Play Sound** | Play a sound effect once | file |
| **Wait** | Pause for a moment | seconds |

**Positions:** `far_left`, `left`, `center`, `right`, `far_right`
**Entrances:** `none`, `fade`, `slide_left`, `slide_right`, `slide_up`, `zoom`
**Exits:** `none`, `fade`, `slide_left`, `slide_right`, `slide_down`, `zoom`
**Character effects:** `bounce`, `shake`, `jump` (play once), `float`, `pulse` (keep going)

---

## Images and animations

Put your files anywhere. When you pick one in the editor, it is **copied into your project's `images/`
folder automatically**, so the project stays self-contained.

| What | Formats | Tips |
|---|---|---|
| **Backgrounds** | PNG, JPG, WebP, BMP | Stretched to the screen size, so use the same aspect ratio (16:9 at 1280×720 by default). |
| **Characters** | PNG with transparency | Art taller than the screen is scaled down to fit. Characters stand on the bottom edge. |
| **Animated images** | Animated **GIF**, **WebP** or **APNG** | They loop automatically and work anywhere an image does. |
| **Frame folders** | A folder of `001.png`, `002.png`, … | Choose it with **Frames folder…**. Add a `fps.txt` file containing a number (e.g. `16`) to set the speed. |
| **Sprite sheets** | `name_stripN.png` | N frames side by side in one image, e.g. `explosion_strip8.png`. |

How to use animation:

- **Animated backgrounds**: pick an animated GIF or frame folder in a Background command.
- **Animated characters**: give an expression an animated image, such as a blinking GIF.
- **Overlays** such as rain, snow or sparkles: use **Play Animation** with *Times to play* set to `0`
  to loop forever, then **Stop Animation** to remove it. Looping overlays are kept in save files.
- **Movement**: the transitions, *Move Character* and the character and screen effects listed above.

If an image is missing, OpenNovella never crashes. It draws a labelled placeholder instead, and
Check Story lists every missing file.

---

## Audio

Music and sounds can be **OGG** (recommended), **MP3** or **WAV**. Music fades in and out smoothly, and
players can set the music and sound volumes separately in Settings. You can also set title screen
music in **Settings**. If the computer has no sound device, the game simply plays silently.

---

## Playing: controls for players

| Action | Keys / mouse |
|---|---|
| Next line | Left click, Space, Enter, scroll down |
| Game menu | Esc, right click |
| History | H, scroll up |
| Auto mode | A |
| Skip | Hold Ctrl, or Tab to toggle |
| Hide text box | V, middle click |
| Quick save / load | F5 / F9 |
| Fullscreen | F11, Alt+Enter |
| Pick a choice | Click, or keys 1–9 |

The window can be resized freely, and the game scales to fit. Save files are kept in the project's
`saves/` folder.

---

## Sharing your game

**File → Export Game…** (or `opennovella export PROJECT OUTPUT_FOLDER`) creates a folder like this:

```
My Game (game)/
├── play.py          ← players run this
├── README.txt       ← instructions for players
├── game/            ← your story and assets
└── opennovella/     ← the engine (without the editor)
```

Players need Python with `pygame` and `Pillow` installed. If you'd rather give them a single
program to run, the exported `README.txt` includes a ready-to-paste
[PyInstaller](https://pyinstaller.org) command.

### Building the .deb

On any Debian or Ubuntu machine:

```bash
sh packaging/build_deb.sh
```

This writes `dist/opennovella_0.1.0_all.deb`. The package version is read from `__version__` in
`opennovella/__init__.py`, which is the only place the version number is set. The package is
architecture-independent (`all`) and contains the engine, the editor, the demo with its artwork
pre-generated, a desktop entry, an icon and a man page.

---

## Command line

```bash
python -m opennovella                         # open the editor
python -m opennovella edit  PROJECT           # open the editor with a project
python -m opennovella play  PROJECT           # play (add --scene NAME, --fullscreen)
python -m opennovella new   FOLDER --title "My Story" --author "Me"
python -m opennovella check PROJECT           # list problems (exit code 1 if errors)
python -m opennovella export PROJECT OUTPUT   # make a shareable game folder
python -m opennovella bugreport [PROJECT]     # print info for a bug report
```

`PROJECT` can be a project folder or the path to its `story.json`.

---

## The story file format (advanced)

Everything lives in `story.json`. Here is a small but complete example:

```json
{
  "format": 1,
  "title": "Tiny Tale",
  "author": "You",
  "resolution": [1280, 720],
  "start_scene": "start",
  "variables": { "brave": false },
  "characters": {
    "kai": { "name": "Kai", "color": "#8fd3ff",
             "images": { "default": "images/kai.png", "happy": "images/kai_happy.gif" } }
  },
  "scenes": {
    "start": { "notes": "", "commands": [
      { "type": "background", "image": "images/forest.png", "transition": "fade", "duration": 1 },
      { "type": "show", "character": "kai", "position": "center", "transition": "slide_up" },
      { "type": "say", "character": "kai", "text": "Do we go into the cave?" },
      { "type": "choice", "prompt": "", "options": [
        { "text": "Yes!", "target": "cave", "condition": "", "effects": "brave = true" },
        { "text": "No way.", "target": "home", "condition": "", "effects": "" }
      ]}
    ]},
    "cave": { "commands": [
      { "type": "say", "character": "kai", "expression": "happy", "text": "So brave!" },
      { "type": "end", "text": "The End", "ending": "Cave Ending" }
    ]},
    "home": { "commands": [ { "type": "end", "text": "Safe at home." } ] }
  }
}
```

You can leave out any field; missing fields use their defaults. The editor keeps any extra fields
you add by hand. Each command's fields are defined in `COMMAND_TYPES` in `opennovella/story.py`.

The engine can also be used from Python:

```python
from opennovella import load_story
from opennovella.engine import Engine

engine = Engine(load_story("examples/demo"))
engine.start()
event = engine.step()          # e.g. Event(type="say", ...)
print(event["name"], event["text"])
```

---

## Project layout

```
OpenNovella/
├── start_editor.py           double-click to open the editor
├── opennovella/
│   ├── story.py              data model + command definitions
│   ├── engine.py             story interpreter (no graphics, easy to test)
│   ├── expressions.py        safe conditions, variables and {interpolation}
│   ├── validate.py           "Check Story"
│   ├── player.py             the pygame game window, menus, saves
│   ├── assets.py             images, animations, fonts, sounds, placeholders
│   ├── export.py             "Export Game"
│   ├── bugreport.py          system info for bug reports
│   └── editor/               tkinter editor (app, dialogs, story map, widgets)
├── examples/demo/            "The Lantern Festival" demo (+ make_art.py)
├── packaging/                build_deb.sh + Debian files (control, desktop entry, icon, man page)
├── tests/                    pytest suite
├── BUG_REPORT.md             how to report a bug
└── .github/ISSUE_TEMPLATE/   bug report template for GitHub
```

---

## Troubleshooting

| Problem | Fix |
|---|---|
| `No module named 'tkinter'` | Linux: `sudo apt install python3-tk`. Windows/macOS: reinstall Python from python.org. |
| `No module named 'pygame'` | `python -m pip install pygame Pillow` |
| Characters show as coloured silhouettes | That's a placeholder: the image is missing. Add it in **Characters** and press F7 to see which files are missing. |
| Animated GIF doesn't move | Make sure Pillow is installed (`python -m pip install Pillow`). |
| No sound | Check the volumes in the game's Settings screen. OGG is the most reliable format. |
| Game says "the story hit a problem" | Open the editor and press **F7**. The problem will be listed there. |
| Game crashed | A `crash.log` is written to the project's `saves/` folder. Please [report it](#reporting-bugs). |

---

## Reporting bugs

Found a problem? Please see **[BUG_REPORT.md](BUG_REPORT.md)**. In short, use **Help → Report a Bug…** in
the editor, or run `python -m opennovella bugreport`. Either one collects your system details for you.

---

## Developing OpenNovella

```bash
python -m pip install -e ".[dev]"
python -m pytest                      # engine, story, player (headless) and editor tests
xvfb-run python -m pytest             # include the editor tests on a headless Linux machine
```

The player runs off-screen with `SDL_VIDEODRIVER=dummy`, so the whole game can be tested
without a window. The tests do this to play through every ending of the demo.

---

## Credits and license

**OpenNovella was created by Shawn Rapaz and Claude Code.**

Released under the **GNU General Public License v3.0**. See [LICENSE](LICENSE). Stories and art you make
with OpenNovella belong to you. Games exported with OpenNovella include a copy of the engine, which is
covered by the GPL.
