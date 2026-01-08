# Robocopy GUI

Eine schlanke grafische Oberfläche für das Windows-Tool `robocopy`, implementiert in Python mit PyQt6.

**Kurz:** Einfache Bedienung für inkrementelle Kopien, Spiegeln, Prüfungen und selektives Löschen.

**Dateien im Repo:**
- `RobocopyGUI.py` – Hauptanwendung (Quellcode)
- `logo.png`, `RobocopyGUI.ico` – App-Logo / Icon
- `dist/RobocopyGUI.exe` – gebaute Einzeldatei (falls vorhanden)
- Hilfsskripte für Build/Sign/Repo-Inspektion

**Voraussetzungen (Entwicklung)**
- Windows
- Python 3.10+ (hier getestet mit 3.14)
- PyQt6
- Pillow (für Icon-Erstellung)
- PyInstaller (zum Erstellen der EXE)

Installation der Abhängigkeiten (Dev-Umgebung):

```powershell
python -m pip install -r requirements.txt
# oder einzeln
python -m pip install PyQt6 pillow pyinstaller
```

Build (einfacher Befehl, erzeugt `dist/RobocopyGUI.exe`):

```powershell
python -m PyInstaller --clean --onefile --windowed --name RobocopyGUI --icon RobocopyGUI.ico --add-data "logo.png;." RobocopyGUI.py
```

Sicherheit / Hinweise:
- Speichere keine privaten Schlüssel oder PFX-Dateien im Repo. Falls Zertifikate zum Signieren verwendet werden, lege diese außerhalb des Repos ab und füge sie zu `.gitignore` hinzu.
- `robocopy` kann Dateien löschen (z. B. bei Mirror/Purge). Prüfe Pfade sorgsam.

Lizenz: Unlicense / freie Verwendung (Bitte anpassen, falls anders gewünscht).

---

Bei Bedarf erstelle ich ein `requirements.txt`, signiere die EXE mit einem Testzertifikat oder lade die gebaute EXE als Release hoch. Sage mir, welche Aktion du als nächstes möchtest.