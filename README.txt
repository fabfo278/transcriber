============================================================
  Transkriptions-App  –  Kurzanleitung
============================================================

VORAUSSETZUNGEN
---------------
Python 3.x sowie folgende Pakete (einmalig installieren):

    pip install faster-whisper pyaudiowpatch keyboard colorama

Die App läuft komplett offline – es werden keine Daten an
externe Dienste gesendet.


STARTEN
-------
    python transcriber.py

Beim allerersten Start wird das Whisper-Modell von
HuggingFace heruntergeladen (~1,5 GB für "medium").
Das dauert einige Minuten und geschieht nur einmalig.


ABLAUF BEIM START
-----------------
1. Ausgabedatei wählen
   – Enter bestätigt den Standardpfad
     (transcriptions/session_YYYY-MM-DD.txt)
   – Oder einen eigenen Pfad eingeben

2. Falls die Datei bereits existiert – Menü:
   [A]  An das Ende anhängen
   [N]  Neuen Abschnitt (mit Trennlinie) am Ende beginnen
   [L]  Nach einer bestimmten Zeile einfügen
   [O]  Datei komplett überschreiben

3. Das Loopback-Gerät (Systemton) wird automatisch gewählt.
   Bei mehreren Geräten erscheint eine Auswahlliste.

4. Aufnahme läuft – einfach das Video starten.


AUFNAHME STOPPEN
----------------
– Tastenkürzel:  Ctrl + Shift + S
– Fallback:      Enter drücken (funktioniert immer)
– Notfall:       Ctrl + C


SPRACHE
-------
Die automatische Spracherkennung ist aktiviert.
Deutsch und Englisch werden erkannt und korrekt
transkribiert – auch wenn beides im selben Video vorkommt.


KONFIGURATION (im Skript, oben im Abschnitt "Konfiguration")
-------------------------------------------------------------
CHUNK_SECONDS   Wie viele Sekunden Audio pro Transkriptionsaufruf
                gesammelt werden. Standard: 5
                – Kleiner = weniger Verzögerung, aber ungenauer
                – Größer = genauer, aber mehr Verzögerung

WHISPER_MODEL   Qualitätsstufe des Modells:
                  "tiny"    – sehr schnell, weniger genau (~150 MB)
                  "small"   – guter Kompromiss          (~500 MB)
                  "medium"  – empfohlen, sehr genau     (~1,5 GB)
                  "large-v3"– beste Qualität, langsam   (~3 GB)

LANGUAGE        None  = automatische Erkennung (Standard)
                "de"  = nur Deutsch erzwingen
                "en"  = nur Englisch erzwingen

DEVICE          "cpu"   – Standard, funktioniert immer
                "cuda"  – NVIDIA-GPU (deutlich schneller)


BEKANNTE EINSCHRÄNKUNGEN
-------------------------
– Auf CPU dauert die Transkription von 5 Sek. Audio ca. 3–15 Sek.
  (je nach Rechner). Es gibt also eine sichtbare Verzögerung.
  Mit "small" statt "medium" wird sie kürzer.

– Das Tastenkürzel Ctrl+Shift+S benötigt auf manchen Systemen
  Administrator-Rechte. Der Enter-Fallback funktioniert immer.

– Kein Loopback-Gerät gefunden?
  → Rechtsklick auf Lautsprecher-Symbol in der Taskleiste
  → Soundeinstellungen > Weitere Soundeinstellungen
  → Tab "Aufnahme" > Rechtsklick > "Deaktivierte Geräte anzeigen"
  → "Stereo Mix" aktivieren (falls vorhanden)
  Alternativ: Skript als Administrator ausführen.


DATEIABLAGE
-----------
Transkriptionen werden standardmäßig gespeichert in:
    transcriber\transcriptions\session_YYYY-MM-DD.txt

============================================================
