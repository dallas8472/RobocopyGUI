# Robocopy GUI

Eine schlanke grafische Oberfläche für das Windows-Tool `robocopy`, implementiert in Python mit PyQt6.

**Kurz:** Einfache Bedienung für inkrementelle Kopien, Spiegeln, Vergleiche und selektives Löschen – inklusive einer Task-Verwaltung für wiederkehrende Jobs, die sich einzeln oder als Warteschlange nacheinander ausführen lassen.

## Funktionen

- **Kopier-Aktionen:** Struktur (nur Ordner), Daten-Update (inkrementell), Spiegeln (Mirror, inkl. Löschen im Ziel), Bereinigen (Purge) und Vergleich (Dry-Run, `/L`)
- **Optionen:** Dateialter-Filter, ACL-/Berechtigungs-Kopie (`/COPYALL`, erfordert Administratorrechte), Verbose-Log, optionale Logdatei
- **Spezial-Löschen:** Dateien im Zielordner nach Änderungsdatum oder Namensmuster entfernen – landen im **Windows-Papierkorb** (`send2trash`), nicht permanent gelöscht
- **Tasks verwalten** (Menü *Tasks → Tasks verwalten...*): eigenes Fenster zum Anlegen, Bearbeiten und Sortieren (Drag & Drop) gespeicherter Jobs; mehrere Tasks markieren und als **Warteschlange** nacheinander automatisch abarbeiten lassen (Fehler in einer Task stoppen die Warteschlange nicht, am Ende gibt es eine Erfolg/Fehler-Zusammenfassung)
- **Admin-Modus:** Neustart mit Administratorrechten direkt aus der App, nötig für ACL-Kopie
- Prüft beim Start, ob `robocopy.exe` im PATH gefunden wird
- Frei skalierbares Fenster mit sinnvoller Mindestgröße

**Dateien im Repo:**
- `RobocopyGUI.py` – Hauptanwendung (Quellcode)
- `logo.png`, `RobocopyGUI.ico` – App-Logo / Icon
- `RobocopyGUI.spec` – PyInstaller-Spec (bündelt auch das benötigte Icon-Font-Subset von `qtawesome`)
- `dist/RobocopyGUI.exe` – gebaute Einzeldatei (falls vorhanden)
- `_create_ico.py` – erzeugt `RobocopyGUI.ico` aus `logo.png` (benötigt Pillow)

**Voraussetzungen (Entwicklung)**
- Windows
- Python 3.10+ (hier getestet mit 3.14)
- PyQt6
- qtawesome (Icons in der Oberfläche)
- send2trash (Papierkorb statt permanentem Löschen)
- Pillow (für Icon-Erstellung)
- PyInstaller (zum Erstellen der EXE)

Installation der Abhängigkeiten (Dev-Umgebung):

```powershell
python -m pip install -r requirements.txt
# oder einzeln
python -m pip install PyQt6 qtawesome send2trash pillow pyinstaller
```

## Build

Empfohlen: über das mitgelieferte Spec-File bauen, da es gezielt das benötigte
Icon-Font-Subset von `qtawesome` mit einbettet (ein direkter `pyinstaller`-Aufruf
ohne Spec-File tut das nicht und die Icons fehlen dann in der EXE):

```powershell
python -m PyInstaller --clean RobocopyGUI.spec
```

Ergebnis liegt danach in `dist/RobocopyGUI.exe`.

## Nutzung

1. Quell- und Zielordner wählen (oder per Drag & Drop auf die Felder ziehen).
2. Optionen einstellen (Dateialter, ACLs, Verbose, Logdatei) und eine Aktion in
   "Ausführung" anklicken.
3. Für wiederkehrende Jobs: über *Tasks → Tasks verwalten...* eine Task mit
   Name, Aktion, Quelle/Ziel und Optionen anlegen. Mehrere Tasks markieren
   (Strg/Umschalt-Klick) und "Warteschlange starten" führt sie der Reihe nach aus.

Sicherheit / Hinweise:
- Speichere keine privaten Schlüssel oder PFX-Dateien im Repo. Falls Zertifikate zum Signieren verwendet werden, lege diese außerhalb des Repos ab und füge sie zu `.gitignore` hinzu.
- `robocopy` kann Dateien löschen (z. B. bei Mirror/Purge) – diese Löschungen laufen direkt über robocopy und landen **nicht** im Papierkorb. Prüfe Pfade sorgsam, insbesondere bei Mirror.
- Konfiguration (zuletzt verwendete Pfade, gespeicherte Tasks) liegt unter `%APPDATA%\RobocopyGUI\`.

Lizenz: [MIT](LICENSE) – freie Nutzung, Veränderung und Weitergabe, auch kommerziell, ohne Gewährleistung.
