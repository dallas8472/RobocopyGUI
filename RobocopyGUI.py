import sys
import os
import json
import subprocess
import datetime
import ctypes
import re
import shutil
import traceback

"""
Robocopy GUI
--------------
This module provides a simple graphical interface for the Windows tool
`robocopy`. The application is implemented with PyQt6 and runs Robocopy
calls in a separate thread, reads the output and shows a formatted log
in the UI. The script is structured so it can be packaged into a single
Windows exe with PyInstaller.

Brief overview of the main components:
- `RobocopyWorker`: background thread that starts the Robocopy process and
    forwards its output to the GUI.
- `MainWindow`: main window with all controls and the log display.
- `AboutDialog`: small info dialog.
- `TaskManagerDialog`: separate window for managing saved tasks/queues/groups.

Note: the UI text is translated at runtime via STRINGS/t(); comments and
docstrings are in English.
"""
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QCheckBox,
    QSpinBox, QGroupBox, QTextEdit, QProgressBar, QFileDialog,
    QMessageBox, QDateEdit, QSplashScreen, QDialog, QDialogButtonBox,
    QSpacerItem, QSizePolicy, QGridLayout,
    QListWidget, QListWidgetItem, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate, QTimer, QSize, QLocale
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap, QAction, QFontMetrics, QActionGroup

try:
    import qtawesome as qta
except ImportError:
    qta = None

try:
    from send2trash import send2trash
except ImportError:
    # Falls back to permanent deletion if send2trash isn't installed, so
    # "delete by date/name" still works.
    send2trash = os.remove

def icon(name, color="#e0e0e0"):
    """Returns a qtawesome icon, or an empty QIcon if qtawesome is missing
    or the icon name is invalid (e.g. an older font version). This way the
    UI never breaks because of a missing icon."""
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color)
    except Exception:
        return QIcon()

# Configuration
APP_NAME = "Robocopy GUI"
VERSION = "2.3"
CONFIG_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'py_config.json')
LOGO_FILENAME = "logo.png"
TASKS_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'tasks.json')
TASK_GROUPS_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'task_groups.json')
SETTINGS_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'settings.json')
# Old filename of the former, separate "presets" feature - only read once for
# migration into TASKS_FILE (see MainWindow._migrate_legacy_presets).
LEGACY_PRESETS_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'presets.json')

# Layout constants
COL_WIDTH = 11
LABEL_WIDTH = 12

# Color palettes for dark/light theme. apply_styles() builds the QSS from
# these, _icon_color() returns the matching default icon color (icons on
# colored buttons like btn_blue/btn_red still get an explicit color='white'
# and are unaffected by this, see _reg_icon).
PALETTES = {
    "dark": {
        "window_bg": "#1e1e1e", "text": "#e0e0e0", "text_muted": "#888888",
        "menubar_bg": "#252526", "menubar_border": "#3e3e3e", "menu_item_hover": "#3e3e3e",
        "tooltip_bg": "#2d2d2d", "tooltip_text": "#f0f0f0", "tooltip_border": "#007acc",
        "groupbox_bg": "#222222", "groupbox_border": "#3a3a3a", "groupbox_title": "#4fb3e8",
        "input_bg": "#2b2b2b", "input_border": "#3e3e3e", "input_text": "#f0f0f0", "input_focus_border": "#4fb3e8",
        "spin_btn_bg": "#3c3c3c", "spin_btn_hover": "#4a4a4a",
        "checkbox_bg": "#2b2b2b", "checkbox_border": "#5a5a5a", "checkbox_disabled_bg": "#262626", "checkbox_disabled_border": "#3a3a3a",
        "button_bg": "#3c3c3c", "button_border": "#454545", "button_text": "white",
        "button_hover": "#4a4a4a", "button_hover_border": "#5a5a5a", "button_pressed": "#333333",
        "button_disabled_bg": "#2a2a2a", "button_disabled_text": "#777777", "button_disabled_border": "#333333",
        "accent": "#007acc", "accent_hover": "#1f8ad2", "accent_pressed": "#006bb3",
        "danger": "#c42b1c", "danger_hover": "#d73a2d", "danger_pressed": "#a92418",
        "list_bg": "#191919", "list_border": "#3e3e3e", "list_text": "#d4d4d4", "list_item_hover": "#2d2d2d",
        "log_bg": "#101010", "log_border": "#3e3e3e", "log_text": "#cccccc",
        "progress_bg": "#252526",
        "status_label": "#4fb3e8",
        "scrollbar_track": "#1e1e1e", "scrollbar_handle": "#454545", "scrollbar_handle_hover": "#5a5a5a",
        "icon_default": "#e0e0e0",
    },
    "light": {
        "window_bg": "#f3f3f3", "text": "#1e1e1e", "text_muted": "#767676",
        "menubar_bg": "#ffffff", "menubar_border": "#d4d4d4", "menu_item_hover": "#e5e5e5",
        "tooltip_bg": "#ffffff", "tooltip_text": "#1e1e1e", "tooltip_border": "#0a66b0",
        "groupbox_bg": "#ffffff", "groupbox_border": "#d9d9d9", "groupbox_title": "#0a66b0",
        "input_bg": "#ffffff", "input_border": "#c9c9c9", "input_text": "#1e1e1e", "input_focus_border": "#0a66b0",
        "spin_btn_bg": "#e8e8e8", "spin_btn_hover": "#d8d8d8",
        "checkbox_bg": "#ffffff", "checkbox_border": "#b0b0b0", "checkbox_disabled_bg": "#eeeeee", "checkbox_disabled_border": "#d5d5d5",
        "button_bg": "#e8e8e8", "button_border": "#c9c9c9", "button_text": "#1e1e1e",
        "button_hover": "#dcdcdc", "button_hover_border": "#b5b5b5", "button_pressed": "#cfcfcf",
        "button_disabled_bg": "#f0f0f0", "button_disabled_text": "#a0a0a0", "button_disabled_border": "#dddddd",
        "accent": "#007acc", "accent_hover": "#1f8ad2", "accent_pressed": "#006bb3",
        "danger": "#c42b1c", "danger_hover": "#d73a2d", "danger_pressed": "#a92418",
        "list_bg": "#ffffff", "list_border": "#c9c9c9", "list_text": "#1e1e1e", "list_item_hover": "#f0f0f0",
        "log_bg": "#ffffff", "log_border": "#c9c9c9", "log_text": "#1e1e1e",
        "progress_bg": "#eaeaea",
        "status_label": "#0a66b0",
        "scrollbar_track": "#f3f3f3", "scrollbar_handle": "#c1c1c1", "scrollbar_handle_hover": "#a6a6a6",
        "icon_default": "#3c3c3c",
    },
}

# Log text colors per theme (see MainWindow.append_log).
LOG_COLORS = {
    "dark": {
        "DEFAULT": "#cccccc", "HEADER": "#007acc", "SUCCESS": "#4ec9b0",
        "WARNING": "#ce9178", "ERROR": "#f44747", "SUMMARY": "#569cd6",
        "SUMMARY_BOLD": "#ffffff",
    },
    "light": {
        "DEFAULT": "#1e1e1e", "HEADER": "#0a66b0", "SUCCESS": "#0f7a5f",
        "WARNING": "#8a5a1e", "ERROR": "#c4291c", "SUMMARY": "#0a66b0",
        "SUMMARY_BOLD": "#000000",
    },
}

# Robocopy parameter sets per action type. Used by both the direct action
# buttons and the task queue, so there is a single source of truth for the
# actual Robocopy switches. Keys are internal identifiers, not user-facing
# text, and stay the same regardless of UI language.
ACTION_PARAMS = {
    "Struktur": ["/E", "/XF", "*", "/DCOPY:DAT", "/R:0", "/W:0"],
    "Update": ["/E", "/DCOPY:DAT", "/XO", "/R:1", "/W:1", "/MT:8", "/Z"],
    "Mirror": ["/MIR", "/DCOPY:DAT", "/R:1", "/W:1", "/MT:8", "/XJ", "/Z"],
    "Purge": ["/PURGE", "/E", "/XF", "*"],
    "Vergleich": ["/E", "/L", "/R:0"],
}

