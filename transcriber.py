"""
Transkriptions-App
Nimmt Systemton (WASAPI-Loopback) auf und transkribiert ihn mit faster-whisper.
"""

import sys
import os
import struct
import threading
import queue
import numpy as np
from datetime import date
from pathlib import Path

# ---------------------------------------------------------------------------
# Konfiguration
# ---------------------------------------------------------------------------
CHUNK_SECONDS = 5
SAMPLE_RATE   = None   # wird automatisch vom Gerät übernommen
CHANNELS      = None   # wird automatisch vom Gerät übernommen
WHISPER_MODEL = "small"
LANGUAGE      = None   # None = automatische Spracherkennung (Deutsch + Englisch u.a.)
DEVICE        = "cpu"

DEFAULT_OUTPUT_DIR = Path(__file__).parent / "transcriptions"

# ---------------------------------------------------------------------------
# Terminal-Farben
# ---------------------------------------------------------------------------

def init_colorama():
    try:
        import colorama
        colorama.init()
    except ImportError:
        pass


def colored(text, code):
    return f"\033[{code}m{text}\033[0m"

def info(msg):    print(colored(msg, "36"))
def success(msg): print(colored(msg, "32"))
def warn(msg):    print(colored(msg, "33"))
def error(msg):   print(colored(msg, "31"))


# ---------------------------------------------------------------------------
# 1. Whisper-Modell laden
# ---------------------------------------------------------------------------

def load_model():
    try:
        from faster_whisper import WhisperModel
    except ImportError:
        error("faster-whisper ist nicht installiert.")
        error("Bitte ausführen: pip install faster-whisper")
        sys.exit(1)

    info(f"Lade Whisper-Modell '{WHISPER_MODEL}' (wird beim ersten Start heruntergeladen)...")
    model = WhisperModel(WHISPER_MODEL, device=DEVICE, compute_type="int8")
    success("Modell geladen.")
    return model


# ---------------------------------------------------------------------------
# 2. Audio-Gerät wählen (pyaudiowpatch / WASAPI-Loopback)
# ---------------------------------------------------------------------------

def get_pyaudio():
    try:
        import pyaudiowpatch as pyaudio
        return pyaudio
    except ImportError:
        error("pyaudiowpatch ist nicht installiert.")
        error("Bitte ausführen: pip install pyaudiowpatch")
        sys.exit(1)


def list_loopback_devices(pa):
    """Gibt alle WASAPI-Loopback-Geräte zurück."""
    try:
        return list(pa.get_loopback_device_info_generator())
    except Exception:
        return []


def select_audio_device():
    pyaudio = get_pyaudio()
    pa = pyaudio.PyAudio()

    loopbacks = list_loopback_devices(pa)

    if not loopbacks:
        error("\nKein WASAPI-Loopback-Gerät gefunden.")
        warn("Mögliche Lösung:")
        warn("  1. Rechtsklick auf das Lautsprecher-Symbol in der Taskleiste")
        warn("  2. Soundeinstellungen > Weitere Soundeinstellungen")
        warn("  3. Tab 'Aufnahme' > Rechtsklick > 'Deaktivierte Geräte anzeigen'")
        warn("  4. 'Stereo Mix' aktivieren (falls vorhanden)")
        warn("  Oder: Skript als Administrator ausführen")
        pa.terminate()
        sys.exit(1)

    if len(loopbacks) == 1:
        dev = loopbacks[0]
        info(f"Loopback-Gerät automatisch gewählt: {dev['name']}")
        pa.terminate()
        return dev

    print("\nMehrere Loopback-Geräte gefunden:")
    for i, d in enumerate(loopbacks, 1):
        print(f"  [{i}] {d['name']}")

    while True:
        choice = input("Gerät wählen (Nummer): ").strip()
        if choice.isdigit() and 1 <= int(choice) <= len(loopbacks):
            dev = loopbacks[int(choice) - 1]
            pa.terminate()
            return dev
        warn("Ungültige Eingabe.")


# ---------------------------------------------------------------------------
# 3. Ausgabedatei wählen
# ---------------------------------------------------------------------------

def resolve_output_file():
    DEFAULT_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    existing = sorted(DEFAULT_OUTPUT_DIR.glob("*.txt"), key=lambda p: p.stat().st_mtime, reverse=True)

    print("\n=== Transkriptionsdatei wählen ===")

    if existing:
        print("\n  Vorhandene Dateien:")
        for i, f in enumerate(existing, 1):
            size_kb = f.stat().st_size // 1024
            print(f"  [{i}] {f.name}  ({size_kb} KB)")
        print(f"\n  [N] Neue Datei anlegen")

        while True:
            choice = input("\nAuswahl: ").strip().upper()
            if choice == "N":
                break
            if choice.isdigit() and 1 <= int(choice) <= len(existing):
                return existing[int(choice) - 1]
            warn("Ungültige Eingabe.")
    else:
        info("Noch keine Dateien im transcriptions-Ordner vorhanden.")

    # Neue Datei anlegen
    default_name = f"session_{date.today()}.txt"
    raw = input(f"Dateiname [{default_name}]: ").strip()
    name = raw if raw else default_name
    if not name.endswith(".txt"):
        name += ".txt"
    path = DEFAULT_OUTPUT_DIR / name

    try:
        with open(path, "a", encoding="utf-8"):
            pass
    except PermissionError:
        error(f"Kein Schreibzugriff auf: {path}")
        sys.exit(1)

    return path


