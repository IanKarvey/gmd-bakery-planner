"""Builds the no-install version of the program.

Run it by double-clicking build_exe.bat. When it finishes you get:

    dist\GMD Bakery Planner\GMD Bakery Planner.exe

Copy (or zip) that whole folder to any Windows laptop. It does NOT need Python installed.
"""
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.environ.get("GMD_BUILD_DIR", HERE)  # where dist\ and build\ go (default: next to this file)
os.chdir(HERE)
NAME = "GMD Bakery Planner"

try:
    import PyInstaller.__main__ as pyinstaller
except ImportError:
    print("Installing the packaging tool (PyInstaller), one time only...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "pyinstaller"])
    import PyInstaller.__main__ as pyinstaller

from PIL import Image  # installed together with matplotlib

logo = next((os.path.join(HERE, f + ext) for f in ("GMD v2", "GMD logo")
             for ext in (".jpg", ".jpeg", ".png") if os.path.exists(os.path.join(HERE, f + ext))), None)

build_dir = os.path.join(OUT, "build")
os.makedirs(build_dir, exist_ok=True)
args = ["bakery_planner.py", "--noconfirm", "--clean", "--windowed", "--name", NAME,
        "--distpath", os.path.join(OUT, "dist"), "--workpath", os.path.join(build_dir, "work"),
        "--specpath", build_dir]
if logo:
    art = Image.open(logo).convert("RGB")
    side = max(art.size)
    square = Image.new("RGB", (side, side), "white")
    square.paste(art, ((side - art.width) // 2, (side - art.height) // 2))
    icon = os.path.join(build_dir, "icon.ico")
    square.resize((256, 256), Image.LANCZOS).save(icon, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
    args += ["--icon", icon, "--add-data", f"{logo}{os.pathsep}."]
pyinstaller.run(args)
print(f"\nDone. Share this folder:  {os.path.join(OUT, 'dist', NAME)}   (the program is {NAME}.exe inside it)")