# --- i18n --------------------------------------------------------------
# Lightweight dict-based translation system (no Qt .ts/.qm toolchain, which
# would be overkill for an app this size). The UI language is picked once at
# startup (system locale, or an explicit user choice saved in settings.json)
# and stays fixed for the running process - switching languages via the menu
# only takes effect after restarting the app, which keeps this simple: no
# need to re-run through every widget and re-set its text live.
STRINGS = {
    "de": {
        "app.mode_admin": "[ADMIN]", "app.mode_user": "[USER]",
        "col.type": "Typ", "col.total": "Total", "col.copied": "Kopiert",
        "col.skipped": "Überspr.", "col.mismatch": "Mismatch", "col.errors": "FEHLER", "col.extras": "Extras",
        "col.dirs": "Verzeich.:", "col.files": "Dateien:", "col.bytes": "Bytes:", "col.times": "Zeiten:",
        "worker.exec_error": "FEHLER BEI AUSFÜHRUNG: {error}",
        # Display labels for the ACTION_PARAMS keys (which stay stable,
        # untranslated identifiers used for JSON persistence/lookup - see
        # action_label()). Struktur/Vergleich are real German words and
        # need a translation; Update/Mirror/Purge are already
        # robocopy/English jargon and read the same in both languages.
        "action.Struktur": "Struktur", "action.Update": "Update", "action.Mirror": "Mirror",
        "action.Purge": "Purge", "action.Vergleich": "Vergleich",
        "about.title": "Info",
        "about.text": "Version {version}<br><br>Modernes Interface für Robocopy.<br>Python & PyQt6 Edition",
        "menu.file": "Datei", "menu.exit": "Beenden",
        "menu.tasks": "Tasks",
        "menu.view": "Ansicht", "menu.light_theme": "Helles Design",
        "menu.language": "Sprache",
        "menu.language_restart_title": "Neustart erforderlich",
        "menu.language_restart_text": "Die Sprache wird nach einem Neustart der Anwendung wirksam.",
        "menu.admin_mode": "Admin-Modus", "menu.restart_as_admin": "Als Administrator neu starten",
        "menu.already_admin": "Läuft bereits als Admin",
        "menu.help": "Hilfe", "menu.about": "Über...",
        "msg.robocopy_missing_title": "robocopy nicht gefunden",
        "msg.robocopy_missing_text": "Das Programm \"robocopy.exe\" wurde im PATH nicht gefunden.\n\n"
            "robocopy ist normalerweise Teil von Windows - ohne dieses Tool "
            "kann diese Anwendung keine Kopier-/Löschvorgänge ausführen.",
        "group.paths": "Pfadauswahl",
        "btn.browse": " Durchsuchen... ",
        "label.source": "Quellordner:", "label.target": "Zielordner:",
        "tooltip.source": "Wählen Sie den Quellordner für den Robocopy-Vorgang.",
        "tooltip.target": "Wählen Sie den Zielordner für den Robocopy-Vorgang.",
        "group.options": "Kopier-Optionen",
        "label.file_age": "Dateialter:",
        "tooltip.days": "Kopiert nur Dateien, die jünger als die angegebene Anzahl von Tagen sind. 0 bedeutet alle Dateien.",
        "label.days_suffix": "Tage (0 = Alle)",
        "chk.acl": "Berechtigungen (ACLs) /COPYALL",
        "tooltip.acl": "Kopiert Dateiberechtigungen (ACLs). Benötigt Administratorrechte.",
        "btn.enable_admin": " Als Admin aktivieren",
        "tooltip.enable_admin": "Neustart als Administrator, um ACL-Kopie zu erlauben",
        "chk.verbose": "Alle Dateien anzeigen (Verbose /V)",
        "tooltip.verbose": "Zeigt auch übersprungene Dateien an. Füllt das Log!",
        "chk.log_prefix": "Logdatei erstellen in ",
        "tooltip.log": "Erstellt eine detaillierte Logdatei des Robocopy-Vorgangs in {dir}.",
        "group.delete": "Spezial-Löschen (Ziel)",
        "tooltip.date": "Wählen Sie ein Datum, um Dateien im Zielordner zu löschen, die an diesem Datum geändert wurden.",
        "btn.delete_by_date": " Löschen nach Datum",
        "tooltip.delete_by_date": "Verschiebt Dateien im Zielordner, die am ausgewählten Datum geändert wurden, in den Papierkorb.",
        "label.date": "Datum:",
        "placeholder.pattern": "z.B. *temp*",
        "tooltip.pattern": "Geben Sie ein Muster ein (z.B. *temp*), um Dateien im Zielordner zu löschen, die diesem Muster entsprechen.",
        "btn.delete_by_name": " Löschen nach Name",
        "tooltip.delete_by_name": "Verschiebt Dateien im Zielordner, deren Namen dem eingegebenen Muster entsprechen, in den Papierkorb.",
        "label.pattern": "Muster:",
        "group.actions": "Ausführung",
        "btn.struct": " Struktur",
        "tooltip.struct": "Kopiert nur die Ordnerstruktur (leere Ordner) ohne Dateien. Nützlich für die Vorbereitung eines Ziels.",
        "btn.update": " Daten Update",
        "tooltip.update": "Führt ein inkrementelles Update durch: Kopiert neue und geänderte Dateien. Überspringt vorhandene, identische Dateien.",
        "btn.mirror": " SPIEGELN (Mirror)",
        "tooltip.mirror": "Spiegelt den Quellordner zum Ziel. Dateien im Ziel, die in der Quelle nicht vorhanden sind, werden GELÖSCHT. Vorsicht!",
        "btn.purge": " BEREINIGEN (Purge)",
        "tooltip.purge": "Löscht Dateien und Ordner im Ziel, die in der Quelle nicht vorhanden sind, ohne Dateien zu kopieren. Vorsicht!",
        "btn.compare": " Vergleich",
        "tooltip.compare": "Führt einen Vergleich der Quell- und Zielordner durch und zeigt die Unterschiede an, ohne Änderungen vorzunehmen.",
        "btn.cancel": " Abbrechen",
        "status.ready": "Bereit",
        "btn.change_log_dir": " Log-Ordner ändern",
        "btn.clear_log": " Log leeren",
        "status.running": "{name} läuft...",
        "status.cancelled": "Abgebrochen",
        "log.job_start": " JOB START: {name} | {time}",
        "log.source": " QUELLE:    {src}",
        "log.target": " ZIEL:      {dst}",
        "log.filter": " FILTER:    Nur Dateien jünger als {days} Tage",
        "log.job_done": "--- {name} BEENDET (Exit-Code {code}) ---",
        "msg.job_done_title": "Fertig", "msg.job_done_text": "{name} wurde erfolgreich beendet.",
        "msg.job_error_title": "Fehler", "msg.job_error_text": "{name} wurde mit Fehlern beendet (Exit-Code {code}).",
        "msg.select_paths": "Bitte Quell- und Zielordner angeben.",
        "msg.acl_confirm_title": "ACLs kopieren",
        "msg.acl_confirm_text": "ACLs kopieren erfordert Admin-Rechte und kann Berechtigungen überschreiben.\nFortfahren?",
        "msg.acl_missing_rights_title": "Fehlende Rechte",
        "msg.acl_missing_rights_text": "ACL Kopie benötigt Admin-Rechte.\nNeustart als Admin?",
        "log.source_missing": "FEHLER: Quellordner nicht gefunden: {src}",
        "log.target_created": "Zielordner automatisch erstellt: {dst}",
        "log.target_create_failed": "FEHLER: Zielordner konnte nicht erstellt werden: {error}",
        "log.acl_skipped": "WARNUNG: ACL-Kopie übersprungen (keine Admin-Rechte).",
        "msg.mirror_warning": "WARNUNG: MIRROR (SPIEGELN)\n\nDies LÖSCHT alle Dateien im Zielordner, die in der Quelle nicht vorhanden sind!\n\nFortfahren?",
        "msg.mirror_filter_warning": "\n\nACHTUNG: Filter aktiv ({days} Tage)! Alte Ordner werden nicht gespiegelt und im Ziel ggf. gelöscht!",
        "msg.critical_warning_title": "Kritische Warnung",
        "msg.purge_warning": "PURGE: Wirklich Dateien im Ziel löschen, die nicht in der Quelle sind (kein Kopieren)?",
        "msg.warning_title": "Warnung",
        "msg.trash_confirm_title": "In Papierkorb verschieben",
        "msg.trash_by_date_confirm": "Alle Dateien in '{target}' in den Papierkorb verschieben, die am {date} geändert wurden?",
        "log.trash_by_date_start": "Starte Verschieben in den Papierkorb nach Datum: {date}...",
        "log.trashed": "In Papierkorb verschoben: {path}",
        "log.error_generic": "Fehler: {error}",
        "log.trash_done": "Fertig. {count} Dateien in den Papierkorb verschoben.",
        "msg.info_title": "Info",
        "msg.trash_done_text": "{count} Dateien in den Papierkorb verschoben.",
        "msg.security_warning_title": "Sicherheitswarnung",
        "msg.trash_by_name_confirm": "SICHERHEITSWARNUNG!\n\nDateien in '{target}'\ndie '{pattern}' im Namen haben in den Papierkorb verschieben?\n\nFortfahren?",
        "log.trash_by_name_start": "Starte Verschieben in den Papierkorb nach Muster: *{pattern}*...",
        "msg.error_title": "Fehler",
        "msg.source_missing": "Quellordner existiert nicht: {src}",
        "msg.target_missing_title": "Zielordner fehlt",
        "msg.target_missing_text": "Zielordner existiert nicht: {dst}\nErstellen?",
        "msg.target_create_failed": "Konnte Zielordner nicht erstellen: {error}",
        "msg.no_selection_title": "Keine Auswahl",
        "msg.no_selection_text": "Bitte mindestens eine Task markieren, die als Warteschlange ausgeführt werden soll.",
        "msg.already_running_title": "Läuft bereits",
        "msg.already_running_text": "Es läuft bereits ein Robocopy-Vorgang.",
        "msg.destructive_warning": "Die Warteschlange enthält {count} destruktive Task(s) (Mirror/Purge), "
            "die Dateien im Ziel LÖSCHEN können:\n\n{names}\n\nWarteschlange trotzdem starten?",
        "log.queue_label": "Warteschlange",
        "log.queue_started": "=== WARTESCHLANGE GESTARTET ({count} Tasks) ===",
        "log.queue_finished": "=== WARTESCHLANGE BEENDET: {ok} OK, {fail} fehlgeschlagen ===",
        "msg.queue_done_title": "Warteschlange abgeschlossen",
        "msg.queue_done_text": "{ok} erfolgreich, {fail} fehlgeschlagen.\n\n{lines}",
        "queue.ok_label": "OK    ", "queue.fail_label": "FEHLER",
        "log.cancelled": "--- ABGEBROCHEN ---",
        "log.queue_cancelled": "--- WARTESCHLANGE ABGEBROCHEN ({pos}/{total} Tasks gestartet) ---",
        "dialog.choose_log_dir": "Log-Ordner auswählen",
        "dialog.choose_folder": "Ordner auswählen",
        "taskdlg.title": "Tasks verwalten",
        "taskdlg.hint": "Strg/Umschalt-Klick markiert mehrere Tasks für die Warteschlange.\nPer Drag & Drop lässt sich die Reihenfolge ändern.",
        "btn.new": " Neu",
        "tooltip.new_task": "Leert das Formular rechts für eine neue Task.",
        "btn.delete": " Löschen",
        "tooltip.delete_tasks": "Löscht die markierte(n) Task(s).",
        "group.groups": "Gruppen",
        "tooltip.group_combo": "Bestehende Gruppe wählen (Dropdown-Pfeil rechts) oder neuen Namen eingeben.",
        "btn.save": " Speichern",
        "tooltip.group_save": "Speichert die aktuell markierten Tasks (in Listreihenfolge) unter diesem Namen als Gruppe.",
        "btn.apply": " Anwenden",
        "tooltip.group_apply": "Markiert die zu dieser Gruppe gehörenden Tasks in der Liste oben.",
        "tooltip.group_delete": "Löscht diese Gruppe (die referenzierten Tasks bleiben erhalten).",
        "group.task_form": "Task bearbeiten",
        "label.name": "Name:", "label.action": "Aktion:",
        "label.source_short": "Quelle:", "label.target_short": "Ziel:",
        "tooltip.browse": "Durchsuchen...",
        "chk.log_simple": "Logdatei erstellen (im eingestellten Log-Ordner)",
        "tooltip.save_task": "Speichert diese Task (überschreibt bei gleichem Namen).",
        "btn.start_queue": " Warteschlange starten",
        "btn.start_queue_n": " Warteschlange starten ({count})",
        "tooltip.start_queue": "Führt alle markierten Tasks in Listreihenfolge nacheinander aus.",
        "btn.close": " Schließen",
        "msg.select_tasks": "Bitte mindestens eine Task in der Liste markieren.",
        "msg.delete_tasks_confirm_title": "Task(s) löschen",
        "msg.delete_tasks_confirm_text": "Folgende Task(s) wirklich löschen?\n\n{names}",
        "msg.group_name_missing": "Bitte einen Namen für die Gruppe angeben.",
        "msg.group_needs_tasks": "Bitte mindestens eine Task markieren, die zur Gruppe gehören soll.",
        "msg.group_invalid": "Bitte eine gültige Gruppe wählen.",
        "log.group_missing_tasks": "WARNUNG: Gruppe '{name}' referenziert nicht mehr vorhandene Task(s), übersprungen: {missing}",
        "msg.group_invalid_delete": "Bitte eine gültige Gruppe zum Löschen wählen.",
        "msg.delete_group_confirm_title": "Gruppe löschen",
        "msg.delete_group_confirm_text": "Gruppe '{name}' wirklich löschen? (Die enthaltenen Tasks selbst bleiben erhalten.)",
    },
    "en": {
        "app.mode_admin": "[ADMIN]", "app.mode_user": "[USER]",
        "col.type": "Type", "col.total": "Total", "col.copied": "Copied",
        "col.skipped": "Skipped", "col.mismatch": "Mismatch", "col.errors": "ERRORS", "col.extras": "Extras",
        "col.dirs": "Dirs:", "col.files": "Files:", "col.bytes": "Bytes:", "col.times": "Times:",
        "worker.exec_error": "EXECUTION ERROR: {error}",
        "action.Struktur": "Structure", "action.Update": "Update", "action.Mirror": "Mirror",
        "action.Purge": "Purge", "action.Vergleich": "Compare",
        "about.title": "About",
        "about.text": "Version {version}<br><br>Modern interface for Robocopy.<br>Python & PyQt6 Edition",
        "menu.file": "File", "menu.exit": "Exit",
        "menu.tasks": "Tasks",
        "menu.view": "View", "menu.light_theme": "Light theme",
        "menu.language": "Language",
        "menu.language_restart_title": "Restart required",
        "menu.language_restart_text": "The language change takes effect after restarting the application.",
        "menu.admin_mode": "Admin mode", "menu.restart_as_admin": "Restart as administrator",
        "menu.already_admin": "Already running as admin",
        "menu.help": "Help", "menu.about": "About...",
        "msg.robocopy_missing_title": "robocopy not found",
        "msg.robocopy_missing_text": "The program \"robocopy.exe\" was not found in the PATH.\n\n"
            "robocopy is normally part of Windows - without this tool "
            "this application cannot perform copy/delete operations.",
        "group.paths": "Path selection",
        "btn.browse": " Browse... ",
        "label.source": "Source folder:", "label.target": "Target folder:",
        "tooltip.source": "Select the source folder for the Robocopy operation.",
        "tooltip.target": "Select the target folder for the Robocopy operation.",
        "group.options": "Copy options",
        "label.file_age": "File age:",
        "tooltip.days": "Only copies files younger than the specified number of days. 0 means all files.",
        "label.days_suffix": "Days (0 = all)",
        "chk.acl": "Permissions (ACLs) /COPYALL",
        "tooltip.acl": "Copies file permissions (ACLs). Requires administrator rights.",
        "btn.enable_admin": " Enable as admin",
        "tooltip.enable_admin": "Restart as administrator to allow ACL copying",
        "chk.verbose": "Show all files (verbose /V)",
        "tooltip.verbose": "Also shows skipped files. Fills up the log!",
        "chk.log_prefix": "Create log file in ",
        "tooltip.log": "Creates a detailed log file of the Robocopy operation in {dir}.",
        "group.delete": "Special delete (target)",
        "tooltip.date": "Select a date to delete files in the target folder that were modified on that date.",
        "btn.delete_by_date": " Delete by date",
        "tooltip.delete_by_date": "Moves files in the target folder that were modified on the selected date to the recycle bin.",
        "label.date": "Date:",
        "placeholder.pattern": "e.g. *temp*",
        "tooltip.pattern": "Enter a pattern (e.g. *temp*) to delete files in the target folder matching this pattern.",
        "btn.delete_by_name": " Delete by name",
        "tooltip.delete_by_name": "Moves files in the target folder whose name matches the entered pattern to the recycle bin.",
        "label.pattern": "Pattern:",
        "group.actions": "Execution",
        "btn.struct": " Structure",
        "tooltip.struct": "Copies only the folder structure (empty folders) without files. Useful for preparing a target.",
        "btn.update": " Data update",
        "tooltip.update": "Performs an incremental update: copies new and changed files. Skips existing, identical files.",
        "btn.mirror": " MIRROR",
        "tooltip.mirror": "Mirrors the source folder to the target. Files in the target that don't exist in the source will be DELETED. Caution!",
        "btn.purge": " PURGE",
        "tooltip.purge": "Deletes files and folders in the target that don't exist in the source, without copying files. Caution!",
        "btn.compare": " Compare",
        "tooltip.compare": "Compares the source and target folders and shows the differences without making any changes.",
        "btn.cancel": " Cancel",
        "status.ready": "Ready",
        "btn.change_log_dir": " Change log folder",
        "btn.clear_log": " Clear log",
        "status.running": "{name} running...",
        "status.cancelled": "Cancelled",
        "log.job_start": " JOB START: {name} | {time}",
        "log.source": " SOURCE:    {src}",
        "log.target": " TARGET:    {dst}",
        "log.filter": " FILTER:    Only files younger than {days} days",
        "log.job_done": "--- {name} FINISHED (exit code {code}) ---",
        "msg.job_done_title": "Done", "msg.job_done_text": "{name} finished successfully.",
        "msg.job_error_title": "Error", "msg.job_error_text": "{name} finished with errors (exit code {code}).",
        "msg.select_paths": "Please specify source and target folders.",
        "msg.acl_confirm_title": "Copy ACLs",
        "msg.acl_confirm_text": "Copying ACLs requires admin rights and can overwrite permissions.\nContinue?",
        "msg.acl_missing_rights_title": "Missing rights",
        "msg.acl_missing_rights_text": "ACL copying requires admin rights.\nRestart as admin?",
        "log.source_missing": "ERROR: Source folder not found: {src}",
        "log.target_created": "Target folder created automatically: {dst}",
        "log.target_create_failed": "ERROR: Could not create target folder: {error}",
        "log.acl_skipped": "WARNING: ACL copy skipped (no admin rights).",
        "msg.mirror_warning": "WARNING: MIRROR\n\nThis DELETES all files in the target folder that don't exist in the source!\n\nContinue?",
        "msg.mirror_filter_warning": "\n\nWARNING: Filter active ({days} days)! Old folders won't be mirrored and may be deleted in the target!",
        "msg.critical_warning_title": "Critical warning",
        "msg.purge_warning": "PURGE: Really delete files in the target that aren't in the source (no copying)?",
        "msg.warning_title": "Warning",
        "msg.trash_confirm_title": "Move to recycle bin",
        "msg.trash_by_date_confirm": "Move all files in '{target}' modified on {date} to the recycle bin?",
        "log.trash_by_date_start": "Starting move to recycle bin by date: {date}...",
        "log.trashed": "Moved to recycle bin: {path}",
        "log.error_generic": "Error: {error}",
        "log.trash_done": "Done. {count} files moved to the recycle bin.",
        "msg.info_title": "Info",
        "msg.trash_done_text": "{count} files moved to the recycle bin.",
        "msg.security_warning_title": "Security warning",
        "msg.trash_by_name_confirm": "SECURITY WARNING!\n\nMove files in '{target}'\nwhose name contains '{pattern}' to the recycle bin?\n\nContinue?",
        "log.trash_by_name_start": "Starting move to recycle bin by pattern: *{pattern}*...",
        "msg.error_title": "Error",
        "msg.source_missing": "Source folder does not exist: {src}",
        "msg.target_missing_title": "Target folder missing",
        "msg.target_missing_text": "Target folder does not exist: {dst}\nCreate it?",
        "msg.target_create_failed": "Could not create target folder: {error}",
        "msg.no_selection_title": "No selection",
        "msg.no_selection_text": "Please select at least one task to run as a queue.",
        "msg.already_running_title": "Already running",
        "msg.already_running_text": "A Robocopy operation is already running.",
        "msg.destructive_warning": "The queue contains {count} destructive task(s) (Mirror/Purge) "
            "that can DELETE files in the target:\n\n{names}\n\nStart the queue anyway?",
        "log.queue_label": "Queue",
        "log.queue_started": "=== QUEUE STARTED ({count} tasks) ===",
        "log.queue_finished": "=== QUEUE FINISHED: {ok} OK, {fail} failed ===",
        "msg.queue_done_title": "Queue finished",
        "msg.queue_done_text": "{ok} succeeded, {fail} failed.\n\n{lines}",
        "queue.ok_label": "OK    ", "queue.fail_label": "FAILED",
        "log.cancelled": "--- CANCELLED ---",
        "log.queue_cancelled": "--- QUEUE CANCELLED ({pos}/{total} tasks started) ---",
        "dialog.choose_log_dir": "Select log folder",
        "dialog.choose_folder": "Select folder",
        "taskdlg.title": "Manage tasks",
        "taskdlg.hint": "Ctrl/Shift-click selects multiple tasks for the queue.\nDrag & drop to change the order.",
        "btn.new": " New",
        "tooltip.new_task": "Clears the form on the right for a new task.",
        "btn.delete": " Delete",
        "tooltip.delete_tasks": "Deletes the selected task(s).",
        "group.groups": "Groups",
        "tooltip.group_combo": "Select an existing group (dropdown arrow on the right) or enter a new name.",
        "btn.save": " Save",
        "tooltip.group_save": "Saves the currently selected tasks (in list order) under this name as a group.",
        "btn.apply": " Apply",
        "tooltip.group_apply": "Selects the tasks belonging to this group in the list above.",
        "tooltip.group_delete": "Deletes this group (the referenced tasks remain).",
        "group.task_form": "Edit task",
        "label.name": "Name:", "label.action": "Action:",
        "label.source_short": "Source:", "label.target_short": "Target:",
        "tooltip.browse": "Browse...",
        "chk.log_simple": "Create log file (in the configured log folder)",
        "tooltip.save_task": "Saves this task (overwrites if the name matches).",
        "btn.start_queue": " Start queue",
        "btn.start_queue_n": " Start queue ({count})",
        "tooltip.start_queue": "Runs all selected tasks one after another in list order.",
        "btn.close": " Close",
        "msg.select_tasks": "Please select at least one task in the list.",
        "msg.delete_tasks_confirm_title": "Delete task(s)",
        "msg.delete_tasks_confirm_text": "Really delete the following task(s)?\n\n{names}",
        "msg.group_name_missing": "Please enter a name for the group.",
        "msg.group_needs_tasks": "Please select at least one task to belong to the group.",
        "msg.group_invalid": "Please select a valid group.",
        "log.group_missing_tasks": "WARNING: Group '{name}' references task(s) that no longer exist, skipped: {missing}",
        "msg.group_invalid_delete": "Please select a valid group to delete.",
        "msg.delete_group_confirm_title": "Delete group",
        "msg.delete_group_confirm_text": "Really delete group '{name}'? (The tasks themselves remain.)",
    },
}

