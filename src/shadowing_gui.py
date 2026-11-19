# -*- coding: utf-8 -*-
"""Small window to build a lesson MP3 without the command line (also the entry point of the Windows .exe).

Type or paste the lesson and the speakers in the two boxes (or load them from the same files run_lesson.py
uses), choose the engine and press Build. The boxes start with a small example.
Like run_lesson.py it does not change google_shadowing_app.py or edge_tts_shadowing_app.py: it sets their
LESSON_DATA, SPEAKERS, OUTPUT_NAME (and, in the .exe, OUTPUT_DIR and GOOGLE_API_KEY) and uses run_lesson.py
for the parts of long lessons and the timeline JSON.

    python src/shadowing_gui.py
    python src/shadowing_gui.py --selftest   # no window: build the example with Edge-TTS, exit code 0 = OK
"""
import ast
import asyncio
import importlib
import json
import os
import queue
import re
import sys
import tempfile
import threading
import traceback
from pathlib import Path

FROZEN = getattr(sys, "frozen", False)
# In the .exe: output folder, ffmpeg.exe and ffprobe.exe are next to the .exe
APP_DIR = Path(sys.executable).parent if FROZEN else Path(__file__).resolve().parent.parent
if FROZEN:
    os.environ["PATH"] = str(APP_DIR) + os.pathsep + os.environ.get("PATH", "")
    if sys.platform == "win32":
        # pydub runs ffmpeg for every segment; without this every call flashes a console window.
        # Must happen before pydub is imported (pydub.utils does 'from subprocess import Popen').
        import subprocess

        class _NoWindowPopen(subprocess.Popen):
            def __init__(self, *args, **kwargs):
                kwargs.setdefault("creationflags", subprocess.CREATE_NO_WINDOW)
                super().__init__(*args, **kwargs)

        subprocess.Popen = _NoWindowPopen
SETTINGS_FILE = Path(os.environ.get("APPDATA", Path.home())) / "ShadowingApp" / "settings.json"
ENGINES = {"Edge-TTS (free)": "edge", "Google Chirp 3 HD (API key)": "google"}

EXAMPLE_LESSON = """# Example lesson: one line = one row, every segment starts with a speaker tag.
# Lines starting with # are skipped.
e: یادم می‌آید a: ik herinner me
b: Ik herinner me haar naam. e: اسمش یادم می‌آید.
e: هدیه a: het cadeau
b: Ik heb een cadeau voor je. e: یک هدیه برایت دارم.
"""
EXAMPLE_SPEAKERS = """SPEAKERS = {
    "a": {"language": "dutch",   "voice": "male1",   "repeats": 2, "speed": 0.8, "silence_ratio": 1.0},
    "b": {"language": "dutch",   "voice": "female1", "repeats": 1, "speed": 0.8, "silence_ratio": 1.0},
    "e": {"language": "persian", "voice": "female1", "repeats": 1, "speed": 1.0, "silence_ratio": 1.2},
}
"""


# ---------------------------------------------------------------- settings (remembered API key, last folder)
def load_settings() -> dict:
    try:
        return json.loads(SETTINGS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_settings(settings: dict) -> None:
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=1), encoding="utf-8")


def default_api_key(settings: dict) -> str:
    """Remembered key, else google_api_key.txt (project root or next to the .exe), else GOOGLE_API_KEY."""
    if settings.get("api_key"):
        return settings["api_key"]
    for folder in (APP_DIR, APP_DIR.parent):
        f = folder / "google_api_key.txt"
        if f.exists():
            return f.read_text(encoding="utf-8").strip()
    return os.getenv("GOOGLE_API_KEY", "")


# ---------------------------------------------------------------- building (no GUI code, can be tested alone)
def load_engine(engine: str):
    import run_lesson
    return run_lesson, importlib.import_module(run_lesson.ENGINES[engine])


def check_google_key(key: str) -> str:
    """Synthesize one word; return "" if the key works, else the error message."""
    _, app = load_engine("google")
    app.GOOGLE_API_KEY = key
    path = Path(tempfile.gettempdir()) / "shadowing_key_test.mp3"
    try:
        app.synthesize_google_tts_sync("test", app.VOICE_PRESETS["dutch"]["female1"], 1.0, path)
        return ""
    except Exception as e:
        return str(e)
    finally:
        path.unlink(missing_ok=True)


def parse_speakers(text: str) -> dict:
    """'SPEAKERS = {...}' (as in a speakers file) or only '{...}'."""
    text = text.strip()
    if not text.startswith("{"):
        text = text.split("=", 1)[1].strip() if "=" in text else text
    try:
        speakers = ast.literal_eval(text)
    except Exception as e:
        raise ValueError(f"The speakers box is not a valid SPEAKERS = {{...}} block ({e}).")
    if not isinstance(speakers, dict) or not speakers:
        raise ValueError("The speakers box must contain SPEAKERS = { \"a\": {...}, ... }.")
    return speakers