# ---------------------------------------------------------------------------
# 4. Datei-Resume-Menü
# ---------------------------------------------------------------------------

def preview_file(lines, max_preview=8):
    """Erste Zeile jedes Absatzes (getrennt durch Leerzeilen)."""
    preview_lines = []
    blank_pending = False
    for i, line in enumerate(lines, 1):
        stripped = line.rstrip("\n")
        if stripped == "":
            blank_pending = True
        else:
            if blank_pending or not preview_lines:
                preview_lines.append((i, stripped))
                blank_pending = False
            if len(preview_lines) >= max_preview:
                break
    return preview_lines


def handle_file_resume(path):
    """
    Gibt zurück: (open_mode, insertion_line_or_None)
    """
    if not path.exists() or path.stat().st_size == 0:
        return "a", None

    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    total = len(lines)
    preview = preview_file(lines)

    print(f"\n=== Vorhandener Inhalt: {path.name} ===")
    for lineno, text in preview:
        snippet = text[:80] + "..." if len(text) > 80 else text
        print(f"  [{lineno:4d}] {snippet}")
    remaining = total - len(preview)
    if remaining > 0:
        print(f"         --- ({remaining} weitere Zeilen nicht angezeigt) ---")

    print(f"\n  [A] An das Ende anhängen (nach Zeile {total})")
    print(f"  [N] Neuen Abschnitt am Ende beginnen")
    print(f"  [L] Nach einer bestimmten Zeile einfügen")
    print(f"  [O] Datei überschreiben (Bestätigung erforderlich)")

    while True:
        choice = input("\nAuswahl: ").strip().upper()

        if choice == "A":
            return "a", None

        if choice == "N":
            with open(path, "a", encoding="utf-8") as f:
                f.write("\n\n---\n\n")
            return "a", None

        if choice == "L":
            while True:
                raw = input(f"Nach Zeile einfügen (1–{total}): ").strip()
                if raw.isdigit() and 1 <= int(raw) <= total:
                    return "insert", int(raw)
                warn("Ungültige Zeilennummer.")

        if choice == "O":
            confirm = input("Wirklich überschreiben? [j/N]: ").strip().lower()
            if confirm == "j":
                return "w", None
            warn("Abgebrochen.")

        else:
            warn("Bitte A, N, L oder O eingeben.")


# ---------------------------------------------------------------------------
# 5. Datei für Schreiben vorbereiten
# ---------------------------------------------------------------------------

def open_output_file(path, mode, insertion_line):
    if mode in ("a", "w"):
        return open(path, mode, encoding="utf-8"), None

    # Insert-Modus
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()

    prefix = lines[:insertion_line]
    suffix = lines[insertion_line:]

    with open(path, "w", encoding="utf-8") as f:
        f.writelines(prefix)
        f.write("\n")

    suffix_path = path.with_suffix(".suffix_tmp")
    with open(suffix_path, "w", encoding="utf-8") as sf:
        sf.writelines(suffix)

    return open(path, "a", encoding="utf-8"), suffix_path


def finalize_insert(file_handle, path, suffix_path):
    file_handle.flush()
    file_handle.close()
    suffix_path = Path(suffix_path)
    if suffix_path.exists():
        with open(suffix_path, "r", encoding="utf-8") as sf:
            suffix = sf.read()
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n")
            f.write(suffix)
        suffix_path.unlink()


# ---------------------------------------------------------------------------
# 6. Transkriptions-Schleife (Producer/Consumer)
# ---------------------------------------------------------------------------

def _prepare_audio(raw_bytes, channels, sample_rate):
    """Bytes → mono float32 numpy array bei 16000 Hz."""
    audio = np.frombuffer(raw_bytes, dtype=np.float32)
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if sample_rate != 16000:
        ratio = 16000 / sample_rate
        new_len = int(len(audio) * ratio)
        indices = np.round(np.linspace(0, len(audio) - 1, new_len)).astype(int)
        audio = audio[indices]
    return audio


