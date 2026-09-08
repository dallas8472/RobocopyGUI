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
Dieses Modul stellt eine einfache grafische Oberfläche für das Windows-Tool
`robocopy` bereit. Die Anwendung ist mit PyQt6 implementiert und startet
Robocopy-Aufrufe in einem separaten Thread, liest die Ausgabe und zeigt ein
formatierbares Log im UI an. Das Script ist so aufgebaut, dass es sich gut
mit PyInstaller in eine einzelne Windows-Exe verpacken lässt.

Kurzbeschreibung der Hauptbestandteile:
- `RobocopyWorker`: Hintergrundthread, der den Robocopy-Prozess startet und
    seine Ausgabe an die GUI weiterreicht.
- `MainWindow`: Hauptfenster mit allen Steuerelementen und Log-Anzeige.
- `AboutDialog`: kleines Info-Dialogfenster.

Hinweis: Kommentare und Docstrings sind auf Deutsch gehalten.
"""
from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QLineEdit, QPushButton, QCheckBox,
    QSpinBox, QGroupBox, QTextEdit, QProgressBar, QFileDialog,
    QMessageBox, QDateEdit, QSplashScreen, QDialog, QDialogButtonBox,
    QSpacerItem, QSizePolicy, QGridLayout,
    QListWidget, QListWidgetItem, QAbstractItemView
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QDate, QTimer, QSize
from PyQt6.QtGui import QFont, QColor, QIcon, QPixmap, QAction, QFontMetrics

try:
    import qtawesome as qta
except ImportError:
    qta = None

try:
    from send2trash import send2trash
except ImportError:
    # Fällt zurück auf permanentes Löschen, falls send2trash nicht installiert ist,
    # damit "Löschen nach Datum/Name" trotzdem funktionsfähig bleibt.
    send2trash = os.remove

def icon(name, color="#e0e0e0"):
    """Liefert ein qtawesome-Icon oder ein leeres QIcon, falls qtawesome
    fehlt oder der Icon-Name ungültig ist (z.B. bei älterer Font-Version).
    So bricht das UI nie wegen eines fehlenden Icons ab."""
    if qta is None:
        return QIcon()
    try:
        return qta.icon(name, color=color)
    except Exception:
        return QIcon()

# Configuration
APP_NAME = "Robocopy GUI"
VERSION = "2.1"
CONFIG_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'py_config.json')
LOGO_FILENAME = "logo.png"
TASKS_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'tasks.json')
# Alter Dateiname der früheren, separaten "Voreinstellungen"-Funktion - wird
# nur noch für die einmalige Migration nach TASKS_FILE gelesen (siehe
# MainWindow._migrate_legacy_presets).
LEGACY_PRESETS_FILE = os.path.join(os.getenv('APPDATA'), 'RobocopyGUI', 'presets.json')

# Layout constants
COL_WIDTH = 11
LABEL_WIDTH = 12

# Robocopy-Parametersätze je Aktionstyp. Wird sowohl von den Direct-Buttons
# als auch von der Task-Queue verwendet, damit es nur eine Quelle der
# Wahrheit für die eigentlichen Robocopy-Switches gibt.
ACTION_PARAMS = {
    "Struktur": ["/E", "/XF", "*", "/DCOPY:DAT", "/R:0", "/W:0"],
    "Update": ["/E", "/DCOPY:DAT", "/XO", "/R:1", "/W:1", "/MT:8", "/Z"],
    "Mirror": ["/MIR", "/DCOPY:DAT", "/R:1", "/W:1", "/MT:8", "/XJ", "/Z"],
    "Purge": ["/PURGE", "/E", "/XF", "*"],
    "Vergleich": ["/E", "/L", "/R:0"],
}

def resource_path(relative_path):
    """Get absolute path to resource, works for dev and for PyInstaller"""
    # Liefert den Pfad einer mitgelieferten Ressource (z.B. logo.png).
    # Bei ausgepackter PyInstaller-Exe existiert das temporäre Attribut
    # `sys._MEIPASS` und muss beim Zugriff berücksichtigt werden.
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

def is_admin():
    """Check if the script is running with admin privileges"""
    # Auf Unix-Systemen würde os.geteuid() funktionieren; unter Windows
    # verwenden wir die Shell32-API, um festzustellen, ob der Benutzer
    # Administratorrechte besitzt.
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
        # Startet das aktuelle Python-Executable mit dem Parameter für
        # das Script neu und fordert die UAC-Dialogbox an (Verbesserung
        # für Windows-Umgebungen).
        ctypes.windll.shell32.ShellExecuteW(None, "runas", executable, params, None, 1)
        sys.exit()
    except Exception as e:
        print(f"Failed to restart as admin: {e}")

class RobocopyWorker(QThread):
    """Hintergrund-Thread zum Ausführen von `robocopy`.

    Der Worker startet den Robocopy-Prozess mit den übergebenen Parametern,
    liest Zeile für Zeile die Ausgabe und sendet diese per Signal an die
    GUI, damit die Anzeige im Hauptthread aktualisiert werden kann.

    Hinweise:
    - Die Prozessausgabe wird im Encoding cp850 gelesen (übliches OEM-Encoding
      auf deutschen Windows-Systemen).
    - Bei Fehlern wird eine entsprechende Meldung an die GUI gesendet.
    """
    log_signal = pyqtSignal(str, str)
    finished_signal = pyqtSignal(int)

    def __init__(self, command):
        super().__init__()
        # `command` ist eine Liste wie ["robocopy", src, dst, ...]
        self.command = command
        self.process = None

    def run(self):
        try:
            # Robocopy im Hintergrund starten und stdout lesen
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

                # Versuche, Zusammenfassungsblöcke (engl./deut.) zu erkennen
                if "Insgesamt" in line or ("Total" in line and "Kopiert" in line):
                    in_summary = True
                    self.log_signal.emit("-" * (LABEL_WIDTH + (6 * (COL_WIDTH+3))), "DEFAULT")
                    header = f"{'Typ':<{LABEL_WIDTH}} {'Total':>{COL_WIDTH}} {'Kopiert':>{COL_WIDTH}} {'Überspr.':>{COL_WIDTH}} {'Mismatch':>{COL_WIDTH}} {'FEHLER':>{COL_WIDTH}} {'Extras':>{COL_WIDTH}}"
                    self.log_signal.emit(header, "SUMMARY")
                    self.log_signal.emit("-" * (LABEL_WIDTH + (6 * (COL_WIDTH+3))), "DEFAULT")
                    continue

                # Innerhalb des Summary-Blocks formatierte Werte extrahieren
                if in_summary:
                    if "-----" in line:
                        continue

                    if ":" in line:
                        clean_line = line.strip()
                        label_mapping = {
                            "Verzeich": "Verzeich.:", "Dirs": "Verzeich.:",
                            "Dateien": "Dateien:", "Files": "Dateien:",
                            "Bytes": "Bytes:",
                            "Zeiten": "Zeiten:", "Times": "Zeiten:",
                            "Geschwind": None, "Speed": None,
                            "Beendet": None, "Ended": None
                        }

                        current_label = None
                        for key, val in label_mapping.items():
                            if key in clean_line:
                                current_label = val
                                break

                        if current_label:
                            vals = re.findall(r"(\d+:\d+:\d+|\d+(?:\.\d+)?\s*[tgmkTGMK]?)", clean_line)
                            if len(vals) >= 6:
                                v = vals[-6:]
                                formatted = f"{current_label:<{LABEL_WIDTH}} {v[0]:>{COL_WIDTH}} {v[1]:>{COL_WIDTH}} {v[2]:>{COL_WIDTH}} {v[3]:>{COL_WIDTH}} {v[4]:>{COL_WIDTH}} {v[5]:>{COL_WIDTH}}"
                                self.log_signal.emit(formatted, "SUMMARY_BOLD")
                                continue

                        if "Geschwind" in line or "Speed" in line or "Beendet" in line or "Ended" in line:
                            self.log_signal.emit(line.strip(), "SUMMARY")
                            continue

                # Filter einige Prozentzeilen
                if re.match(r"^\s*\d+%", line):
                    continue

                # Bestimme Farb-/Typ-Kategorie für die Anzeige
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

                # Ausgabe an GUI senden
                self.log_signal.emit(line, color_type)

            self.process.wait()
            self.finished_signal.emit(self.process.returncode if self.process.returncode is not None else 0)
        except Exception as e:
            self.log_signal.emit(f"FEHLER BEI AUSFÜHRUNG: {e}", "ERROR")
            self.finished_signal.emit(-1)

    def terminate(self):
        # Beende den Robocopy-Prozess falls aktiv und stoppe den Thread
        if hasattr(self, 'process') and self.process:
            self.process.terminate()
        super().terminate()

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        """Kleines Info-Dialogfenster mit App-Logo und Versionsangabe."""
        self.setWindowTitle("Info")
        self.setFixedWidth(400)
        self.setStyleSheet("background-color: #1e1e1e; color: #d4d4d4;")
        if parent:
            self.setWindowIcon(parent.windowIcon())
        layout = QVBoxLayout()
        lbl_logo = QLabel()
        pixmap = QPixmap(resource_path(LOGO_FILENAME))
        if not pixmap.isNull():
            lbl_logo.setPixmap(pixmap.scaled(250, 250, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            lbl_logo.setText(f"<b>{APP_NAME}</b>")
            lbl_logo.setStyleSheet("font-size: 18pt; color: #007acc;")
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_logo)

        layout.addSpacing(15)
        lbl_text = QLabel(f"Version {VERSION}<br><br>Modernes Interface für Robocopy.<br>Python & PyQt6 Edition")
        lbl_text.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(lbl_text)

        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        btn_box.accepted.connect(self.accept)
        btn_box.setStyleSheet("QPushButton { background-color: #3c3c3c; color: white; border: 1px solid #555; padding: 5px; width: 80px; border-radius: 6px; }")
        layout.addWidget(btn_box, alignment=Qt.AlignmentFlag.AlignCenter)
        self.setLayout(layout)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        """Hauptfenster der Anwendung.

        Enthält alle Bedienelemente zur Auswahl von Quell-/Zielpfaden, Optionen
        und die Log-Anzeige. Verantwortlich für das Starten des
        `RobocopyWorker`-Threads und das Verarbeiten der UI-Interaktionen.
        """
        self.log_dir = r"C:\tmp"
        mode_str = "[ADMIN]" if is_admin() else "[USER]"
        self.setWindowTitle(f"{APP_NAME} v{VERSION}  {mode_str}")
        self.resize(1150, 850)
        # Nur die Breite fest begrenzen (Lesbarkeit); die Höhe bleibt dem von
        # Qt aus dem Layout berechneten, inhaltlich korrekten Minimum
        # überlassen (siehe minimumSizeHint) - ein geratener fester Wert
        # hätte bei kleinem Fenster Zeilen abgeschnitten oder das Fenster
        # unnötig hoch erzwungen.
        self.setMinimumWidth(1000)

        # Tasks: persistente Liste gespeicherter Job-Definitionen
        # (name/action/source/target/days/acl/verbose/log), siehe TASKS_FILE.
        self.queue_tasks = []
        # Die tatsächlich für den aktuellen Warteschlangen-Lauf ausgewählten
        # Tasks (Teilmenge von queue_tasks, in Listreihenfolge) - siehe start_queue().
        self._active_run_tasks = []
        self.queue_pos = 0
        self.queue_results = []
        self.queue_running = False
        self._queue_total = 0
        self._task_dialog = None

        icon_path = resource_path(LOGO_FILENAME)
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        self.apply_styles()
        self.init_menu()
        self.init_ui()
        self.load_config()
        self.check_robocopy_available()

    def check_robocopy_available(self):
        """Prüft einmalig beim Start, ob robocopy.exe im PATH gefunden wird.
        robocopy ist normalerweise fester Bestandteil von Windows, kann aber
        z.B. in stark abgespeckten Windows-Umgebungen oder bei einem kaputten
        PATH fehlen. Ohne diesen Hinweis würde man den Fehler erst als rohe
        Python-Exception im Log sehen, sobald man einen Lauf startet."""
        if shutil.which("robocopy") is None:
            QMessageBox.warning(
                self, "robocopy nicht gefunden",
                "Das Programm \"robocopy.exe\" wurde im PATH nicht gefunden.\n\n"
                "robocopy ist normalerweise Teil von Windows - ohne dieses Tool "
                "kann diese Anwendung keine Kopier-/Löschvorgänge ausführen."
            )

    def apply_styles(self):
        self.setStyleSheet("""
            QMainWindow, QWidget { background-color: #1e1e1e; color: #e0e0e0; font-family: 'Segoe UI', sans-serif; font-size: 10pt; }
            QMenuBar { background-color: #252526; color: #e0e0e0; border-bottom: 1px solid #3e3e3e; padding: 2px; }
            QMenuBar::item { padding: 4px 10px; border-radius: 4px; }
            QMenuBar::item:selected { background-color: #3e3e3e; }
            QMenu { background-color: #252526; color: #e0e0e0; border: 1px solid #454545; padding: 4px; }
            QMenu::item { padding: 6px 24px 6px 12px; border-radius: 4px; }
            QMenu::item:selected { background-color: #007acc; color: white; }
            QToolTip { background-color: #2d2d2d; color: #f0f0f0; border: 1px solid #007acc; padding: 4px; border-radius: 4px; }
            QGroupBox { border: 1px solid #3a3a3a; border-radius: 8px; margin-top: 20px; font-weight: 600; background-color: #222222; }
            QGroupBox::title { subcontrol-origin: margin; left: 10px; padding: 0 6px; color: #4fb3e8; }
            QLabel { background: transparent; }
            QLineEdit, QComboBox, QDateEdit {
                background-color: #2b2b2b; border: 1px solid #3e3e3e; padding: 6px 8px;
                color: #f0f0f0; border-radius: 5px; selection-background-color: #007acc;
            }
            QLineEdit:focus, QComboBox:focus, QDateEdit:focus { border: 1px solid #4fb3e8; }
            QComboBox::drop-down { border: none; width: 22px; }
            QComboBox QAbstractItemView {
                background-color: #2b2b2b; color: #f0f0f0; border: 1px solid #454545;
                selection-background-color: #007acc; outline: 0;
            }
            QSpinBox { background-color: #2b2b2b; border: 1px solid #3e3e3e; padding: 4px; color: #f0f0f0; border-radius: 5px; min-height: 20px; }
            QSpinBox::up-button, QSpinBox::down-button { width: 22px; background-color: #3c3c3c; border: none; }
            QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #4a4a4a; }
            QCheckBox { spacing: 8px; }
            QCheckBox::indicator {
                width: 16px; height: 16px; border-radius: 4px;
                border: 1px solid #5a5a5a; background-color: #2b2b2b;
            }
            QCheckBox::indicator:hover { border: 1px solid #4fb3e8; }
            QCheckBox::indicator:checked { background-color: #007acc; border: 1px solid #007acc; }
            QCheckBox::indicator:disabled { background-color: #262626; border: 1px solid #3a3a3a; }
            QPushButton {
                background-color: #3c3c3c; border: 1px solid #454545; padding: 8px 16px;
                border-radius: 6px; color: white; font-weight: 600;
            }
            QPushButton:hover { background-color: #4a4a4a; border: 1px solid #5a5a5a; }
            QPushButton:pressed { background-color: #333333; }
            QPushButton:disabled { background-color: #2a2a2a; color: #777777; border: 1px solid #333333; }
            QPushButton#btn_blue { background-color: #007acc; border: 1px solid #007acc; }
            QPushButton#btn_blue:hover { background-color: #1f8ad2; }
            QPushButton#btn_blue:pressed { background-color: #006bb3; }
            QPushButton#btn_red { background-color: #c42b1c; border: 1px solid #c42b1c; }
            QPushButton#btn_red:hover { background-color: #d73a2d; }
            QPushButton#btn_red:pressed { background-color: #a92418; }
            QListWidget {
                background-color: #191919; border: 1px solid #3e3e3e; border-radius: 5px;
                color: #d4d4d4; outline: 0; padding: 2px;
            }
            QListWidget::item { padding: 4px 6px; border-radius: 4px; }
            QListWidget::item:selected { background-color: #007acc; color: white; }
            QListWidget::item:hover:!selected { background-color: #2d2d2d; }
            QTextEdit { background-color: #101010; color: #cccccc; border: 1px solid #3e3e3e; border-radius: 5px; font-family: 'Consolas', monospace; font-size: 10pt; }
            QProgressBar { border: 1px solid #3e3e3e; border-radius: 5px; text-align: center; background-color: #252526; }
            QProgressBar::chunk { background-color: #007acc; border-radius: 4px; }
            QLabel#status_label { color: #4fb3e8; font-weight: 600; font-size: 11pt; }
            QScrollBar:vertical { background: #1e1e1e; width: 12px; margin: 0; }
            QScrollBar::handle:vertical { background: #454545; min-height: 24px; border-radius: 5px; }
            QScrollBar::handle:vertical:hover { background: #5a5a5a; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
            QScrollBar:horizontal { background: #1e1e1e; height: 12px; margin: 0; }
            QScrollBar::handle:horizontal { background: #454545; min-width: 24px; border-radius: 5px; }
            QScrollBar::handle:horizontal:hover { background: #5a5a5a; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
        """)

    # apply_styles: definiert das Aussehen der Anwendung via Stylesheet

    def init_menu(self):
        menubar = self.menuBar()
        file_menu = menubar.addMenu('Datei')
        exit_action = QAction(icon('fa5s.sign-out-alt'), 'Beenden', self)
        exit_action.triggered.connect(self.close)
        file_menu.addAction(exit_action)

        tasks_menu = menubar.addMenu('Tasks')
        manage_tasks_action = QAction(icon('fa5s.list'), 'Tasks verwalten...', self)
        manage_tasks_action.triggered.connect(self.open_task_manager)
        tasks_menu.addAction(manage_tasks_action)

        admin_menu = menubar.addMenu('Admin-Modus')
        restart_action = QAction(icon('fa5s.user-shield'), 'Als Administrator neu starten', self)
        if is_admin():
            restart_action.setEnabled(False)
            restart_action.setText("Läuft bereits als Admin")
        else:
            restart_action.triggered.connect(restart_as_admin)
        admin_menu.addAction(restart_action)

        help_menu = menubar.addMenu('Hilfe')
        about_action = QAction(icon('fa5s.info-circle'), 'Über...', self)
        about_action.triggered.connect(self.show_about)
        help_menu.addAction(about_action)

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setSpacing(8)
        main_layout.setContentsMargins(16, 8, 16, 12)

        # Paths
        grp_paths = QGroupBox("Pfadauswahl")
        layout_paths = QVBoxLayout()
        layout_paths.setSpacing(8)

        def create_path_row(label_text, combo):
            row = QHBoxLayout()
            lbl = QLabel(label_text)
            lbl.setMinimumWidth(80)
            combo.setEditable(True)
            combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            btn = QPushButton(" Durchsuchen... ")
            btn.setIcon(icon('fa5s.folder-open'))
            btn.clicked.connect(lambda: self.browse_folder(combo))
            row.addWidget(lbl)
            row.addWidget(combo)
            row.addWidget(btn)
            return row

        self.cmb_source = QComboBox()
        self.cmb_source.setMinimumWidth(220)
        self.cmb_source.currentIndexChanged.connect(self.sync_target_combo)
        self.cmb_source.setToolTip("Wählen Sie den Quellordner für den Robocopy-Vorgang.")
        layout_paths.addLayout(create_path_row("Quellordner:", self.cmb_source))

        self.cmb_target = QComboBox()
        self.cmb_target.setMinimumWidth(220)
        self.cmb_target.setToolTip("Wählen Sie den Zielordner für den Robocopy-Vorgang.")
        layout_paths.addLayout(create_path_row("Zielordner:", self.cmb_target))

        grp_paths.setLayout(layout_paths)
        grp_paths.setMaximumHeight(160)
        main_layout.addWidget(grp_paths)

        # Options
        h_mid = QHBoxLayout()

        grp_opts = QGroupBox("Kopier-Optionen")
        layout_opts = QVBoxLayout()
        layout_opts.setSpacing(6)

        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Dateialter:"))
        self.spin_days = QSpinBox()
        self.spin_days.setRange(0, 9999)
        self.spin_days.setValue(0)
        self.spin_days.setToolTip("Kopiert nur Dateien, die jünger als die angegebene Anzahl von Tagen sind. 0 bedeutet alle Dateien.")
        r1.addWidget(self.spin_days)
        r1.addWidget(QLabel("Tage (0 = Alle)"))
        r1.addStretch()
        layout_opts.addLayout(r1)

        # ACL-Kopie: standardmäßig aus, erfordert Administratorrechte.
        # Wenn die Anwendung ohne Admin-Rechte läuft, wird die Checkbox
        # deaktiviert und ein Button angeboten, der zum Neustart als
        # Administrator auffordert.
        self.chk_acl = QCheckBox("Berechtigungen (ACLs) /COPYALL")
        self.chk_acl.setChecked(False)
        self.chk_acl.setToolTip("Kopiert Dateiberechtigungen (ACLs). Benötigt Administratorrechte.")
        layout_opts.addWidget(self.chk_acl)
        if not is_admin():
            self.chk_acl.setEnabled(False)
            self.chk_acl.setStyleSheet("color: #888;")
            # Eigene Zeile (statt neben der Checkbox), damit der lange
            # Checkbox-Text bei schmalem Fenster nicht mit dem Button kollidiert.
            h_acl = QHBoxLayout()
            btn_enable_acl = QPushButton(" Als Admin aktivieren")
            btn_enable_acl.setIcon(icon('fa5s.user-shield'))
            btn_enable_acl.setToolTip("Neustart als Administrator, um ACL-Kopie zu erlauben")
            btn_enable_acl.setFixedWidth(190)
            btn_enable_acl.setStyleSheet("QPushButton { padding: 6px 10px; }")
            btn_enable_acl.clicked.connect(restart_as_admin)
            h_acl.addWidget(btn_enable_acl)
            h_acl.addStretch()
            layout_opts.addLayout(h_acl)

        self.chk_verbose = QCheckBox("Alle Dateien anzeigen (Verbose /V)")
        self.chk_verbose.setToolTip("Zeigt auch übersprungene Dateien an. Füllt das Log!")
        layout_opts.addWidget(self.chk_verbose)

        self.chk_log = QCheckBox()
        # Default: do not create a log file unless the user enables it
        self.chk_log.setChecked(False)
        self._update_log_checkbox_text()
        layout_opts.addWidget(self.chk_log)

        grp_opts.setLayout(layout_opts)
        h_mid.addWidget(grp_opts, stretch=1)

        # Delete
        grp_del = QGroupBox("Spezial-Löschen (Ziel)")
        layout_del = QGridLayout()
        layout_del.setVerticalSpacing(8)

        self.date_edit = QDateEdit()
        self.date_edit.setDate(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setToolTip("Wählen Sie ein Datum, um Dateien im Zielordner zu löschen, die an diesem Datum geändert wurden.")
        btn_del_date = QPushButton(" Löschen nach Datum")
        btn_del_date.setIcon(icon('fa5s.calendar-times'))
        btn_del_date.clicked.connect(self.delete_by_date)
        btn_del_date.setToolTip("Verschiebt Dateien im Zielordner, die am ausgewählten Datum geändert wurden, in den Papierkorb.")
        layout_del.addWidget(QLabel("Datum:"), 0, 0)
        layout_del.addWidget(self.date_edit, 0, 1)
        layout_del.addWidget(btn_del_date, 0, 2)

        self.txt_pattern = QLineEdit()
        self.txt_pattern.setPlaceholderText("z.B. *temp*")
        self.txt_pattern.setToolTip("Geben Sie ein Muster ein (z.B. *temp*), um Dateien im Zielordner zu löschen, die diesem Muster entsprechen.")
        btn_del_name = QPushButton(" Löschen nach Name")
        btn_del_name.setIcon(icon('fa5s.eraser'))
        btn_del_name.clicked.connect(self.delete_by_name)
        btn_del_name.setToolTip("Verschiebt Dateien im Zielordner, deren Namen dem eingegebenen Muster entsprechen, in den Papierkorb.")
        layout_del.addWidget(QLabel("Muster:"), 1, 0)
        layout_del.addWidget(self.txt_pattern, 1, 1)
        layout_del.addWidget(btn_del_name, 1, 2)

        grp_del.setLayout(layout_del)
        h_mid.addWidget(grp_del, stretch=1)
        main_layout.addLayout(h_mid)

        # Actions
        grp_actions = QGroupBox("Ausführung")
        layout_actions = QHBoxLayout()

        btn_struct = QPushButton(" Struktur")
        btn_struct.setIcon(icon('fa5s.sitemap', color='white'))
        btn_struct.setObjectName("btn_blue")
        btn_struct.setToolTip("Kopiert nur die Ordnerstruktur (leere Ordner) ohne Dateien. Nützlich für die Vorbereitung eines Ziels.")
        btn_struct.clicked.connect(lambda: self.run_robo("Struktur", list(ACTION_PARAMS["Struktur"])))

        btn_copy = QPushButton(" Daten Update")
        btn_copy.setIcon(icon('fa5s.copy', color='white'))
        btn_copy.setObjectName("btn_blue")
        btn_copy.setToolTip("Führt ein inkrementelles Update durch: Kopiert neue und geänderte Dateien. Überspringt vorhandene, identische Dateien.")
        # Verwende /Z anstelle von /ZB, damit Robocopy nicht in den Backup-Modus
        # wechselt, der zusätzliche Rechte (Sichern/Wiederherstellen) verlangt.
        btn_copy.clicked.connect(lambda: self.run_robo("Update", list(ACTION_PARAMS["Update"])))

        btn_mirror = QPushButton(" SPIEGELN (Mirror)")
        btn_mirror.setIcon(icon('fa5s.exchange-alt', color='white'))
        btn_mirror.setObjectName("btn_red")
        btn_mirror.setToolTip("Spiegelt den Quellordner zum Ziel. Dateien im Ziel, die in der Quelle nicht vorhanden sind, werden GELÖSCHT. Vorsicht!")
        btn_mirror.clicked.connect(self.action_mirror)

        btn_purge = QPushButton(" BEREINIGEN (Purge)")
        btn_purge.setIcon(icon('fa5s.trash-alt', color='white'))
        btn_purge.setObjectName("btn_red")
        btn_purge.setToolTip("Löscht Dateien und Ordner im Ziel, die in der Quelle nicht vorhanden sind, ohne Dateien zu kopieren. Vorsicht!")
        btn_purge.clicked.connect(self.action_purge)

        btn_comp = QPushButton(" Vergleich")
        btn_comp.setIcon(icon('fa5s.balance-scale'))
        btn_comp.setToolTip("Führt einen Vergleich der Quell- und Zielordner durch und zeigt die Unterschiede an, ohne Änderungen vorzunehmen.")
        btn_comp.clicked.connect(lambda: self.run_robo("Vergleich", list(ACTION_PARAMS["Vergleich"])))

        self.btn_cancel = QPushButton(" Abbrechen")
        self.btn_cancel.setIcon(icon('fa5s.times-circle'))
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

        # Footer
        self.lbl_status = QLabel("Bereit")
        self.lbl_status.setObjectName("status_label")
        main_layout.addWidget(self.lbl_status)

        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        main_layout.addWidget(self.progress)

        self.txt_log = QTextEdit()
        self.txt_log.setReadOnly(True)
        # Kein festes setMinimumHeight: Das würde die Mindestgröße des ganzen
        # Fensters unnötig aufblähen. Die großzügige Höhe im Alltag kommt
        # stattdessen vom Stretch-Faktor unten + der initialen Fenstergröße;
        # bei sehr kleinem Fenster darf das Log entsprechend schrumpfen (und
        # bleibt dank Scrollbar weiter nutzbar).
        self.txt_log.setMinimumHeight(80)
        self.txt_log.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        main_layout.addWidget(self.txt_log, 3)

        # Log buttons (placed side-by-side to save vertical space)
        h_log_buttons = QHBoxLayout()
        self.btn_log_dir = QPushButton(" Log-Ordner ändern")
        self.btn_log_dir.setIcon(icon('fa5s.folder'))
        self.btn_log_dir.clicked.connect(self.choose_log_dir)
        self.btn_log_dir.setFixedWidth(180)
        btn_clear_log = QPushButton(" Log leeren")
        btn_clear_log.setIcon(icon('fa5s.eraser'))
        btn_clear_log.clicked.connect(self.clear_log)
        btn_clear_log.setFixedWidth(140)
        h_log_buttons.addWidget(self.btn_log_dir)
        h_log_buttons.addWidget(btn_clear_log)
        h_log_buttons.addStretch()
        main_layout.addLayout(h_log_buttons)

    def show_about(self):
        AboutDialog(self).exec()

    def browse_folder(self, combo):
        folder = QFileDialog.getExistingDirectory(self, "Ordner auswählen", combo.currentText())
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

    def get_log_file(self):
        if not os.path.exists(self.log_dir):
            try:
                os.makedirs(self.log_dir)
            except:
                pass
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        return os.path.join(self.log_dir, f"robocopy_{timestamp}.log")

    def append_log(self, text, color_type="DEFAULT"):
        colors = {
            "DEFAULT": "#cccccc", "HEADER": "#007acc", "SUCCESS": "#4ec9b0",
            "WARNING": "#ce9178", "ERROR": "#f44747", "SUMMARY": "#569cd6",
            "SUMMARY_BOLD": "#ffffff"
        }
        color = colors.get(color_type, "#cccccc")
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
        """Interaktiver Wrapper für die fünf Direct-Action-Buttons.

        Liest Quelle/Ziel/Optionen aus den Formularfeldern, zeigt die
        gewohnten Bestätigungsdialoge und delegiert die eigentliche
        Ausführung an `execute_job` (auch von der Task-Queue genutzt).
        """
        src = self.cmb_source.currentText().strip()
        dst = self.cmb_target.currentText().strip()
        if not self.validate_paths():
            return
        if not src or not dst:
            QMessageBox.warning(self, "Fehler", "Bitte Quell- und Zielordner angeben.")
            return
        # Prüfe, ob ACL-Kopie angefordert wurde und ggf. Rechte abfragen
        if self.chk_acl.isChecked():
            reply = QMessageBox.question(
                self, "ACLs kopieren",
                "ACLs kopieren erfordert Admin-Rechte und kann Berechtigungen überschreiben.\nFortfahren?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.No:
                self.chk_acl.setChecked(False)
            else:
                if not is_admin():
                    reply = QMessageBox.question(
                        self, "Fehlende Rechte",
                        "ACL Kopie benötigt Admin-Rechte.\nNeustart als Admin?",
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
        """Führt einen einzelnen Robocopy-Job aus.

        `interactive=False` (Task-Queue) unterdrückt Dialoge: fehlendes Ziel
        wird still angelegt, fehlende Quelle/ACL-Rechte führen zu einer
        Log-Zeile statt einer Modal-Abfrage.
        """
        if not interactive:
            if not os.path.exists(src):
                self.append_log(f"FEHLER: Quellordner nicht gefunden: {src}", "ERROR")
                if on_finished:
                    on_finished(name, -1)
                return
            if not os.path.exists(dst):
                try:
                    os.makedirs(dst, exist_ok=True)
                    self.append_log(f"Zielordner automatisch erstellt: {dst}", "WARNING")
                except Exception as e:
                    self.append_log(f"FEHLER: Zielordner konnte nicht erstellt werden: {e}", "ERROR")
                    if on_finished:
                        on_finished(name, -1)
                    return
            if acl and not is_admin():
                self.append_log("WARNUNG: ACL-Kopie übersprungen (keine Admin-Rechte).", "WARNING")
                acl = False

        if acl:
            params.append("/COPYALL")
        else:
            params.append("/COPY:DAT")

        if days > 0:
            date_str = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y%m%d")
            params.append(f"/MAXAGE:{date_str}")

        # Falls Logging aktiviert ist, Dateinamen vorbereiten und Robocopy
        # so starten, dass die Ausgabe auch in eine Logdatei geschrieben wird.
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
        self.lbl_status.setText(f"{name} läuft...")
        self.progress.setRange(0, 0)
        self.btn_cancel.setEnabled(True)

        self.append_log("="*60, "HEADER")
        self.append_log(f" JOB START: {name} | {datetime.datetime.now().strftime('%H:%M:%S')}", "HEADER")
        self.append_log(f" QUELLE:    {src}", "DEFAULT")
        self.append_log(f" ZIEL:      {dst}", "DEFAULT")
        if days > 0:
            self.append_log(f" FILTER:    Nur Dateien jünger als {days} Tage", "WARNING")
        self.append_log("="*60, "HEADER")

        self.worker = RobocopyWorker(cmd)
        self.worker.log_signal.connect(self.append_log)
        self.worker.finished_signal.connect(lambda code: self._job_done(name, code, on_finished))
        self.worker.start()
        self.centralWidget().setEnabled(False)

    def _job_done(self, name, code, on_finished):
        self.centralWidget().setEnabled(True)
        self.progress.setRange(0, 100)
        self.progress.setValue(100)
        success = code is not None and 0 <= code < 8
        self.append_log(f"--- {name} BEENDET (Exit-Code {code}) ---", "HEADER" if success else "ERROR")
        self.progress.setValue(0)
        self.lbl_status.setText("Bereit")
        self.btn_cancel.setEnabled(False)
        if on_finished:
            on_finished(name, code)

    def job_finished(self, name, code):
        success = code is not None and 0 <= code < 8
        if success:
            QMessageBox.information(self, "Fertig", f"{name} wurde erfolgreich beendet.")
        else:
            QMessageBox.warning(self, "Fehler", f"{name} wurde mit Fehlern beendet (Exit-Code {code}).")

    def action_mirror(self):
        days = self.spin_days.value()
        msg = "WARNUNG: MIRROR (SPIEGELN)\n\nDies LÖSCHT alle Dateien im Zielordner, die in der Quelle nicht vorhanden sind!\n\nFortfahren?"
        if days > 0:
            msg += f"\n\nACHTUNG: Filter aktiv ({days} Tage)! Alte Ordner werden nicht gespiegelt und im Ziel ggf. gelöscht!"
        if QMessageBox.question(self, "Kritische Warnung", msg, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.run_robo("Mirror", list(ACTION_PARAMS["Mirror"]))

    def action_purge(self):
        if QMessageBox.question(self, "Warnung", "PURGE: Wirklich Dateien im Ziel löschen, die nicht in der Quelle sind (kein Kopieren)?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            self.run_robo("Purge", list(ACTION_PARAMS["Purge"]))

    def delete_by_date(self):
        target = self.cmb_target.currentText()
        if not os.path.exists(target):
            return
        target_date = self.date_edit.date().toPyDate()
        if QMessageBox.question(self, "In Papierkorb verschieben", f"Alle Dateien in '{target}' in den Papierkorb verschieben, die am {target_date} geändert wurden?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            count = 0
            # Starte Löschvorgang; protokolliere Fortschritt im Log
            self.txt_log.clear()
            self.append_log(f"Starte Verschieben in den Papierkorb nach Datum: {target_date}...", "HEADER")
            for root, dirs, files in os.walk(target):
                for file in files:
                    full_path = os.path.join(root, file)
                    try:
                        if datetime.date.fromtimestamp(os.path.getmtime(full_path)) == target_date:
                            send2trash(full_path)
                            self.append_log(f"In Papierkorb verschoben: {full_path}", "WARNING")
                            count += 1
                    except Exception as e:
                        self.append_log(f"Fehler: {e}", "ERROR")
            self.append_log(f"Fertig. {count} Dateien in den Papierkorb verschoben.", "SUMMARY")
            QMessageBox.information(self, "Info", f"{count} Dateien in den Papierkorb verschoben.")

    def delete_by_name(self):
        target = self.cmb_target.currentText()
        pattern = self.txt_pattern.text().strip()
        if not os.path.exists(target) or not pattern:
            return
        if QMessageBox.warning(self, "Sicherheitswarnung", f"SICHERHEITSWARNUNG!\n\nDateien in '{target}'\ndie '{pattern}' im Namen haben in den Papierkorb verschieben?\n\nFortfahren?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No) == QMessageBox.StandardButton.Yes:
            count = 0
            self.txt_log.clear()
            self.append_log(f"Starte Verschieben in den Papierkorb nach Muster: *{pattern}*...", "HEADER")
            for root, dirs, files in os.walk(target):
                for file in files:
                    if pattern.lower() in file.lower():
                        full_path = os.path.join(root, file)
                        try:
                            send2trash(full_path)
                            self.append_log(f"In Papierkorb verschoben: {full_path}", "WARNING")
                            count += 1
                        except Exception as e:
                            self.append_log(f"Fehler: {e}", "ERROR")
            self.append_log(f"Fertig. {count} Dateien in den Papierkorb verschoben.", "SUMMARY")
            QMessageBox.information(self, "Info", f"{count} Dateien in den Papierkorb verschoben.")

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

        # Lade gespeicherte Tasks (falls vorhanden)
        try:
            if os.path.exists(TASKS_FILE):
                with open(TASKS_FILE, 'r', encoding='utf-8') as tf:
                    self.queue_tasks = json.load(tf)
        except Exception:
            # Nicht kritisch – Tasks werden dann leer gestartet
            pass

        self._migrate_legacy_presets()

    def _migrate_legacy_presets(self):
        """Einmalige Migration: frühere "Voreinstellungen" (presets.json)
        gab es als separates Konzept, das durch die Tasks-Liste ersetzt
        wurde. Damit dabei keine vom Nutzer bereits gespeicherten
        Voreinstellungen verloren gehen, werden sie hier als normale Tasks
        (Standardaktion "Update") übernommen. Läuft nur einmal: presets.json
        wird danach umbenannt, damit nicht bei jedem Start erneut importiert wird."""
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
            print(f"Konnte alte Voreinstellungen nicht migrieren: {e}")

    # load_config: liest zuletzt verwendete Pfadpaare aus der Config-Datei und
    # füllt die Dropdowns. Fehler werden still ignoriert (nicht-kritisch).

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
            QMessageBox.warning(self, "Fehler", f"Quellordner existiert nicht: {src}")
            return False
        if not os.path.exists(dst):
            reply = QMessageBox.question(
                self, "Zielordner fehlt",
                f"Zielordner existiert nicht: {dst}\nErstellen?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
            )
            if reply == QMessageBox.StandardButton.Yes:
                try:
                    os.makedirs(dst, exist_ok=True)
                except Exception as e:
                    QMessageBox.warning(self, "Fehler", f"Konnte Zielordner nicht erstellen: {e}")
                    return False
        return True

    # --- Tasks: Persistenz + Warteschlangen-Ausführung -------------------
    # Die Bearbeitung (Speichern/Laden/Löschen/Reihenfolge) findet im
    # separaten TaskManagerDialog statt (siehe open_task_manager), der
    # direkt auf self.queue_tasks arbeitet und save_tasks() aufruft.

    def open_task_manager(self):
        if getattr(self, '_task_dialog', None) is None:
            self._task_dialog = TaskManagerDialog(self)
        self._task_dialog.refresh_list()
        self._task_dialog.show()
        self._task_dialog.raise_()
        self._task_dialog.activateWindow()

    def save_tasks(self):
        try:
            os.makedirs(os.path.dirname(TASKS_FILE), exist_ok=True)
            with open(TASKS_FILE, 'w', encoding='utf-8') as tf:
                json.dump(self.queue_tasks, tf, ensure_ascii=False, indent=2)
        except Exception as e:
            self.append_log(f"WARNUNG: Konnte Tasks nicht speichern: {e}", "WARNING")

    def start_queue(self, tasks):
        """Führt die übergebenen Tasks (Liste von Task-Dicts, in Ausführungs-
        reihenfolge) nacheinander aus. Wird vom TaskManagerDialog aufgerufen."""
        if not tasks:
            QMessageBox.information(
                self, "Keine Auswahl",
                "Bitte mindestens eine Task markieren, die als Warteschlange ausgeführt werden soll."
            )
            return
        if hasattr(self, 'worker') and self.worker.isRunning():
            QMessageBox.warning(self, "Läuft bereits", "Es läuft bereits ein Robocopy-Vorgang.")
            return

        destructive = [t for t in tasks if t['action'] in ("Mirror", "Purge")]
        if destructive:
            names = "\n".join(f"- {t['name']}" for t in destructive)
            reply = QMessageBox.question(
                self, "Kritische Warnung",
                f"Die Warteschlange enthält {len(destructive)} destruktive Task(s) (Mirror/Purge), "
                f"die Dateien im Ziel LÖSCHEN können:\n\n{names}\n\nWarteschlange trotzdem starten?",
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
        self.append_log(f"=== WARTESCHLANGE GESTARTET ({self._queue_total} Tasks) ===", "HEADER")
        self._run_next_queue_task()

    def _run_next_queue_task(self):
        if not self.queue_running:
            return
        if self.queue_pos >= len(self._active_run_tasks):
            self._finish_queue()
            return
        task = self._active_run_tasks[self.queue_pos]
        self.queue_pos += 1
        label = f"[Queue {self.queue_pos}/{self._queue_total}] {task['name']}"
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
        self.append_log(f"=== WARTESCHLANGE BEENDET: {ok_count} OK, {fail_count} fehlgeschlagen ===", status)
        lines = [f"{'OK    ' if s else 'FEHLER'} - {n} (Code {c})" for n, s, c in self.queue_results]
        QMessageBox.information(
            self, "Warteschlange abgeschlossen",
            f"{ok_count} erfolgreich, {fail_count} fehlgeschlagen.\n\n" + "\n".join(lines)
        )

    def cancel_robo(self):
        if hasattr(self, 'worker') and self.worker.isRunning():
            self.worker.terminate()
            self.worker.wait()
            self.append_log("--- ABGEBROCHEN ---", "ERROR")
            self.btn_cancel.setEnabled(False)
            self.centralWidget().setEnabled(True)
            self.progress.setValue(0)
            self.lbl_status.setText("Abgebrochen")
            if self.queue_running:
                self.queue_running = False
                self.append_log(
                    f"--- WARTESCHLANGE ABGEBROCHEN ({self.queue_pos}/{self._queue_total} Tasks gestartet) ---",
                    "ERROR"
                )

    # cancel_robo: sicherstellen, dass Hintergrundprozess (und ggf. eine
    # laufende Task-Queue) beendet und die UI wieder aktiv ist.

    def choose_log_dir(self):
        dir = QFileDialog.getExistingDirectory(self, "Log-Ordner auswählen", self.log_dir)
        if dir:
            self.log_dir = dir
            self._update_log_checkbox_text()

    def _update_log_checkbox_text(self):
        """Zeigt den Log-Pfad gekürzt in der Checkbox an (voller Pfad im
        Tooltip), damit ein sehr langer, frei gewählter Ordnerpfad nicht die
        Mindestbreite des Fensters unkontrolliert aufbläht."""
        prefix = "Logdatei erstellen in "
        metrics = QFontMetrics(self.chk_log.font())
        elided_path = metrics.elidedText(self.log_dir, Qt.TextElideMode.ElideMiddle, 260)
        self.chk_log.setText(prefix + elided_path)
        self.chk_log.setToolTip(f"Erstellt eine detaillierte Logdatei des Robocopy-Vorgangs in {self.log_dir}.")

    def clear_log(self):
        self.txt_log.clear()

class TaskManagerDialog(QDialog):
    """Eigenständiges Fenster zur Task-Verwaltung: anlegen, bearbeiten,
    löschen, per Drag & Drop sortieren und eine Auswahl als Warteschlange
    starten. Arbeitet direkt auf main_window.queue_tasks; die eigentliche
    Ausführung (execute_job/_run_next_queue_task/...) bleibt in MainWindow,
    damit der Log-Bereich und der Fortschritt dort sichtbar sind."""

    def __init__(self, main_window):
        super().__init__(main_window)
        self.main_window = main_window
        self.setWindowTitle("Tasks verwalten")
        if not main_window.windowIcon().isNull():
            self.setWindowIcon(main_window.windowIcon())
        self.resize(820, 480)
        self.setMinimumSize(700, 420)

        outer = QVBoxLayout(self)

        content = QHBoxLayout()
        content.setSpacing(12)

        # Linke Seite: Liste der gespeicherten Tasks
        left = QVBoxLayout()
        lbl_hint = QLabel(
            "Strg/Umschalt-Klick markiert mehrere Tasks für die Warteschlange.\n"
            "Per Drag & Drop lässt sich die Reihenfolge ändern."
        )
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
        btn_new = QPushButton(" Neu")
        btn_new.setIcon(icon('fa5s.plus-circle'))
        btn_new.setToolTip("Leert das Formular rechts für eine neue Task.")
        btn_new.clicked.connect(self.new_task)
        btn_delete = QPushButton(" Löschen")
        btn_delete.setIcon(icon('fa5s.trash'))
        btn_delete.setToolTip("Löscht die markierte(n) Task(s).")
        btn_delete.clicked.connect(self.delete_selected)
        row_left_buttons.addWidget(btn_new)
        row_left_buttons.addWidget(btn_delete)
        left.addLayout(row_left_buttons)

        content.addLayout(left, 1)

        # Rechte Seite: Formular zum Anlegen/Bearbeiten einer Task
        right = QVBoxLayout()
        grp_form = QGroupBox("Task bearbeiten")
        form = QVBoxLayout()
        form.setSpacing(8)

        row_name = QHBoxLayout()
        row_name.addWidget(QLabel("Name:"))
        self.txt_name = QLineEdit()
        row_name.addWidget(self.txt_name)
        form.addLayout(row_name)

        row_action = QHBoxLayout()
        row_action.addWidget(QLabel("Aktion:"))
        self.cmb_action = QComboBox()
        self.cmb_action.addItems(list(ACTION_PARAMS.keys()))
        row_action.addWidget(self.cmb_action)
        row_action.addStretch()
        form.addLayout(row_action)

        row_src = QHBoxLayout()
        row_src.addWidget(QLabel("Quelle:"))
        self.txt_source = QLineEdit()
        btn_src = QPushButton()
        btn_src.setIcon(icon('fa5s.folder-open'))
        btn_src.setToolTip("Durchsuchen...")
        btn_src.clicked.connect(lambda: self._browse(self.txt_source))
        row_src.addWidget(self.txt_source)
        row_src.addWidget(btn_src)
        form.addLayout(row_src)

        row_dst = QHBoxLayout()
        row_dst.addWidget(QLabel("Ziel:"))
        self.txt_target = QLineEdit()
        btn_dst = QPushButton()
        btn_dst.setIcon(icon('fa5s.folder-open'))
        btn_dst.setToolTip("Durchsuchen...")
        btn_dst.clicked.connect(lambda: self._browse(self.txt_target))
        row_dst.addWidget(self.txt_target)
        row_dst.addWidget(btn_dst)
        form.addLayout(row_dst)

        row_days = QHBoxLayout()
        row_days.addWidget(QLabel("Dateialter:"))
        self.spin_days = QSpinBox()
        self.spin_days.setRange(0, 9999)
        row_days.addWidget(self.spin_days)
        row_days.addWidget(QLabel("Tage (0 = Alle)"))
        row_days.addStretch()
        form.addLayout(row_days)

        self.chk_acl = QCheckBox("Berechtigungen (ACLs) /COPYALL")
        self.chk_verbose = QCheckBox("Alle Dateien anzeigen (Verbose /V)")
        self.chk_log = QCheckBox("Logdatei erstellen (im eingestellten Log-Ordner)")
        form.addWidget(self.chk_acl)
        form.addWidget(self.chk_verbose)
        form.addWidget(self.chk_log)
        form.addStretch()

        grp_form.setLayout(form)
        right.addWidget(grp_form, 1)

        btn_save = QPushButton(" Speichern")
        btn_save.setIcon(icon('fa5s.save'))
        btn_save.setObjectName("btn_blue")
        btn_save.setToolTip("Speichert diese Task (überschreibt bei gleichem Namen).")
        btn_save.clicked.connect(self.save_current)
        right.addWidget(btn_save)

        content.addLayout(right, 1)
        outer.addLayout(content, 1)

        footer = QHBoxLayout()
        self.btn_start_queue = QPushButton(" Warteschlange starten")
        self.btn_start_queue.setIcon(icon('fa5s.play', color='white'))
        self.btn_start_queue.setObjectName("btn_blue")
        self.btn_start_queue.setToolTip("Führt alle markierten Tasks in Listreihenfolge nacheinander aus.")
        self.btn_start_queue.clicked.connect(self.start_selected_queue)
        btn_close = QPushButton(" Schließen")
        btn_close.setIcon(icon('fa5s.times-circle'))
        btn_close.clicked.connect(self.close)
        footer.addWidget(self.btn_start_queue)
        footer.addStretch()
        footer.addWidget(btn_close)
        outer.addLayout(footer)

        self.new_task()
        self.refresh_list()

    def _browse(self, line_edit):
        folder = QFileDialog.getExistingDirectory(self, "Ordner auswählen", line_edit.text())
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
        t = current.data(Qt.ItemDataRole.UserRole)
        self.txt_name.setText(t["name"])
        self.cmb_action.setCurrentText(t["action"])
        self.txt_source.setText(t["source"])
        self.txt_target.setText(t["target"])
        self.spin_days.setValue(t.get("days", 0))
        self.chk_acl.setChecked(t.get("acl", False))
        self.chk_verbose.setChecked(t.get("verbose", False))
        self.chk_log.setChecked(t.get("log", False))

    def save_current(self):
        src = self.txt_source.text().strip()
        dst = self.txt_target.text().strip()
        if not src or not dst:
            QMessageBox.warning(self, "Fehler", "Bitte Quell- und Zielordner angeben.")
            return
        name = self.txt_name.text().strip()
        if not name:
            name = f"{self.cmb_action.currentText()}: {src} → {dst}"
            self.txt_name.setText(name)
        task = {
            "name": name,
            "action": self.cmb_action.currentText(),
            "source": src,
            "target": dst,
            "days": self.spin_days.value(),
            "acl": self.chk_acl.isChecked(),
            "verbose": self.chk_verbose.isChecked(),
            "log": self.chk_log.isChecked(),
        }
        tasks = self.main_window.queue_tasks
        existing_index = next((i for i, t in enumerate(tasks) if t['name'] == name), None)
        if existing_index is not None:
            tasks[existing_index] = task
        else:
            tasks.append(task)
        self.main_window.save_tasks()
        self.refresh_list(select_name=name)

    def delete_selected(self):
        items = self.list_tasks.selectedItems()
        if not items:
            QMessageBox.warning(self, "Fehler", "Bitte mindestens eine Task in der Liste markieren.")
            return
        names = [it.data(Qt.ItemDataRole.UserRole)['name'] for it in items]
        reply = QMessageBox.question(
            self, "Task(s) löschen",
            "Folgende Task(s) wirklich löschen?\n\n" + "\n".join(f"- {n}" for n in names),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Yes:
            self.main_window.queue_tasks = [t for t in self.main_window.queue_tasks if t['name'] not in names]
            self.main_window.save_tasks()
            self.new_task()
            self.refresh_list()

    def refresh_list(self, select_name=None):
        selected_names = (
            {select_name} if select_name is not None
            else {it.data(Qt.ItemDataRole.UserRole)['name'] for it in self.list_tasks.selectedItems()}
        )
        self.list_tasks.blockSignals(True)
        self.list_tasks.clear()
        for t in self.main_window.queue_tasks:
            item = QListWidgetItem(f"[{t['action']}] {t['name']}  ({t['source']} → {t['target']})")
            item.setData(Qt.ItemDataRole.UserRole, t)
            self.list_tasks.addItem(item)
            if t['name'] in selected_names:
                item.setSelected(True)
                self.list_tasks.setCurrentItem(item)
        self.list_tasks.blockSignals(False)
        self._update_queue_button_label()

    def _on_reordered(self):
        # Nach Drag&Drop: Reihenfolge aus der aktuellen Anzeige neu aufbauen
        # und in main_window.queue_tasks persistieren.
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
            self.btn_start_queue.setText(f" Warteschlange starten ({count})")
        else:
            self.btn_start_queue.setText(" Warteschlange starten")

    def start_selected_queue(self):
        selected_items = sorted(self.list_tasks.selectedItems(), key=lambda it: self.list_tasks.row(it))
        tasks = [it.data(Qt.ItemDataRole.UserRole) for it in selected_items]
        self.main_window.start_queue(tasks)

if __name__ == "__main__":
    # Anwendung starten
    app = QApplication(sys.argv)

    # Versuche, ein Splash-Bild zu laden. Falls vorhanden, kurz anzeigen,
    # ansonsten direkt das Hauptfenster öffnen.
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
            # Zeige Splash für 1.5 Sekunden bevor das Hauptfenster geöffnet wird
            QTimer.singleShot(1500, start_main)
        else:
            window = MainWindow()
            window.show()
    else:
        window = MainWindow()
        window.show()
    # Haupt-Event-Loop
    sys.exit(app.exec())