def build(engine: str, lesson_text: str, speakers_text: str, name: str, api_key: str = "") -> Path:
    """Build the lesson like run_lesson.py does. Returns the output folder."""
    run_lesson, app = load_engine(engine)
    app.LESSON_DATA = lesson_text.strip()
    app.SPEAKERS = parse_speakers(speakers_text)
    if not app.parse_lesson_lines(app.LESSON_DATA):
        raise ValueError("The lesson box has no line with a speaker tag (e.g. a: Hallo).")
    app.OUTPUT_NAME = name
    if FROZEN:
        app.OUTPUT_DIR = APP_DIR / "output"
    if engine == "google":
        app.GOOGLE_API_KEY = api_key
    for row in app.parse_lesson_lines(app.LESSON_DATA):  # unknown tags: stop before anything is synthesized
        for tag, _ in row:
            app.resolve_speaker(tag)
    # run_lesson.split_export replaces two functions of the app; put them back afterwards, so a second
    # build in the same window does not wrap them twice
    originals = app.normalize_and_export, app.adaptive_silence
    run_lesson.app = app
    try:
        run_lesson.split_export(name)
        asyncio.run(app.build_lesson())
    finally:
        app.normalize_and_export, app.adaptive_silence = originals
    return app.OUTPUT_DIR


# ---------------------------------------------------------------- window
class QueueWriter:
    """stdout / stderr replacement: everything the apps print goes to the log box."""

    encoding = "utf-8"

    def __init__(self, q):
        self.q = q

    def write(self, text):
        self.q.put(text)

    def flush(self):
        pass