def _recording_thread(device_info, stop_event, audio_queue):
    """Nimmt kontinuierlich Audio auf und legt Chunks in die Queue."""
    import pyaudiowpatch as pyaudio

    sample_rate = int(device_info["defaultSampleRate"])
    channels    = device_info["maxInputChannels"]
    frames_per_chunk = sample_rate * CHUNK_SECONDS

    pa = pyaudio.PyAudio()
    stream = pa.open(
        format=pyaudio.paFloat32,
        channels=channels,
        rate=sample_rate,
        frames_per_buffer=512,
        input=True,
        input_device_index=device_info["index"],
    )

    try:
        while not stop_event.is_set():
            frames = []
            collected = 0
            while collected < frames_per_chunk:
                to_read = min(512, frames_per_chunk - collected)
                try:
                    data = stream.read(to_read, exception_on_overflow=False)
                    frames.append(data)
                    collected += to_read
                except Exception:
                    break
            if frames:
                audio_queue.put((b"".join(frames), channels, sample_rate))
    finally:
        stream.stop_stream()
        stream.close()
        pa.terminate()
        audio_queue.put(None)  # Signal: Aufnahme beendet


def transcription_loop(device_info, model, file_handle, stop_event):
    audio_queue = queue.Queue()

    rec_thread = threading.Thread(
        target=_recording_thread,
        args=(device_info, stop_event, audio_queue),
        daemon=True,
    )
    rec_thread.start()

    success("\n[Aufnahme läuft] Drücke Ctrl+Shift+S zum Stoppen (oder Enter eingeben)\n")

    while True:
        item = audio_queue.get()
        if item is None:
            break  # Aufnahme beendet, Queue leer

        raw_bytes, channels, sample_rate = item
        pending = audio_queue.qsize()
        if pending > 0:
            info(f"  [Warteschlange: {pending} Chunk{'s' if pending > 1 else ''} (~{pending * CHUNK_SECONDS} Sek. ausstehend)]")

        audio = _prepare_audio(raw_bytes, channels, sample_rate)

        rms = np.sqrt(np.mean(audio ** 2))
        if rms < 0.001:
            continue

        try:
            segments, _ = model.transcribe(
                audio,
                language=LANGUAGE,
                beam_size=5,
                vad_filter=True,
                vad_parameters={"min_silence_duration_ms": 500},
            )
            text = " ".join(seg.text.strip() for seg in segments).strip()
            if text:
                print(text)
                file_handle.write(text + "\n")
                file_handle.flush()
        except Exception as exc:
            warn(f"Transkriptionsfehler (übersprungen): {exc}")

    # Verbleibende Chunks in der Queue noch abarbeiten
    remaining = audio_queue.qsize()
    if remaining > 0:
        info(f"\n[Aufnahme gestoppt] Verarbeite noch {remaining} ausstehende Chunk{'s' if remaining > 1 else ''}...")
        while not audio_queue.empty():
            item = audio_queue.get()
            if item is None:
                continue
            raw_bytes, channels, sample_rate = item
            audio = _prepare_audio(raw_bytes, channels, sample_rate)
            rms = np.sqrt(np.mean(audio ** 2))
            if rms < 0.001:
                continue
            try:
                segments, _ = model.transcribe(
                    audio, language=LANGUAGE, beam_size=5,
                    vad_filter=True,
                    vad_parameters={"min_silence_duration_ms": 500},
                )
                text = " ".join(seg.text.strip() for seg in segments).strip()
                if text:
                    print(text)
                    file_handle.write(text + "\n")
                    file_handle.flush()
            except Exception:
                pass
        success("Alle ausstehenden Chunks verarbeitet.")


# ---------------------------------------------------------------------------
# 7. Stop-Mechanismus
# ---------------------------------------------------------------------------

def setup_stop(stop_event):
    def wait_for_enter():
        input()
        stop_event.set()

    t = threading.Thread(target=wait_for_enter, daemon=True)
    t.start()

    try:
        import keyboard
        keyboard.add_hotkey("ctrl+shift+s", stop_event.set)
    except Exception:
        pass


# ---------------------------------------------------------------------------
# 8. Hauptprogramm
# ---------------------------------------------------------------------------

def main():
    init_colorama()

    print("=" * 55)
    print("  Transkriptions-App")
    print("=" * 55)

    model       = load_model()
    device_info = select_audio_device()
    path        = resolve_output_file()
    mode, insertion_line = handle_file_resume(path)
    file_handle, suffix_path = open_output_file(path, mode, insertion_line)

    stop_event = threading.Event()
    setup_stop(stop_event)

    try:
        transcription_loop(device_info, model, file_handle, stop_event)
    except KeyboardInterrupt:
        pass
    finally:
        if suffix_path:
            finalize_insert(file_handle, path, suffix_path)
        else:
            file_handle.flush()
            file_handle.close()

    success(f"\nTranskription gespeichert in: {path}")


if __name__ == "__main__":
    main()
