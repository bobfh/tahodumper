"""
Build script for packaging TahoCard Dumper into a standalone Windows executable (.exe)
using PyInstaller.
"""

import os
import sys
import subprocess
import shutil

def build():
    root_dir = os.path.dirname(os.path.abspath(__file__))
    dist_dir = os.path.join(root_dir, "dist")
    build_dir = os.path.join(root_dir, "build")

    print("[*] Starting PyInstaller build for TahoCard Dumper...")

    # PyInstaller arguments
    cmd = [
        sys.executable,
        "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--name", "TahoDumper",
        "--collect-all", "smartcard",
        "--hidden-import", "smartcard",
        "--hidden-import", "smartcard.pcsc",
        "--hidden-import", "smartcard.pcsc.PCSCExceptions",
        "--hidden-import", "smartcard.pcsc.PCSCReader",
        "--hidden-import", "smartcard.pcsc.PCSCCardConnection",
        "--hidden-import", "smartcard.reader",
        "--hidden-import", "smartcard.reader.ReaderFactory",
        "--hidden-import", "smartcard.System",
        "--hidden-import", "tkinter",
        "--hidden-import", "tkinter.ttk",
        "--hidden-import", "tkinter.messagebox",
        "--hidden-import", "tkinter.scrolledtext",
        os.path.join(root_dir, "main.py")
    ]

    print(f"[*] Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, cwd=root_dir)
    if result.returncode != 0:
        print("[-] Build failed!")
        sys.exit(result.returncode)

    exe_path = os.path.join(dist_dir, "TahoDumper.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print(f"[+] Build successful! Output: {exe_path} ({size_mb:.2f} MB)")
    else:
        print("[-] Output executable not found!")

if __name__ == "__main__":
    build()