def main() -> None:
    import tkinter as tk
    from tkinter import filedialog, messagebox, scrolledtext, ttk

    settings = load_settings()
    log_queue = queue.Queue()
    sys.stdout = sys.stderr = QueueWriter(log_queue)

    root = tk.Tk()
    root.title("Shadowing lesson builder")
    root.geometry("900x780")
    frm = ttk.Frame(root, padding=10)
    frm.pack(fill="both", expand=True)
    frm.columnconfigure(1, weight=1)

    name_var = tk.StringVar(value=settings.get("name", "my_lesson"))
    engine_var = tk.StringVar(value=settings.get("engine", next(iter(ENGINES))))
    key_var = tk.StringVar(value=default_api_key(settings))
    remember_var = tk.BooleanVar(value=bool(settings.get("api_key")))
    last_output = {"dir": None}

    def text_box(row, label, height, content):
        """Label + 'Load from file…' + 'Example' buttons above a text box; returns the box."""
        head = ttk.Frame(frm)
        head.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        ttk.Label(head, text=label).pack(side="left")
        box = scrolledtext.ScrolledText(frm, height=height, font=("Consolas", 10), undo=True)
        box.grid(row=row + 1, column=0, columnspan=3, sticky="nsew")
        box.insert("1.0", content)
        return head, box

    def load_file(box, title, set_name=False):
        path = filedialog.askopenfilename(title=title, initialdir=settings.get("folder", str(APP_DIR)),
                                          filetypes=[("Text files", "*.txt"), ("All files", "*.*")])
        if not path:
            return
        box.delete("1.0", "end")
        box.insert("1.0", Path(path).read_text(encoding="utf-8"))
        settings["folder"] = str(Path(path).parent)
        if set_name:  # output name = lesson file name
            name_var.set(re.sub(r"[^\w\-]", "_", Path(path).stem))

    def reset(box, content):
        box.delete("1.0", "end")
        box.insert("1.0", content)

    row = 0
    head, lesson_box = text_box(row, "Lesson  (type, paste, or load a file)", 9,
                                settings.get("lesson_text", EXAMPLE_LESSON))
    ttk.Button(head, text="Example", command=lambda: reset(lesson_box, EXAMPLE_LESSON)).pack(side="right")
    ttk.Button(head, text="Load from file…",
               command=lambda: load_file(lesson_box, "Lesson text", True)).pack(side="right", padx=5)
    frm.rowconfigure(row + 1, weight=2)
    row += 2
    head, speakers_box = text_box(row, "Speakers  (SPEAKERS = {...})", 6,
                                  settings.get("speakers_text", EXAMPLE_SPEAKERS))
    ttk.Button(head, text="Example", command=lambda: reset(speakers_box, EXAMPLE_SPEAKERS)).pack(side="right")
    ttk.Button(head, text="Load from file…",
               command=lambda: load_file(speakers_box, "SPEAKERS = {...} file")).pack(side="right", padx=5)
    frm.rowconfigure(row + 1, weight=1)
    row += 2
    ttk.Label(frm, text="Output name").grid(row=row, column=0, sticky="w", pady=(8, 3))
    ttk.Entry(frm, textvariable=name_var).grid(row=row, column=1, sticky="ew", padx=5, pady=(8, 3))
    row += 1
    ttk.Label(frm, text="Engine").grid(row=row, column=0, sticky="w", pady=3)
    ttk.Combobox(frm, textvariable=engine_var, values=list(ENGINES), state="readonly").grid(
        row=row, column=1, sticky="w", padx=5)
    row += 1
    ttk.Label(frm, text="Google API key").grid(row=row, column=0, sticky="w", pady=3)
    key_entry = ttk.Entry(frm, textvariable=key_var, show="•")
    key_entry.grid(row=row, column=1, sticky="ew", padx=5)
    remember = ttk.Checkbutton(frm, text="Remember", variable=remember_var)
    remember.grid(row=row, column=2, sticky="w")
    row += 1

    buttons = ttk.Frame(frm)
    buttons.grid(row=row, column=0, columnspan=3, sticky="w", pady=8)
    build_btn = ttk.Button(buttons, text="Build lesson")
    build_btn.pack(side="left")
    open_btn = ttk.Button(buttons, text="Open output folder", state="disabled",
                          command=lambda: os.startfile(last_output["dir"]))
    open_btn.pack(side="left", padx=8)
    row += 1

    log = scrolledtext.ScrolledText(frm, height=10, font=("Consolas", 9))
    log.grid(row=row, column=0, columnspan=3, sticky="nsew")
    frm.rowconfigure(row, weight=1)

    def engine_changed(*_):
        state = "normal" if ENGINES[engine_var.get()] == "google" else "disabled"
        key_entry.configure(state=state)
        remember.configure(state=state)

    engine_var.trace_add("write", engine_changed)
    engine_changed()

    def poll_log():
        while not log_queue.empty():
            log.insert("end", log_queue.get())
            log.see("end")
        root.after(100, poll_log)

    def remember_settings():
        settings.update(lesson_text=lesson_box.get("1.0", "end-1c"), speakers_text=speakers_box.get("1.0", "end-1c"),
                        name=name_var.get(), engine=engine_var.get())
        if remember_var.get() and key_var.get().strip():
            settings["api_key"] = key_var.get().strip()
        else:
            settings.pop("api_key", None)
        try:
            save_settings(settings)
        except Exception as e:
            print(f"[Warning] settings not saved: {e}\n")

    def worker(engine, lesson, speakers, name, key):
        try:
            if engine == "google":
                print("Checking the Google API key…\n")
                error = check_google_key(key)
                if error:
                    root.after(0, lambda: messagebox.showerror(
                        "Google API key", "The key does not work:\n\n" + error[:600] +
                        "\n\nCheck the key, and that the Cloud Text-to-Speech API and billing are enabled."))
                    return
                print("Key OK.\n")
            out_dir = build(engine, lesson, speakers, name, key)
            last_output["dir"] = str(out_dir)
            root.after(0, lambda: (open_btn.configure(state="normal"),
                                   messagebox.showinfo("Done", f"The lesson is ready in\n{out_dir}")))
        except Exception as e:
            traceback.print_exc()
            root.after(0, lambda e=e: messagebox.showerror("Error", str(e)[:800]))
        finally:
            root.after(0, lambda: build_btn.configure(state="normal"))

    def start_build():
        lesson, speakers = lesson_box.get("1.0", "end-1c"), speakers_box.get("1.0", "end-1c")
        name = name_var.get().strip()
        engine = ENGINES[engine_var.get()]
        key = key_var.get().strip()
        problems = []
        if not lesson.strip():
            problems.append("The lesson box is empty.")
        else:
            try:
                parse_speakers(speakers)
            except ValueError as e:
                problems.append(str(e))
        if not re.fullmatch(r"[\w\-]+", name):
            problems.append("Output name: only letters, digits, _ and -.")
        if engine == "google" and not key:
            problems.append("Google needs an API key (or choose Edge-TTS).")
        if problems:
            messagebox.showwarning("Missing input", "\n".join(problems))
            return
        remember_settings()
        log.delete("1.0", "end")
        build_btn.configure(state="disabled")
        threading.Thread(target=worker, args=(engine, lesson, speakers, name, key), daemon=True).start()

    build_btn.configure(command=start_build)
    poll_log()
    root.mainloop()


def selftest() -> int:
    """Build the example with Edge-TTS without a window (used by the GitHub build to test the .exe).
    The log is written to <output folder>/selftest.log."""
    import io
    log = io.StringIO()
    sys.stdout = sys.stderr = log
    code = 1
    import shutil
    print(f"ffmpeg: {shutil.which('ffmpeg')}  ffprobe: {shutil.which('ffprobe')}")
    try:
        out_dir = build("edge", EXAMPLE_LESSON, EXAMPLE_SPEAKERS, "selftest")
        files = sorted(Path(out_dir).glob("selftest_*.mp3"))
        jsons = sorted(Path(out_dir).glob("selftest_*.json"))
        print(f"\nSELFTEST {'OK' if files and jsons else 'FAILED'}: {files[-1:]} {jsons[-1:]}")
        code = 0 if files and jsons else 1
    except Exception:
        traceback.print_exc()
        out_dir = APP_DIR / "output"
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / "selftest.log").write_text(log.getvalue(), encoding="utf-8")
    return code


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(selftest())
    main()