_current_lang = "en"

def detect_system_language():
    """Maps the OS locale to one of our supported languages, defaulting to
    English for anything that isn't German (broadest reach for an
    international audience)."""
    try:
        name = QLocale.system().name()  # e.g. "de_DE", "en_US"
    except Exception:
        name = "en"
    return "de" if name.lower().startswith("de") else "en"

def set_language(lang):
    global _current_lang
    _current_lang = lang if lang in STRINGS else "en"

def t(key, **kwargs):
    """Looks up `key` in the active language, falling back to English and
    finally to the raw key if truly missing (so a missing translation shows
    up as an odd-looking label instead of crashing)."""
    text = STRINGS.get(_current_lang, {}).get(key)
    if text is None:
        text = STRINGS["en"].get(key, key)
    if kwargs:
        return text.format(**kwargs)
    return text

def action_label(action_key):
    """Translated display label for an ACTION_PARAMS key. The key itself
    (e.g. "Struktur", "Vergleich") stays a stable, untranslated identifier
    used for JSON persistence and for looking up the robocopy switches in
    ACTION_PARAMS - only the text shown to the user goes through t()."""
    return t(f"action.{action_key}")

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    # Returns the path of a bundled resource (e.g. logo.png). Once frozen by
    # PyInstaller, the temporary attribute `sys._MEIPASS` exists and must be
    # taken into account when resolving the path.
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def is_admin():
    """Check if the script is running with admin privileges"""
    # os.geteuid() would work on Unix; on Windows we use the shell32 API to
    # determine whether the user has administrator rights.
    try:
        return os.geteuid() == 0
    except AttributeError:
        try:
            return ctypes.windll.shell32.IsUserAnAdmin()
        except:
            return False

def restart_as_admin():
    """Restart the script with admin privileges"""
    script_path = os.path.abspath(__file__)
    executable = sys.executable
    params = "" if getattr(sys, 'frozen', False) else f'"{script_path}"'
    try:
        # Restarts the current Python executable with the script path as an
        # argument and requests the UAC prompt (needed on Windows).
        ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
        sys.exit()
    except Exception as e:
        print(f"Failed to restart as admin: {e}")

