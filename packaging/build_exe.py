#!/usr/bin/env python3
"""Build dist/OpenNovella-<version>.exe, a single-file Windows program (editor + player).

Run it with a Windows Python that has the build tools installed:

    python -m pip install pyinstaller pygame Pillow
    python packaging/build_exe.py

On Linux, packaging/build_exe_wine.sh runs this script with Windows Python under Wine.
"""

import os
import re
import shutil
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WORK = os.path.join(ROOT, "build", "exe")
DIST = os.path.join(ROOT, "dist")
ICON_DIR = os.path.join(ROOT, "opennovella", "icons")
DEMO = os.path.join(ROOT, "examples", "demo")

VERSION_INFO = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Shawn Rapaz and Claude Code'),
      StringStruct('FileDescription', 'OpenNovella'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', 'OpenNovella'),
      StringStruct('LegalCopyright', 'GPL-3.0-or-later'),
      StringStruct('OriginalFilename', 'OpenNovella.exe'),
      StringStruct('ProductName', 'OpenNovella'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def read_version() -> str:
    with open(os.path.join(ROOT, "opennovella", "__init__.py"), encoding="utf-8") as fh:
        return re.search(r'^__version__ = "(.+)"$', fh.read(), re.M).group(1)


def make_icon(path: str) -> None:
    from PIL import Image
    sizes = (16, 32, 48, 64, 128, 256)
    images = [Image.open(os.path.join(ICON_DIR, f"opennovella-{s}.png")).convert("RGBA") for s in sizes]
    images[-1].save(path, sizes=[(s, s) for s in sizes], append_images=images[:-1])


def main() -> int:
    if sys.platform != "win32":
        print("Run this with a Windows Python (on Linux: packaging/build_exe_wine.sh).", file=sys.stderr)
        return 1
    version = read_version()
    print(f"Building OpenNovella {version} for Windows ...")
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK)

    # The demo art is generated, not stored in git
    if not os.path.isfile(os.path.join(DEMO, "images", "bg_village.png")):
        env = dict(os.environ, SDL_VIDEODRIVER="dummy", PYGAME_HIDE_SUPPORT_PROMPT="1")
        subprocess.run([sys.executable, os.path.join(DEMO, "make_art.py")], check=True, env=env,
                       stdout=subprocess.DEVNULL)
        print("  demo artwork generated")

    icon = os.path.join(WORK, "opennovella.ico")
    make_icon(icon)
    nums = tuple(int(n) for n in (version.split(".") + ["0"] * 4)[:4])
    version_file = os.path.join(WORK, "version_info.txt")
    with open(version_file, "w", encoding="utf-8") as fh:
        fh.write(VERSION_INFO.format(nums=nums, version=version))

    # Copy the demo without player saves so they don't end up in the .exe
    demo_copy = os.path.join(WORK, "demo")
    shutil.copytree(DEMO, demo_copy, ignore=shutil.ignore_patterns("saves", "__pycache__", "*.pyc"))
    # "Export Game" copies the engine's .py files next to the exported game, so ship the source too
    pkg_copy = os.path.join(WORK, "opennovella")
    shutil.copytree(os.path.join(ROOT, "opennovella"), pkg_copy,
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    name = f"OpenNovella-{version}"
    import PyInstaller.__main__
    PyInstaller.__main__.run([
        os.path.join(ROOT, "start_editor.py"),
        "--name", name, "--onefile", "--windowed", "--noconfirm", "--clean",
        "--icon", icon, "--version-file", version_file,
        "--distpath", DIST, "--workpath", os.path.join(WORK, "pyinstaller"), "--specpath", WORK,
        "--add-data", f"{pkg_copy}{os.pathsep}opennovella",
        "--add-data", f"{demo_copy}{os.pathsep}examples/demo",
        "--add-data", f"{os.path.join(ROOT, 'README.md')}{os.pathsep}.",
        "--add-data", f"{os.path.join(ROOT, 'BUG_REPORT.md')}{os.pathsep}.",
        "--collect-submodules", "opennovella",
    ])
    print(f"Done: {os.path.join(DIST, name + '.exe')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
