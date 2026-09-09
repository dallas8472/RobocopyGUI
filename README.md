# Robocopy GUI

A lightweight graphical interface for the Windows tool `robocopy`, implemented in Python with PyQt6.

**In short:** Simple operation for incremental copies, mirroring, comparisons and selective deletion – including task management for recurring jobs that can be run individually or as a queue, one after another.

## Features

- **Copy actions:** Structure (folders only), data update (incremental), mirror (including deleting in the target), purge (delete without copying) and compare (dry run, `/L`)
- **Options:** file-age filter, ACL/permission copy (`/COPYALL`, requires administrator rights), verbose log, optional log file
- **Special delete:** remove files in the target folder by modification date or name pattern – they go to the **Windows recycle bin** (`send2trash`), not permanently deleted
- **Task management** (menu *Tasks → Manage tasks...*): a separate window to create, edit and reorder (drag & drop) saved jobs; select multiple tasks and run them automatically one after another as a **queue** (an error in one task doesn't stop the queue; you get a success/failure summary at the end)
- **Groups:** save combinations of tasks that are needed together under one name – one click selects all matching tasks again, without picking them individually
- **Light/dark theme** (menu *View*), the choice is saved and restored on the next start
- **Language:** UI language is picked automatically from the system locale at startup (German or English); can be overridden via the menu, takes effect after a restart
- **Admin mode:** restart with administrator rights directly from the app, needed for ACL copying
- Checks at startup whether `robocopy.exe` can be found
- Freely resizable window with a sensible minimum size; a running job can be cancelled at any time

**Files in the repo:**
- `RobocopyGUI.py` – main application (source code)
- `logo.png`, `RobocopyGUI.ico` – app logo / icon
- `RobocopyGUI.spec` – PyInstaller spec (also bundles the required icon font subset from `qtawesome`)
- `dist/RobocopyGUI.exe` – built single-file executable (if present)
- `_create_ico.py` – generates `RobocopyGUI.ico` from `logo.png` (requires Pillow)

**Requirements (development)**
- Windows
- Python 3.10+ (tested here with 3.14)
- PyQt6
- qtawesome (icons in the UI)
- send2trash (recycle bin instead of permanent deletion)
- Pillow (for icon generation)
- PyInstaller (for building the exe)

Installing dependencies (dev environment):

```powershell
python -m pip install -r requirements.txt
# or individually
python -m pip install PyQt6 qtawesome send2trash pillow pyinstaller
```

## Build

Recommended: build via the provided spec file, since it specifically embeds
the required icon font subset from `qtawesome` (a direct `pyinstaller` call
without the spec file doesn't do this, and the icons would be missing from
the exe):

```powershell
python -m PyInstaller --clean RobocopyGUI.spec
```

The result is written to `dist/RobocopyGUI.exe`.

## Usage

1. Select the source and target folders (or drag & drop them onto the fields).
2. Set options (file age, ACLs, verbose, log file) and click an action under
   "Execution".
3. For recurring jobs: use *Tasks → Manage tasks...* to create a task with a
   name, action, source/target and options. Select multiple tasks
   (Ctrl/Shift-click) and "Start queue" runs them one after another.
4. Select tasks that are frequently run together and save them under
   "Groups" with a name – "Apply" selects them again with one click.

Security / notes:
- Don't store private keys or PFX files in the repo. If certificates are used for signing, keep them outside the repo and add them to `.gitignore`.
- `robocopy` can delete files (e.g. with Mirror/Purge) – these deletions go through robocopy directly and do **not** end up in the recycle bin. Check paths carefully, especially with Mirror.
- Configuration (recently used paths, saved tasks) is stored under `%APPDATA%\RobocopyGUI\`.

License: [MIT](LICENSE) – free to use, modify and redistribute, including commercially, without warranty.