class RobocopyWorker(QThread):
    """Background thread that runs `robocopy`.

    The worker starts the Robocopy process with the given parameters, reads
    its output line by line and sends it to the GUI via a signal so the
    display can be updated on the main thread.

    Notes:
    - The process output is read using the cp850 encoding (the common OEM
      encoding on German Windows systems).
    - Errors are sent to the GUI as a log message.
    """
    log_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(int)

    def __init__(self, command):
        super().__init__()
        # `command` is a list like ["robocopy", src, dst, ...]
        self.command = command
        self.process = None

    def run(self):
        try:
            # Start robocopy in the background and read stdout
            self.process = subprocess.Popen(
                self.command,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='cp850',
                errors='replace',
                creationflags=subprocess.CREATE_NO_WINDOW
            )

            in_summary = False
            for line in self.process.stdout:
                line = line.rstrip()
                if not line:
                    continue

                # Try to recognize the start of the summary block (German/English)
                if "Insgesamt" in line or ("Total" in line and "Kopiert" in line):
                    in_summary = True
                    self.log_signal.emit("-" * (LABEL_WIDTH + (6 * (COL_WIDTH+3))), "DEFAULT")
                    header = (
                        f"{t('col.type'):<{LABEL_WIDTH}} {t('col.total'):>{COL_WIDTH}} {t('col.copied'):>{COL_WIDTH}} "
                        f"{t('col.skipped'):>{COL_WIDTH}} {t('col.mismatch'):>{COL_WIDTH}} {t('col.errors'):>{COL_WIDTH}} {t('col.extras'):>{COL_WIDTH}}"
                    )
                    self.log_signal.emit(header, "SUMMARY")
                    self.log_signal.emit("-" * (LABEL_WIDTH + (6 * (COL_WIDTH+3))), "DEFAULT")
                    continue

                # Extract formatted values inside the summary block. Note:
                # these keys match ROBOCOPY's OWN output (which follows the
                # Windows system locale, independent of our app's UI
                # language), so they intentionally stay hardcoded in both
                # languages rather than going through t().
                if in_summary:
                    if "-----" in line:
                        continue

                    if ":" in line:
                        clean_line = line.strip()
                        label_mapping = {
                            "Verzeich": t("col.dirs"), "Dirs": t("col.dirs"),
                            "Dateien": t("col.files"), "Files": t("col.files"),
                            "Bytes": t("col.bytes"),
                            "Zeiten": t("col.times"), "Times": t("col.times"),
                            "Geschwind": None, "Speed": None,
                            "Beendet": None, "Ended": None
                        }

                        current_label = None
                        for key, val in label_mapping.items():
                            if key in clean_line:
                                current_label = val
                                break

                        if current_label:
                            # \s* is placed INSIDE the optional unit group on
                            # purpose: this way whitespace is only consumed
                            # together with a following unit (t/g/m/k). If
                            # \s* were in front (as it originally was), it
                            # would also greedily eat the entire gap to the
                            # next number even without a unit present - the
                            # value would then carry its whitespace BEFORE
                            # the number, which breaks the right-alignment
                            # (":>11") that follows and makes the table in
                            # the log look garbled.
                            vals = re.findall(r"(\d+:\d+:\d+|\d+(?:\.\d+)?(?:\s*[tgmkTGMK])?)", clean_line)
                            if len(vals) >= 6:
                                v = [x.strip() for x in vals[-6:]]
                                formatted = f"{current_label:<{LABEL_WIDTH}} {v[0]:>{COL_WIDTH}} {v[1]:>{COL_WIDTH}} {v[2]:>{COL_WIDTH}} {v[3]:>{COL_WIDTH}} {v[4]:>{COL_WIDTH}} {v[5]:>{COL_WIDTH}}"
                                self.log_signal.emit(formatted, "SUMMARY_BOLD")
                                continue

                        if "Geschwind" in line or "Speed" in line or "Beendet" in line or "Ended" in line:
                            self.log_signal.emit(line.strip(), "SUMMARY")
                            continue

                # Filter out some percentage lines
                if re.match(r"^\s*\d+%", line):
                    continue

                # Determine color/type category for the display
                color_type = "DEFAULT"
                if "ROBOCOPY" in line or "---" in line or "===" in line:
                    color_type = "HEADER"
                elif "FEHLER" in line or "ERROR" in line:
                    color_type = "ERROR"
                elif "Neue Datei" in line or "New File" in line:
                    color_type = "SUCCESS"
                elif "*EXTRA" in line:
                    color_type = "WARNING"
                elif "*Gleich" in line or "*SAME" in line:
                    color_type = "DEFAULT"

                # Send output to the GUI
                self.log_signal.emit(line, color_type)

            self.process.wait()
            self.finished_signal.emit(self.process.returncode if self.process.returncode is not None else 0)
        except Exception as e:
            self.log_signal.emit(t("worker.exec_error", error=e), "ERROR")
            self.finished_signal.emit(-1)

    def terminate(self):
        # Stop the Robocopy process if active and terminate the thread
        if hasattr(self, 'process') and self.process:
            self.process.terminate()
        super().terminate()

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        """Small info dialog with app logo and version number."""
        self.setWindowTitle(t("about.title"))
        self.setFixedWidth(400)
        p = PALETTES[getattr(parent, "theme", "dark")]
        self.setStyleSheet(f"background-color: {p['window_bg']}; color: {p['text']};")
        if parent:
            self.setWindowIcon(parent.windowIcon())
        layout = QVBoxLayout()
        lbl_logo = QLabel()
        pixmap = QPixmap(resource_path(LOGO_FILENAME))
        if not pixmap.isNull():
            lbl_logo.setPixmap(pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            lbl_logo.setText(f"<b>{APP_NAME}</b>")
            lbl_logo.setStyleSheet(f"font-size: 18pt; color: {p['accent']};")
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_logo)

        layout.addSpacing(15)
        lbl_text = QLabel(t("about.text", version=VERSION))
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_text)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        btn_box.setStyleSheet(
            f"QPushButton {{ background-color: {p['button_bg']}; color: {p['button_text']}; "
            f"border: 1px solid {p['button_border']}; padding: 5px; width: 80px; border-radius: 6px; }}"
        )
        layout.addWidget(btn_box, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        """Main window of the application.

        Holds all controls for selecting source/target paths, options and
        the log display. Responsible for starting the `RobocopyWorker`
        thread and handling UI interactions.
        """
        self.log_dir = r"C:\tmp"
        mode_str = t("app.mode_admin") if is_admin() else t("app.mode_user")
        self.setWindowTitle(f"{APP_NAME} v{VERSION}  {mode_str}")
        self.resize(1150, 850)
        # Only constrain the width (readability); the height is left to
        # Qt's layout-computed, content-correct minimum (see
        # minimumSizeHint) - a guessed fixed value would either clip rows at
        # a small window size or force the window unnecessarily tall.
        self.setMinimumWidth(1000)

        # Tasks: persistent list of saved job definitions
        # (name/action/source/target/days/acl/verbose/log), see TASKS_FILE.
        self.queue_tasks = []
        # The tasks actually selected for the current queue run (a subset of
        # queue_tasks, in list order) - see start_queue().
        self._active_run_tasks = []
        self.queue_pos = 0
        self.queue_results = []
        self.queue_running = False
        self._queue_total = 0
        self._task_dialog = None

        # Task groups: named, ordered lists of task names (see
        # TASK_GROUPS_FILE), so you don't have to select all matching tasks
        # individually on every queue run.
        self.task_groups = []

        # Theme and language must be set before apply_styles()/init_menu()/
        # init_ui(), since those depend directly on them (stylesheet/icon
        # colors, and all the UI text built via t()).
        self.theme = "dark"
        self.language = detect_system_language()
        self._themed_icons = []  # (widget, icon_name) - see _reg_icon/refresh_theme_icons
        self.load_settings()
        set_language(self.language)

        icon_path = resource_path(LOGO_FILENAME)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.apply_styles()
        self.init_menu()
        self.init_ui()
        self.load_config()
        self.check_robocopy_available()

    def load_settings(self):
        try:
            if os.path.exists(SETTINGS_FILE):
                with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if data.get("theme") in PALETTES:
                        self.theme = data["theme"]
                    if data.get("language") in STRINGS:
                        self.language = data["language"]
        except Exception:
            # Not critical - defaults (dark theme, system language) are used
            pass

    def save_settings(self):
        try:
            os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
            with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
                json.dump({"theme": self.theme, "language": self.language}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _icon_color(self):
        return PALETTES[self.theme]["icon_default"]

    def _reg_icon(self, widget, name, color=None):
        """Sets a qtawesome icon on widget (QPushButton or QAction).
        Without an explicit `color`, the current theme's default color is
        used AND the icon is remembered for refresh_theme_icons(), so it
        gets recolored automatically on a theme switch. Icons on colored
        buttons (btn_blue/btn_red) deliberately pass a fixed `color`
        (usually 'white') and are unaffected by this."""
        widget.setIcon(icon(name, color=color or self._icon_color()))
        if color is None:
            self._themed_icons.append((widget, name))
        return widget

    def refresh_theme_icons(self):
        c = self._icon_color()
        for widget, name in self._themed_icons:
            widget.setIcon(icon(name, color=c))

    def toggle_theme(self, light_enabled):
        self.theme = "light" if light_enabled else "dark"
        self.apply_styles()
        self.refresh_theme_icons()
        if self._task_dialog is not None:
            self._task_dialog.refresh_theme_icons()
        self.save_settings()

    def set_language_and_notify(self, lang):
        if lang == self.language:
            return
        self.language = lang
        self.save_settings()
        QMessageBox.information(self, t("menu.language_restart_title"), t("menu.language_restart_text"))

    def check_robocopy_available(self):
        """Checks once at startup whether robocopy.exe can be found in the
        PATH. robocopy is normally a built-in part of Windows, but it can be
        missing e.g. in heavily stripped-down Windows environments or with a
        broken PATH. Without this notice, the error would only show up as a
        raw Python exception in the log once a run is started."""
        if shutil.which("robocopy") is None:
            QMessageBox.warning(self, t("msg.robocopy_missing_title"), t("msg.robocopy_missing_text"))

    def apply_styles(self):
        p = PALETTES[self.theme]
        self.setStyleSheet(f"""
            QMainWindow, QWidget {{ background-color: {p['window_bg']}; color: {p['text']}; font-family: 'Segoe UI', sans-serif; font-size: 10pt; }}
            QMenuBar {{ background-color: {p['menubar_bg']}; color: {p['text']}; border-bottom: 1px solid {p['menubar_border']}; padding: 2px; }}
            QMenuBar::item {{ padding: 4px 10px; border-radius: 4px; }}
            QMenuBar::item:selected {{ background-color: {p['menu_item_hover']}; }}
            QMenu {{ background-color: {p['menubar_bg']}; color: {p['text']}; border: 1px solid {p['groupbox_border']}; padding: 4px; }}
            QMenu::item {{ padding: 6px 24px 6px 12px; border-radius: 4px; }}
            QMenu::item:selected {{ background-color: {p['accent']}; color: white; }}
            QToolTip {{ background-color: {p['tooltip_bg']}; color: {p['tooltip_text']}; border: 1px solid {p['tooltip_border']}; padding: 4px; border-radius: 4px; }}
            QGroupBox {{ border: 1px solid {p['groupbox_border']}; border-radius: 8px; margin-top: 20px; font-weight: 600; background-color: {p['groupbox_bg']}; }}
            QGroupBox::title {{ subcontrol-origin: margin; left: 10px; padding: 0 6px; color: {p['groupbox_title']}; }}
            QLabel {{ background: transparent; }}
            QLineEdit, QComboBox, QDateEdit {{
                background-color: {p['input_bg']}; border: 1px solid {p['input_border']}; padding: 6px 8px;
                color: {p['input_text']}; border-radius: 5px; selection-background-color: {p['accent']};
            }}
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus {{ border: 1px solid {p['input_focus_border']}; }}
            QComboBox::drop-down {{
                subcontrol-origin: padding; subcontrol-position: top right; width: 24px;
                border-left: 1px solid {p['input_border']}; background-color: {p['spin_btn_bg']};
                border-top-right-radius: 5px; border-bottom-right-radius: 5px;
            }}
            QComboBox::drop-down:hover {{ background-color: {p['spin_btn_hover']}; }}
            QComboBox::down-arrow {{
                image: none; width: 0; height: 0; margin-right: 8px;
                border-left: 4px solid transparent; border-right: 4px solid transparent;
                border-top: 5px solid {p['input_text']};
            }}
            QComboBox QAbstractItemView {{
                background-color: {p['input_bg']}; color: {p['input_text']}; border: 1px solid {p['groupbox_border']};
                selection-background-color: {p['accent']}; outline: 0;
            }}
            QSpinBox {{ background-color: {p['input_bg']}; border: 1px solid {p['input_border']}; padding: 4px; color: {p['input_text']}; border-radius: 5px; min-height: 20px; }}
            QSpinBox::up-button, QSpinBox::down-button {{ width: 22px; background-color: {p['spin_btn_bg']}; border: none; }}
            QSpinBox::up-button:hover, QSpinBox::down-button:hover {{ background-color: {p['spin_btn_hover']}; }}
            QCheckBox {{ spacing: 8px; }}
            QCheckBox::indicator {{
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid {p['checkbox_border']}; background-color: {p['checkbox_bg']};
            }}
            QCheckBox::indicator:hover {{ border: 1px solid {p['input_focus_border']}; }}
            QCheckBox::indicator:checked {{ background-color: {p['accent']}; border: 1px solid {p['accent']}; }}
            QCheckBox::indicator:disabled {{ background-color: {p['checkbox_disabled_bg']}; border: 1px solid {p['checkbox_disabled_border']}; }}
            QPushButton {{
                background-color: {p['button_bg']}; border: 1px solid {p['button_border']}; padding: 8px 16px;
                border-radius: 6px; color: {p['button_text']}; font-weight: 600;
            }}
            QPushButton:hover {{ background-color: {p['button_hover']}; border: 1px solid {p['button_hover_border']}; }}
            QPushButton:pressed {{ background-color: {p['button_pressed']}; }}
            QPushButton:disabled {{ background-color: {p['button_disabled_bg']}; color: {p['button_disabled_text']}; border: 1px solid {p['button_disabled_border']}; }}
            QPushButton#btn_blue {{ background-color: {p['accent']}; border: 1px solid {p['accent']}; color: white; }}
            QPushButton#btn_blue:hover {{ background-color: {p['accent_hover']}; }}
            QPushButton#btn_blue:pressed {{ background-color: {p['accent_pressed']}; }}
            QPushButton#btn_red {{ background-color: {p['danger']}; border: 1px solid {p['danger']}; color: white; }}
            QPushButton#btn_red:hover {{ background-color: {p['danger_hover']}; }}
            QPushButton#btn_red:pressed {{ background-color: {p['danger_pressed']}; }}
            QListWidget {{
                background-color: {p['list_bg']}; border: 1px solid {p['list_border']}; border-radius: 5px;
                color: {p['list_text']}; outline: 0; padding: 2px;
            }}
            QListWidget::item {{ padding: 4px 6px; border-radius: 4px; }}
            QListWidget::item:selected {{ background-color: {p['accent']}; color: white; }}
            QListWidget::item:hover:!selected {{ background-color: {p['list_item_hover']}; }}
            QTextEdit {{ background-color: {p['log_bg']}; color: {p['log_text']}; border: 1px solid {p['log_border']}; border-radius: 5px; font-family: 'Consolas', monospace; font-size: 10pt; }}
            QProgressBar {{ border: 1px solid {p['groupbox_border']}; border-radius: 5px; text-align: center; background-color: {p['progress_bg']}; }}
            QProgressBar::chunk {{ background-color: {p['accent']}; border-radius: 4px; }}
            QLabel#status_label {{ color: {p['status_label']}; font-weight: 600; font-size: 11pt; }}
            QScrollBar:vertical {{ background: {p['scrollbar_track']}; width: 12px; margin: 0; }}
            QScrollBar::handle:vertical {{ background: {p['scrollbar_handle']}; min-height: 24px; border-radius: 5px; }}
            QScrollBar::handle:vertical:hover {{ background: {p['scrollbar_handle_hover']}; }}
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
            QScrollBar:horizontal {{ background: {p['scrollbar_track']}; height: 12px; margin: 0; }}
            QScrollBar::handle:horizontal {{ background: {p['scrollbar_handle']}; min-width: 24px; border-radius: 5px; }}
            QScrollBar::handle:horizontal:hover {{ background: {p['scrollbar_handle_hover']}; }}
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
        """)

    # apply_styles: defines the application's look via a stylesheet built from PALETTES[self.theme]

    def init_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu(t("menu.file"))
        exit_action = QAction(t("menu.exit"), self)
        self._reg_icon(exit_action, 'fa5s.sign-out-alt')
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        # Direct clickable action instead of a dropdown menu, so "Tasks"
        # opens the manager immediately with one click.
        # No icon here: on a direct menu bar action (no dropdown), Qt
        # renders the icon instead of the text - consistent with the other
        # menu bar entries (File/View/...), which are also text-only
        # without an icon.
        manage_tasks_action = QAction(t("menu.tasks"), self)
        manage_tasks_action.triggered.connect(self.open_task_manager)
        menubar.addAction(manage_tasks_action)

        view_menu = menubar.addMenu(t("menu.view"))
        self.light_theme_action = QAction(t("menu.light_theme"), self)
        self.light_theme_action.setCheckable(True)
        self.light_theme_action.setChecked(self.theme == "light")
        self.light_theme_action.toggled.connect(self.toggle_theme)
        view_menu.addAction(self.light_theme_action)

        # Language names are shown in their own language (not translated),
        # which is the common convention for a language picker.
        language_menu = view_menu.addMenu(t("menu.language"))
        language_group = QActionGroup(self)
        language_group.setExclusive(True)
        lang_de_action = QAction("Deutsch", self)
        lang_de_action.setCheckable(True)
        lang_de_action.setChecked(self.language == "de")
        lang_de_action.triggered.connect(lambda: self.set_language_and_notify("de"))
        lang_en_action = QAction("English", self)
        lang_en_action.setCheckable(True)
        lang_en_action.setChecked(self.language == "en")
        lang_en_action.triggered.connect(lambda: self.set_language_and_notify("en"))
        for a in (lang_de_action, lang_en_action):
            language_group.addAction(a)
            language_menu.addAction(a)

        admin_menu = menubar.addMenu(t("menu.admin_mode"))
        restart_action = QAction(t("menu.restart_as_admin"), self)
        self._reg_icon(restart_action, 'fa5s.user-shield')
        if is_admin():
            restart_action.setEnabled(False)
            restart_action.setText(t("menu.already_admin"))
        else:
            restart_action.triggered.connect(restart_as_admin)
        admin_menu.addAction(restart_action)

        help_menu = menubar.addMenu(t("menu.help"))
        about_action = QAction(t("menu.about"), self)
        self._reg_icon(about_action, 'fa5s.info-circle')
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 8, 16, 12)

        # Paths
        grp_paths = QGroupBox(t("group.paths"))
        layout_paths = QVBoxLayout()
        layout_paths.setSpacing(8)

        def create_path_row(label_text, combo):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(80)
            combo.setEditable(True)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn = QPushButton(t("btn.browse"))
            self._reg_icon(btn, 'fa5s.folder-open')
            btn.clicked.connect(lambda: self.browse_folder(combo))
            row.addWidget(lbl)
            row.addWidget(combo)
            row.addWidget(btn)
            return row

        self.cmb_source = QComboBox()
        self.cmb_source.setMinimumWidth(220)
        self.cmb_source.currentIndexChanged.connect(self.sync_target_combo)
        self.cmb_source.setToolTip(t("tooltip.source"))
        layout_paths.addLayout(create_path_row(t("label.source"), self.cmb_source))

        self.cmb_target = QComboBox()
        self.cmb_target.setMinimumWidth(220)
        self.cmb_target.setToolTip(t("tooltip.target"))
        layout_paths.addLayout(create_path_row(t("label.target"), self.cmb_target))

        grp_paths.setLayout(layout_paths)
        grp_paths.setMaximumHeight(160)
        main_layout.addWidget(grp_paths)

        # Options
        h_mid = QHBoxLayout()

        grp_opts = QGroupBox(t("group.options"))
        layout_opts = QVBoxLayout()
        layout_opts.setSpacing(6)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel(t("label.file_age")))
        self.spin_days = QSpinBox()
        self.spin_days.setRange(0, 9999)
        self.spin_days.setValue(0)
        self.spin_days.setToolTip(t("tooltip.days"))
        r1.addWidget(self.spin_days)
        r1.addWidget(QLabel(t("label.days_suffix")))
        r1.addStretch()
        layout_opts.addLayout(r1)

        # ACL copy: off by default, requires administrator rights. If the
        # app is running without admin rights, the checkbox is disabled and
        # a button is shown offering to restart as administrator.
        self.chk_acl = QCheckBox(t("chk.acl"))
        self.chk_acl.setChecked(False)
        self.chk_acl.setToolTip(t("tooltip.acl"))
        layout_opts.addWidget(self.chk_acl)
        if not is_admin():
            self.chk_acl.setEnabled(False)
            self.chk_acl.setStyleSheet("color: #888;")
            # Own row (instead of next to the checkbox), so the long
            # checkbox text doesn't collide with the button at a narrow
            # window width.
            h_acl = QHBoxLayout()
            btn_enable_acl = QPushButton(t("btn.enable_admin"))
            self._reg_icon(btn_enable_acl, 'fa5s.user-shield')
            btn_enable_acl.setToolTip(t("tooltip.enable_admin"))
            btn_enable_acl.setFixedWidth(190)
            btn_enable_acl.setStyleSheet("QPushButton { padding: 6px 10px; }")
            btn_enable_acl.clicked.connect(restart_as_admin)
            h_acl.addWidget(btn_enable_acl)
            h_acl.addStretch()
            layout_opts.addLayout(h_acl)

        self.chk_verbose = QCheckBox(t("chk.verbose"))
        self.chk_verbose.setToolTip(t("tooltip.verbose"))
        layout_opts.addWidget(self.chk_verbose)

        self.chk_log = QCheckBox()
        # Default: do not create a log file unless the user enables it
        self.chk_log.setChecked(False)
        self._update_log_checkbox_text()
        layout_opts.addWidget(self.chk_log)

        grp_opts.setLayout(layout_opts)
        h_mid.addWidget(grp_opts, stretch=1)

        # Delete
        grp_del = QGroupBox(t("group.delete"))
        layout_del = QGridLayout()
        layout_del.setVerticalSpacing(8)

        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setToolTip(t("tooltip.date"))
        btn_del_date = QPushButton(t("btn.delete_by_date"))
        self._reg_icon(btn_del_date, 'fa5s.calendar-times')
        btn_del_date.clicked.connect(self.delete_by_date)
        btn_del_date.setToolTip(t("tooltip.delete_by_date"))
        layout_del.addWidget(QLabel(t("label.date")), 0, 0)
        layout_del.addWidget(self.date_edit, 0, 1)
        layout_del.addWidget(btn_del_date, 0, 2)

        self.txt_pattern = QLineEdit()
        self.txt_pattern.setPlaceholderText(t("placeholder.pattern"))
        self.txt_pattern.setToolTip(t("tooltip.pattern"))
        btn_del_name = QPushButton(t("btn.delete_by_name"))
        self._reg_icon(btn_del_name, 'fa5s.eraser')
        btn_del_name.clicked.connect(self.delete_by_name)
        btn_del_name.setToolTip(t("tooltip.delete_by_name"))
        layout_del.addWidget(QLabel(t("label.pattern")), 1, 0)
        layout_del.addWidget(self.txt_pattern, 1, 1)
        layout_del.addWidget(btn_del_name, 1, 2)

        grp_del.setLayout(layout_del)
        h_mid.addWidget(grp_del, stretch=1)
        main_layout.addLayout(h_mid)

        # Actions
        grp_actions = QGroupBox(t("group.actions"))
        layout_actions = QHBoxLayout()

        btn_struct = QPushButton(t("btn.struct"))
        btn_struct.setIcon(icon('fa5s.sitemap', color='white'))
        btn_struct.setObjectName("btn_blue")
        btn_struct.setToolTip(t("tooltip.struct"))
        btn_struct.clicked.connect(lambda: self.run_robo(action_label("Struktur"), list(ACTION_PARAMS["Struktur"])))

        btn_copy = QPushButton(t("btn.update"))
        btn_copy.setIcon(icon('fa5s.copy', color='white'))
        btn_copy.setObjectName("btn_blue")
        btn_copy.setToolTip(t("tooltip.update"))
        # Uses /Z instead of /ZB, so Robocopy doesn't switch to backup mode,
        # which requires extra privileges (backup/restore).
        btn_copy.clicked.connect(lambda: self.run_robo(action_label("Update"), list(ACTION_PARAMS["Update"])))

        btn_mirror = QPushButton(t("btn.mirror"))
        btn_mirror.setIcon(icon('fa5s.exchange-alt', color='white'))
        btn_mirror.setObjectName("btn_red")
        btn_mirror.setToolTip(t("tooltip.mirror"))
        btn_mirror.clicked.connect(self.action_mirror)

        btn_purge = QPushButton(t("btn.purge"))
        btn_purge.setIcon(icon('fa5s.trash-alt', color='white'))
        btn_purge.setObjectName("btn_red")
        btn_purge.setToolTip(t("tooltip.purge"))
        btn_purge.clicked.connect(self.action_purge)

        btn_comp = QPushButton(t("btn.compare"))
        self._reg_icon(btn_comp, 'fa5s.balance-scale')
        btn_comp.setToolTip(t("tooltip.compare"))
        btn_comp.clicked.connect(lambda: self.run_robo(action_label("Vergleich"), list(ACTION_PARAMS["Vergleich"])))

        self.btn_cancel = QPushButton(t("btn.cancel"))
        self._reg_icon(self.btn_cancel, 'fa5s.times-circle')
        self.btn_cancel.clicked.connect(self.cancel_robo)
        self.btn_cancel.setEnabled(False)

        for btn in [btn_struct, btn_copy, btn_mirror, btn_purge, btn_comp, self.btn_cancel]:
            btn.setMinimumHeight(45)
            btn.setMinimumWidth(110)
        for btn in [btn_struct, btn_copy, btn_mirror, btn_purge, btn_comp]:
            layout_actions.addWidget(btn)
        layout_actions.addWidget(self.btn_cancel)
        grp_actions.setLayout(layout_actions)
        # keep action buttons compact so the log has more vertical room
        grp_actions.setMaximumHeight(120)
        main_layout.addWidget(grp_actions)

        # Widgets that get locked while a job is running (see _set_busy).
        # Deliberately NOT the whole grp_actions group or centralWidget(),
        # since btn_cancel would then be locked too as a child widget and a
        # running job could never be cancelled.
        self._lockable_widgets = [
            grp_paths, grp_opts, grp_del,
            btn_struct, btn_copy, btn_mirror, btn_purge, btn_comp,
        ]

        # Footer
        self.lbl_status = QLabel(t("status.ready"))
        self.lbl_status.setObjectName("status_label")
        main_layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        main_layout.addWidget(self.progress)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        # No fixed setMinimumHeight: that would needlessly inflate the whole
        # window's minimum size. The generous height in everyday use comes
        # from the stretch factor below + the initial window size instead;
        # at a very small window size the log may shrink accordingly (and
        # remains usable thanks to the scrollbar).
        self.txt_log.setMinimumHeight(80)
        self.txt_log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.txt_log, 3)

        # Log buttons (placed side-by-side to save vertical space)
        h_log_buttons = QHBoxLayout()
        self.btn_log_dir = QPushButton(t("btn.change_log_dir"))
        self._reg_icon(self.btn_log_dir, 'fa5s.folder')
        self.btn_log_dir.clicked.connect(self.choose_log_dir)
        self.btn_log_dir.setFixedWidth(180)
        btn_clear_log = QPushButton(t("btn.clear_log"))
        self._reg_icon(btn_clear_log, 'fa5s.eraser')
        btn_clear_log.clicked.connect(self.clear_log)
        btn_clear_log.setFixedWidth(140)
        h_log_buttons.addWidget(self.btn_log_dir)
        h_log_buttons.addWidget(btn_clear_log)
        h_log_buttons.addStretch()
        main_layout.addLayout(h_log_buttons)

    def show_about(self):
        AboutDialog(self).exec()

    def browse_folder(self, combo):
        folder = QFileDialog.getExistingDirectory(self, t("dialog.choose_folder"), combo.currentText())
        if folder:
            combo.setCurrentText(os.path.normpath(folder))

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        urls = event.mimeData().urls()
        if urls:
            path = urls[0].toLocalFile()
            if self.sender() == self.cmb_source:
                self.cmb_source.setCurrentText(path)
            else:
                self.cmb_target.setCurrentText(path)
            event.acceptProposedAction()

    def _set_busy(self, busy):
        """Locks/unlocks the input widgets while a job is running. btn_cancel
        is deliberately excluded, so a running job can always be cancelled."""
        for w in self._lockable_widgets:
            w.setEnabled(not busy)

    def get_log_file(self):
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir)
            except:
                pass
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return os.path.join(self.log_dir, f"robocopy_{timestamp}.log")

    def append_log(self, text, color_type="DEFAULT"):
        colors = LOG_COLORS[self.theme]
        color = colors.get(color_type, colors["DEFAULT"])
        weight = "bold" if color_type == "SUMMARY_BOLD" else "normal"
        safe_text = text.replace(" ", "&nbsp;")
        self.txt_log.append(f'<span style="color:{color}; font-weight:{weight};">{safe_text}</span>')
        self.txt_log.verticalScrollBar().setValue(self.txt_log.verticalScrollBar().maximum())
        if self.chk_log.isChecked() and hasattr(self, 'current_log_file'):
            try:
                with open(self.current_log_file, "a", encoding="utf-8") as f:
                    f.write(text + "\n")
            except:
                pass

    def run_robo(self, name, params):
        """Interactive wrapper for the five direct action buttons.

        Reads source/target/options from the form fields, shows the usual
        confirmation dialogs and delegates the actual execution to
        `execute_job` (also used by the task queue).
        """
        src = self.cmb_source.currentText().strip()
        dst = self.cmb_target.currentText().strip()
        if not self.validate_paths():
            return
        if not src or not dst:
            QMessageBox.warning(self, t("msg.error_title"), t("msg.select_paths"))
            return
        # Check whether ACL copying was requested and ask for rights if needed
        if self.chk_acl.isChecked():
            reply = QMessageBox.question(
                self, t("msg.acl_confirm_title"), t("msg.acl_confirm_text"),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.chk_acl.setChecked(False)
            else:
                if not is_admin():
                    reply = QMessageBox.question(
                        self, t("msg.acl_missing_rights_title"), t("msg.acl_missing_rights_text"),
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
                    )
                    if reply == QMessageBox.StandardButton.Yes:
                        restart_as_admin()
                        return
                    else:
                        self.chk_acl.setChecked(False)
        self.save_config(src, dst)
        self.execute_job(
            name, src, dst, list(params), self.spin_days.value(),
            acl=self.chk_acl.isChecked(),
            verbose=self.chk_verbose.isChecked(),
            log_enabled=self.chk_log.isChecked(),
            interactive=True,
            clear_log_widget=True,
            on_finished=self.job_finished,
        )

    def execute_job(self, name, src, dst, params, days, acl, verbose, log_enabled,
                     interactive=True, clear_log_widget=True, on_finished=None):
        """Runs a single Robocopy job.

        `interactive=False` (task queue) suppresses dialogs: a missing
        target is created silently, a missing source or missing ACL rights
        result in a log line instead of a modal prompt.
        """
        if not interactive:
            if not os.path.exists(src):
                self.append_log(t("log.source_missing", src=src), "ERROR")
                if on_finished:
                    on_finished(name, -1)
                return
            if not os.path.exists(dst):
                try:
                    os.makedirs(dst, exist_ok=True)
                    self.append_log(t("log.target_created", dst=dst), "WARNING")
                except Exception as e:
                    self.append_log(t("log.target_create_failed", error=e), "ERROR")
                    if on_finished:
                        on_finished(name, -1)
                    return
            if acl and not is_admin():
                self.append_log(t("log.acl_skipped"), "WARNING")
                acl = False

        if acl:
            params.append("/COPYALL")
        else:
            params.append("/COPY:DAT")

        if days > 0:
            date_str = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
            params.append(f"/MAXAGE:{date_str}")

        # If logging is enabled, prepare the file name and start Robocopy so
        # its output also gets written to a log file.
        if log_enabled:
            self.current_log_file = self.get_log_file()
            params.append(f'/LOG+:{self.current_log_file}')
            params.append("/TEE")

        if verbose:
            params.append("/V")
        params.append("/NP")

        cmd = ["robocopy", src, dst] + params

        if clear_log_widget:
            self.txt_log.clear()
        self.lbl_status.setText(t("status.running", name=name))
        self.progress.setRange(0, 0)
        self.btn_cancel.setEnabled(True)

        self.append_log("="*60, "HEADER")
        self.append_log(t("log.job_start", name=name, time=datetime.datetime.now().strftime('%H:%M:%S')), "HEADER")
        self.append_log(t("log.source", src=src), "DEFAULT")
        self.append_log(t("log.target", dst=dst), "DEFAULT")
        if days > 0:
            self.append_log(t("log.filter", days=days), "WARNING")
        self.append_log("="*60, "HEADER")

        self.worker = RobocopyWorker(cmd)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(lambda code: self._job_done(name, code, on_finished))
        self.worker.start()
        self._set_busy(True)

    def _job_done(self, name, code, on_finished):
        self._set_busy(False)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        success = code is not None and 0 <= code < 8
        self.append_log(t("log.job_done", name=name, code=code), "HEADER" if success else "ERROR")
        self.progress.setValue(0)
        self.lbl_status.setText(t("status.ready"))
        self.btn_cancel.setEnabled(False)
        if on_finished:
            on_finished(name, code)

    def job_finished(self, name, code):
        success = code is not None and 0 <= code < 8
        if success:
            QMessageBox.information(self, t("msg.job_done_title"), t("msg.job_done_text", name=name))
        else:
            QMessageBox.warning(self, t("msg.job_error_title"), t("msg.job_error_text", name=name, code=code))

    def action_mirror(self):
        days = self.spin_days.value()
        msg = t("msg.mirror_warning")
        if days > 0:
            msg += t("msg.mirror_filter_warning", days=days)
        if QMessageBox.question(self, t("msg.critical_warning_title"), msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.run_robo(action_label("Mirror"), list(ACTION_PARAMS["Mirror"]))

    def action_purge(self):
        if QMessageBox.question(self, t("msg.warning_title"), t("msg.purge_warning"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.run_robo(action_label("Purge"), list(ACTION_PARAMS["Purge"]))

    def delete_by_date(self):
        target = self.cmb_target.currentText()
        if not os.path.exists(target):
            return
        target_date = self.date_edit.date().toPyDate()
        if QMessageBox.question(self, t("msg.trash_confirm_title"), t("msg.trash_by_date_confirm", target=target, date=target_date), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            count = 0
            # Start the delete operation; log progress
            self.txt_log.clear()
            self.append_log(t("log.trash_by_date_start", date=target_date), "HEADER")
            for root, dirs, files in os.walk(target):
                for file in files:
                    full_path = os.path.join(root, file)
                    try:
                        if datetime.date.fromtimestamp(os.path.getmtime(full_path)) == target_date:
                            send2trash(full_path)
                            self.append_log(t("log.trashed", path=full_path), "WARNING")
                            count += 1
                    except Exception as e:
                        self.append_log(t("log.error_generic", error=e), "ERROR")
            self.append_log(t("log.trash_done", count=count), "SUMMARY")
            QMessageBox.information(self, t("msg.info_title"), t("msg.trash_done_text", count=count))

    def delete_by_name(self):
        target = self.cmb_target.currentText()
        pattern = self.txt_pattern.text().strip()
        if not os.path.exists(target) or not pattern:
            return
        if QMessageBox.warning(self, t("msg.security_warning_title"), t("msg.trash_by_name_confirm", target=target, pattern=pattern), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            count = 0
            self.txt_log.clear()
            self.append_log(t("log.trash_by_name_start", pattern=pattern), "HEADER")
            for root, dirs, files in os.walk(target):
                for file in files:
                    if pattern.lower() in file.lower():
                        full_path = os.path.join(root, file)
                        try:
                            send2trash(full_path)
                            self.append_log(t("log.trashed", path=full_path), "WARNING")
                            count += 1
                        except Exception as e:
                            self.append_log(t("log.error_generic", error=e), "ERROR")
            self.append_log(t("log.trash_done", count=count), "SUMMARY")
            QMessageBox.information(self, t("msg.info_title"), t("msg.trash_done_text", count=count))

    def load_config(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
                    for item in data:
                        self.cmb_source.addItem(item['SourcePath'])
                        self.cmb_target.addItem(item['TargetPath'])
            except:
                pass

        # Load saved tasks (if any)
        try:
            if os.path.exists(TASKS_FILE):
                with open(TASKS_FILE, 'r', encoding='utf-8') as tf:
                    self.queue_tasks = json.load(tf)
        except Exception:
            # Not critical - tasks then start out empty
            pass

        # Load saved task groups (if any)
        try:
            if os.path.exists(TASK_GROUPS_FILE):
                with open(TASK_GROUPS_FILE, 'r', encoding='utf-8') as gf:
                    self.task_groups = json.load(gf)
        except Exception:
            pass

        self._migrate_legacy_presets()

    def _migrate_legacy_presets(self):
        """One-time migration: the former "presets" feature (presets.json)
        was a separate concept that got replaced by the tasks list. To avoid
        losing presets the user had already saved, they are imported here as
        regular tasks (default action "Update"). Runs only once: presets.json
        is renamed afterwards so it isn't re-imported on every start."""
        if not os.path.exists(LEGACY_PRESETS_FILE):
            return
        try:
            with open(LEGACY_PRESETS_FILE, 'r', encoding='utf-8') as pf:
                legacy_presets = json.load(pf)
            existing_names = {t['name'] for t in self.queue_tasks}
            imported = 0
            for name, p in legacy_presets.items():
                if name in existing_names:
                    continue
                self.queue_tasks.append({
                    "name": name,
                    "action": "Update",
                    "source": p.get("source", ""),
                    "target": p.get("target", ""),
                    "days": p.get("days", 0),
                    "acl": p.get("acl", False),
                    "verbose": p.get("verbose", False),
                    "log": p.get("log", False),
                })
                imported += 1
            if imported:
                self.save_tasks()
            os.replace(LEGACY_PRESETS_FILE, LEGACY_PRESETS_FILE + ".migrated")
        except Exception as e:
            print(f"Could not migrate legacy presets: {e}")

    # load_config: reads recently used path pairs from the config file and
    # fills the dropdowns. Errors are silently ignored (not critical).

    def save_config(self, src, dst):
        data = []
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, 'r') as f:
                    data = json.load(f)
            except:
                pass
        data = [x for x in data if x['SourcePath'] != src or x['TargetPath'] != dst]
        data.insert(0, {"SourcePath": src, "TargetPath": dst})
        data = data[:10]
        if not os.path.exists(os.path.dirname(CONFIG_FILE)):
            os.makedirs(os.path.dirname(CONFIG_FILE))
        with open(CONFIG_FILE, 'w') as f:
            json.dump(data, f)

    def sync_target_combo(self, index):
        if self.cmb_target.count() > index:
            self.cmb_target.setCurrentIndex(index)

    def validate_paths(self):
        src = self.cmb_source.currentText().strip()
        dst = self.cmb_target.currentText().strip()
        if not os.path.exists(src):
            QMessageBox.warning(self, t("msg.error_title"), t("msg.source_missing", src=src))
            return False
        if not os.path.exists(dst):
            reply = QMessageBox.question(
                self, t("msg.target_missing_title"), t("msg.target_missing_text", dst=dst),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(dst, exist_ok=True)
                except Exception as e:
                    QMessageBox.warning(self, t("msg.error_title"), t("msg.target_create_failed", error=e))
                    return False
        return True

    # --- Tasks: persistence + queue execution -----------------------------
    # Editing (save/load/delete/order) happens in the separate
    # TaskManagerDialog (see open_task_manager), which operates directly on
    # self.queue_tasks and calls save_tasks().

    def open_task_manager(self):
        if getattr(self, '_task_dialog', None) is None:
            self._task_dialog = TaskManagerDialog(self)
        self._task_dialog.refresh_list()
        self._task_dialog.refresh_groups()
        self._task_dialog.show()
        self._task_dialog.raise_()
        self._task_dialog.activateWindow()

    def save_tasks(self):
        try:
            os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
            with open(TASKS_FILE, 'w', encoding='utf-8') as tf:
                json.dump(self.queue_tasks, tf, ensure_ascii=False, indent=2)
        except Exception as e:
            self.append_log(f"WARNING: Could not save tasks: {e}", "WARNING")

    def save_task_groups(self):
        try:
            os.makedirs(os.path.dirname(TASK_GROUPS_FILE), exist_ok=True)
            with open(TASK_GROUPS_FILE, 'w', encoding='utf-8') as gf:
                json.dump(self.task_groups, gf, ensure_ascii=False, indent=2)
        except Exception as e:
            self.append_log(f"WARNING: Could not save task groups: {e}", "WARNING")

    def start_queue(self, tasks):
        """Runs the given tasks (a list of task dicts, in execution order)
        one after another. Called by TaskManagerDialog."""
        if not tasks:
            QMessageBox.information(self, t("msg.no_selection_title"), t("msg.no_selection_text"))
            return
        if hasattr(self, 'worker') and self.worker.isRunning():
            QMessageBox.warning(self, t("msg.already_running_title"), t("msg.already_running_text"))
            return

        destructive = [t_ for t_ in tasks if t_['action'] in ("Mirror", "Purge")]
        if destructive:
            names = "\n".join(f"- {t_['name']}" for t_ in destructive)
            reply = QMessageBox.question(
                self, t("msg.critical_warning_title"),
                t("msg.destructive_warning", count=len(destructive), names=names),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        self.txt_log.clear()
        self._active_run_tasks = tasks
        self.queue_pos = 0
        self.queue_results = []
        self.queue_running = True
        self._queue_total = len(self._active_run_tasks)
        self.append_log(t("log.queue_started", count=self._queue_total), "HEADER")
        self._run_next_queue_task()

    def _run_next_queue_task(self):
        if not self.queue_running:
            return
        if self.queue_pos >= len(self._active_run_tasks):
            self._finish_queue()
            return
        task = self._active_run_tasks[self.queue_pos]
        self.queue_pos += 1
        label = f"[{t('log.queue_label')} {self.queue_pos}/{self._queue_total}] {task['name']}"
        params = list(ACTION_PARAMS.get(task['action'], []))
        self.execute_job(
            label, task['source'], task['target'], params, task.get('days', 0),
            acl=task.get('acl', False),
            verbose=task.get('verbose', False),
            log_enabled=task.get('log', False),
            interactive=False,
            clear_log_widget=False,
            on_finished=self._on_queue_task_done,
        )

    def _on_queue_task_done(self, name, code):
        success = code is not None and 0 <= code < 8
        self.queue_results.append((name, success, code))
        if not self.queue_running:
            return
        self._run_next_queue_task()

    def _finish_queue(self):
        self.queue_running = False
        ok_count = sum(1 for _, success, _ in self.queue_results if success)
        fail_count = len(self.queue_results) - ok_count
        status = "HEADER" if fail_count == 0 else "ERROR"
        self.append_log(t("log.queue_finished", ok=ok_count, fail=fail_count), status)
        lines = [f"{t('queue.ok_label') if s else t('queue.fail_label')} - {n} (Code {c})" for n, s, c in self.queue_results]
        QMessageBox.information(
            self, t("msg.queue_done_title"),
            t("msg.queue_done_text", ok=ok_count, fail=fail_count, lines="\n".join(lines))
        )

    def cancel_robo(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            self.append_log(t("log.cancelled"), "ERROR")
            self.btn_cancel.setEnabled(False)
            self._set_busy(False)
            self.progress.setValue(0)
            self.lbl_status.setText(t("status.cancelled"))
            if self.queue_running:
                self.queue_running = False
                self.append_log(t("log.queue_cancelled", pos=self.queue_pos, total=self._queue_total), "ERROR")

    # cancel_robo: makes sure the background process (and, if applicable, a
    # running task queue) is stopped and the UI is active again.

    def choose_log_dir(self):
        dir = QFileDialog.getExistingDirectory(self, t("dialog.choose_log_dir"), self.log_dir)
        if dir:
            self.log_dir = dir
            self._update_log_checkbox_text()

    def _update_log_checkbox_text(self):
        """Shows the log path elided in the checkbox (full path in the
        tooltip), so a very long, freely chosen folder path doesn't
        uncontrollably inflate the window's minimum width."""
        prefix = t("chk.log_prefix")
        metrics = QFontMetrics(self.chk_log.font())
        elided_path = metrics.elidedText(self.log_dir, Qt.TextElideMode.ElideMiddle, 260)
        self.chk_log.setText(prefix + elided_path)
        self.chk_log.setToolTip(t("tooltip.log", dir=self.log_dir))

    def clear_log(self):
        self.txt_log.clear()

class TaskManagerDialog(QDialog):
    """Standalone window for task management: create, edit, delete, sort via
    drag & drop and run a selection as a queue. Operates directly on
    main_window.queue_tasks; the actual execution (execute_job/
    _run_next_queue_task/...) stays in MainWindow so the log area and
    progress are visible there."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle(t("taskdlg.title"))
        if not main_window.windowIcon().isNull():
            self.setWindowIcon(main_window.windowIcon())
        self.resize(820, 520)
        # No fixed setMinimumSize: like MainWindow, Qt should compute the
        # content-correct minimum size from the layout itself instead of
        # clipping content with a guessed number.
        self._themed_icons = []  # (widget, icon_name) - see _reg_icon/refresh_theme_icons

        outer = QVBoxLayout(self)

        content = QHBoxLayout()
        content.setSpacing(12)

        # Left side: list of saved tasks
        left = QVBoxLayout()
        lbl_hint = QLabel(t("taskdlg.hint"))
        lbl_hint.setWordWrap(True)
        left.addWidget(lbl_hint)

        self.list_tasks = QListWidget()
        self.list_tasks.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.list_tasks.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.list_tasks.model().rowsMoved.connect(self._on_reordered)
        self.list_tasks.currentItemChanged.connect(self._on_current_changed)
        self.list_tasks.itemSelectionChanged.connect(self._update_queue_button_label)
        left.addWidget(self.list_tasks, 1)

        row_left_buttons = QHBoxLayout()
        btn_new = QPushButton(t("btn.new"))
        self._reg_icon(btn_new, 'fa5s.plus-circle')
        btn_new.setToolTip(t("tooltip.new_task"))
        btn_new.clicked.connect(self.new_task)
        btn_delete = QPushButton(t("btn.delete"))
        self._reg_icon(btn_delete, 'fa5s.trash')
        btn_delete.setToolTip(t("tooltip.delete_tasks"))
        btn_delete.clicked.connect(self.delete_selected)
        row_left_buttons.addWidget(btn_new)
        row_left_buttons.addWidget(btn_delete)
        left.addLayout(row_left_buttons)

        # Groups: a named, saved selection of multiple tasks (referenced by
        # name, not copied) - "Apply group" only selects the matching tasks
        # in the list above; starting the run still requires the separate
        # "Start queue" click.
        grp_groups = QGroupBox(t("group.groups"))
        layout_groups = QVBoxLayout()
        layout_groups.setSpacing(6)

        self.cmb_group = QComboBox()
        self.cmb_group.setEditable(True)
        self.cmb_group.setToolTip(t("tooltip.group_combo"))
        # activated (not currentTextChanged) only fires on an actual
        # selection from the dropdown, not on every keystroke while typing a
        # new name - selects the matching tasks right away, without also
        # having to click "Apply".
        self.cmb_group.activated.connect(self.apply_group)
        layout_groups.addWidget(self.cmb_group)

        row_group_buttons = QHBoxLayout()
        btn_group_save = QPushButton(t("btn.save"))
        self._reg_icon(btn_group_save, 'fa5s.layer-group')
        btn_group_save.setToolTip(t("tooltip.group_save"))
        btn_group_save.clicked.connect(self.save_group)
        btn_group_apply = QPushButton(t("btn.apply"))
        self._reg_icon(btn_group_apply, 'fa5s.check-square')
        btn_group_apply.setToolTip(t("tooltip.group_apply"))
        btn_group_apply.clicked.connect(self.apply_group)
        btn_group_delete = QPushButton(t("btn.delete"))
        self._reg_icon(btn_group_delete, 'fa5s.trash')
        btn_group_delete.setToolTip(t("tooltip.group_delete"))
        btn_group_delete.clicked.connect(self.delete_group)
        row_group_buttons.addWidget(btn_group_save)
        row_group_buttons.addWidget(btn_group_apply)
        row_group_buttons.addWidget(btn_group_delete)
        layout_groups.addLayout(row_group_buttons)

        grp_groups.setLayout(layout_groups)
        left.addWidget(grp_groups)

        content.addLayout(left, 1)

        # Right side: form for creating/editing a task
        right = QVBoxLayout()
        grp_form = QGroupBox(t("group.task_form"))
        form = QVBoxLayout()
        form.setSpacing(8)

        row_name = QHBoxLayout()
        row_name.addWidget(QLabel(t("label.name")))
        self.txt_name = QLineEdit()
        row_name.addWidget(self.txt_name)
        form.addLayout(row_name)

        row_action = QHBoxLayout()
        row_action.addWidget(QLabel(t("label.action")))
        self.cmb_action = QComboBox()
        # Display text is the translated label; the underlying stable key
        # (used for JSON persistence / ACTION_PARAMS lookup) is stored as
        # item data - see action_label().
        for action_key in ACTION_PARAMS.keys():
            self.cmb_action.addItem(action_label(action_key), action_key)
        row_action.addWidget(self.cmb_action)
        row_action.addStretch()
        form.addLayout(row_action)

        row_src = QHBoxLayout()
        row_src.addWidget(QLabel(t("label.source_short")))
        self.txt_source = QLineEdit()
        btn_src = QPushButton()
        self._reg_icon(btn_src, 'fa5s.folder-open')
        btn_src.setToolTip(t("tooltip.browse"))
        btn_src.clicked.connect(lambda: self._browse(self.txt_source))
        row_src.addWidget(self.txt_source)
        row_src.addWidget(btn_src)
        form.addLayout(row_src)

        row_dst = QHBoxLayout()
        row_dst.addWidget(QLabel(t("label.target_short")))
        self.txt_target = QLineEdit()
        btn_dst = QPushButton()
        self._reg_icon(btn_dst, 'fa5s.folder-open')
        btn_dst.setToolTip(t("tooltip.browse"))
        btn_dst.clicked.connect(lambda: self._browse(self.txt_target))
        row_dst.addWidget(self.txt_target)
        row_dst.addWidget(btn_dst)
        form.addLayout(row_dst)

        row_days = QHBoxLayout()
        row_days.addWidget(QLabel(t("label.file_age")))
        self.spin_days = QSpinBox()
        self.spin_days.setRange(0, 9999)
        row_days.addWidget(self.spin_days)
        row_days.addWidget(QLabel(t("label.days_suffix")))
        row_days.addStretch()
        form.addLayout(row_days)

        self.chk_acl = QCheckBox(t("chk.acl"))
        self.chk_verbose = QCheckBox(t("chk.verbose"))
        self.chk_log = QCheckBox(t("chk.log_simple"))
        form.addWidget(self.chk_acl)
        form.addWidget(self.chk_verbose)
        form.addWidget(self.chk_log)
        form.addStretch()

        grp_form.setLayout(form)
        right.addWidget(grp_form, 1)

        btn_save = QPushButton(t("btn.save"))
        self._reg_icon(btn_save, 'fa5s.save')
        btn_save.setObjectName("btn_blue")
        btn_save.setToolTip(t("tooltip.save_task"))
        btn_save.clicked.connect(self.save_current)
        right.addWidget(btn_save)

        content.addLayout(right, 1)
        outer.addLayout(content, 1)

        footer = QHBoxLayout()
        self.btn_start_queue = QPushButton(t("btn.start_queue"))
        self.btn_start_queue.setIcon(icon('fa5s.play', color='white'))
        self.btn_start_queue.setObjectName("btn_blue")
        self.btn_start_queue.setToolTip(t("tooltip.start_queue"))
        self.btn_start_queue.clicked.connect(self.start_selected_queue)
        btn_close = QPushButton(t("btn.close"))
        self._reg_icon(btn_close, 'fa5s.times-circle')
        btn_close.clicked.connect(self.close)
        footer.addWidget(self.btn_start_queue)
        footer.addStretch()
        footer.addWidget(btn_close)
        outer.addLayout(footer)

        self.new_task()
        self.refresh_list()
        self.refresh_groups()

    def _reg_icon(self, widget, name, color=None):
        """Like MainWindow._reg_icon: sets a theme-dependent qtawesome icon
        and remembers it for refresh_theme_icons() (the color comes from
        main_window's current theme default)."""
        widget.setIcon(icon(name, color=color or self.main_window._icon_color()))
        if color is None:
            self._themed_icons.append((widget, name))
        return widget

    def refresh_theme_icons(self):
        c = self.main_window._icon_color()
        for widget, name in self._themed_icons:
            widget.setIcon(icon(name, color=c))

    def _browse(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, t("dialog.choose_folder"), line_edit.text())
        if folder:
            line_edit.setText(os.path.normpath(folder))

    def new_task(self):
        self.list_tasks.setCurrentRow(-1)
        self.txt_name.clear()
        self.txt_source.clear()
        self.txt_target.clear()
        self.spin_days.setValue(0)
        self.chk_acl.setChecked(False)
        self.chk_verbose.setChecked(False)
        self.chk_log.setChecked(False)
        self.cmb_action.setCurrentIndex(0)
        self.txt_name.setFocus()

    def _on_current_changed(self, current, previous):
        if current is None:
            return
        t_ = current.data(Qt.ItemDataRole.UserRole)
        self.txt_name.setText(t_["name"])
        self.cmb_action.setCurrentIndex(self.cmb_action.findData(t_["action"]))
        self.txt_source.setText(t_["source"])
        self.txt_target.setText(t_["target"])
        self.spin_days.setValue(t_.get("days", 0))
        self.chk_acl.setChecked(t_.get("acl", False))
        self.chk_verbose.setChecked(t_.get("verbose", False))
        self.chk_log.setChecked(t_.get("log", False))

    def save_current(self):
        src = self.txt_source.text().strip()
        dst = self.txt_target.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, t("msg.error_title"), t("msg.select_paths"))
            return
        name = self.txt_name.text().strip()
        if not name:
            name = f"{self.cmb_action.currentText()}: {src} → {dst}"
            self.txt_name.setText(name)
        task = {
            "name": name,
            "action": self.cmb_action.currentData(),
            "source": src,
            "target": dst,
            "days": self.spin_days.value(),
            "acl": self.chk_acl.isChecked(),
            "verbose": self.chk_verbose.isChecked(),
            "log": self.chk_log.isChecked(),
        }
        tasks = self.main_window.queue_tasks
        existing_index = next((i for i, t_ in enumerate(tasks) if t_['name'] == name), None)
        if existing_index is not None:
            tasks[existing_index] = task
        else:
            tasks.append(task)
        self.main_window.save_tasks()
        self.refresh_list(select_name=name)

    def delete_selected(self):
        items = self.list_tasks.selectedItems()
        if not items:
            QMessageBox.warning(self, t("msg.error_title"), t("msg.select_tasks"))
            return
        names = [it.data(Qt.ItemDataRole.UserRole)['name'] for it in items]
        reply = QMessageBox.question(
            self, t("msg.delete_tasks_confirm_title"),
            t("msg.delete_tasks_confirm_text", names="\n".join(f"- {n}" for n in names)),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.main_window.queue_tasks = [t_ for t_ in self.main_window.queue_tasks if t_['name'] not in names]
            self.main_window.save_tasks()
            self.new_task()
            self.refresh_list()

    # --- Groups: named, ordered task selection (referenced by name) ---

    def save_group(self):
        name = self.cmb_group.currentText().strip()
        if not name:
            QMessageBox.warning(self, t("msg.error_title"), t("msg.group_name_missing"))
            return
        items = sorted(self.list_tasks.selectedItems(), key=lambda it: self.list_tasks.row(it))
        if not items:
            QMessageBox.warning(self, t("msg.error_title"), t("msg.group_needs_tasks"))
            return
        task_names = [it.data(Qt.ItemDataRole.UserRole)['name'] for it in items]
        groups = self.main_window.task_groups
        existing_index = next((i for i, g in enumerate(groups) if g['name'] == name), None)
        group = {"name": name, "tasks": task_names}
        if existing_index is not None:
            groups[existing_index] = group
        else:
            groups.append(group)
        self.main_window.save_task_groups()
        self.refresh_groups(select_name=name)

    def apply_group(self):
        name = self.cmb_group.currentText().strip()
        group = next((g for g in self.main_window.task_groups if g['name'] == name), None)
        if group is None:
            QMessageBox.warning(self, t("msg.error_title"), t("msg.group_invalid"))
            return
        wanted = set(group['tasks'])
        available_names = {t_['name'] for t_ in self.main_window.queue_tasks}
        missing = [n for n in group['tasks'] if n not in available_names]
        self.list_tasks.clearSelection()
        for i in range(self.list_tasks.count()):
            item = self.list_tasks.item(i)
            if item.data(Qt.ItemDataRole.UserRole)['name'] in wanted:
                item.setSelected(True)
        self._update_queue_button_label()
        if missing:
            self.main_window.append_log(
                t("log.group_missing_tasks", name=name, missing=", ".join(missing)),
                "WARNING"
            )

    def delete_group(self):
        name = self.cmb_group.currentText().strip()
        groups = self.main_window.task_groups
        if not name or not any(g['name'] == name for g in groups):
            QMessageBox.warning(self, t("msg.error_title"), t("msg.group_invalid_delete"))
            return
        reply = QMessageBox.question(
            self, t("msg.delete_group_confirm_title"), t("msg.delete_group_confirm_text", name=name),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.main_window.task_groups = [g for g in groups if g['name'] != name]
            self.main_window.save_task_groups()
            self.refresh_groups()

    def refresh_groups(self, select_name=None):
        self.cmb_group.clear()
        self.cmb_group.addItems([g['name'] for g in self.main_window.task_groups])
        if select_name is not None:
            self.cmb_group.setCurrentText(select_name)

    def refresh_list(self, select_name=None):
        selected_names = (
            {select_name} if select_name is not None
            else {it.data(Qt.ItemDataRole.UserRole)['name'] for it in self.list_tasks.selectedItems()}
        )
        self.list_tasks.blockSignals(True)
        self.list_tasks.clear()
        for t_ in self.main_window.queue_tasks:
            item = QListWidgetItem(f"[{action_label(t_['action'])}] {t_['name']}  ({t_['source']} → {t_['target']})")
            item.setData(Qt.ItemDataRole.UserRole, t_)
            self.list_tasks.addItem(item)
            if t_['name'] in selected_names:
                item.setSelected(True)
                self.list_tasks.setCurrentItem(item)
        self.list_tasks.blockSignals(False)
        self._update_queue_button_label()

    def _on_reordered(self):
        # After drag & drop: rebuild the order from the current display
        # order and persist it to main_window.queue_tasks.
        reordered = []
        for i in range(self.list_tasks.count()):
            data = self.list_tasks.item(i).data(Qt.ItemDataRole.UserRole)
            if data is not None:
                reordered.append(data)
        self.main_window.queue_tasks = reordered
        self.main_window.save_tasks()

    def _update_queue_button_label(self):
        count = len(self.list_tasks.selectedItems())
        if count > 0:
            self.btn_start_queue.setText(t("btn.start_queue_n", count=count))
        else:
            self.btn_start_queue.setText(t("btn.start_queue"))

    def start_selected_queue(self):
        selected_items = sorted(self.list_tasks.selectedItems(), key=lambda it: self.list_tasks.row(it))
        tasks = [it.data(Qt.ItemDataRole.UserRole) for it in selected_items]
        self.main_window.start_queue(tasks)

if __name__ == "__main__":
    # Start the application
    app = QApplication(sys.argv)

    # Try to load a splash image. If present, show it briefly, otherwise
    # open the main window directly.
    app_icon_path = resource_path(LOGO_FILENAME)
    if os.path.exists(app_icon_path):
        app.setWindowIcon(QIcon(app_icon_path))
        pixmap = QPixmap(app_icon_path)
        if not pixmap.isNull():
            if pixmap.width() > 500:
                pixmap = pixmap.scaledToWidth(500, Qt.TransformationMode.SmoothTransformation)
            splash = QSplashScreen(pixmap, Qt.WindowType.WindowStaysOnTopHint)
            splash.show()
            def start_main():
                global window
                window = MainWindow()
                window.show()
                splash.finish(window)
            # Show the splash for 1.5 seconds before opening the main window
            QTimer.singleShot(1500, start_main)
        else:
            window = MainWindow()
            window.show()
    else:
        window = MainWindow()
        window.show()
    # Main event loop
    sys.exit(app.exec())
