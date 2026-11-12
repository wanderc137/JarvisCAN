#!/usr/bin/env python3
import argparse
import json
import os
import re
import select
import subprocess
import sys
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_MODEL = ROOT / "models" / "vosk-model-small-es-0.42"
DEFAULT_PYLIB = ROOT / ".pylibs"
DEFAULT_TTS_DIR = ROOT / "data"
DEFAULT_PIPER_BIN = ROOT / "vendor" / "piper" / "piper"
DEFAULT_PIPER_MODEL = ROOT / "models" / "piper" / "es_MX-claude-high.onnx"
DEFAULT_PIPER_DATA = ROOT / "vendor" / "piper" / "espeak-ng-data"
DEFAULT_TTS_ENGINE = os.environ.get("JARVIS_TTS_ENGINE", "auto")


def _env_float(name, default):
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return float(default)


TTS_PROFILES = {
    "flat": {
        "length_scale": 1.0,
        "noise_scale": 0.667,
        "noise_w": 0.82,
        "sentence_silence": 0.35,
    },
    "human": {
        "length_scale": 1.0,
        "noise_scale": 0.667,
        "noise_w": 0.82,
        "sentence_silence": 0.35,
    },
    "human-lite": {
        "length_scale": 1.02,
        "noise_scale": 0.667,
        "noise_w": 0.90,
        "sentence_silence": 0.45,
    },
}
DEFAULT_TTS_PROFILE = os.environ.get("JARVIS_TTS_PROFILE", "human-lite")
DEFAULT_TTS_NOISE_SCALE = _env_float("JARVIS_TTS_NOISE_SCALE", 0.667)
DEFAULT_TTS_NOISE_W = _env_float("JARVIS_TTS_NOISE_W", 0.90)
DEFAULT_TTS_SENTENCE_SILENCE = _env_float("JARVIS_TTS_SENTENCE_SILENCE", 0.45)
SAMPLE_RATE = 16000
CHUNK = 3200
LIGHTDM_UID = 103
LIGHTDM_RUNTIME = f"/run/user/{LIGHTDM_UID}"
AUDIO_REMOTE = False


def ensure_vosk_path():
    p = str(DEFAULT_PYLIB)
    if p not in sys.path:
        sys.path.insert(0, p)


def _audio_prefix(binary, remote=None):
    if remote is None:
        remote = AUDIO_REMOTE
    if remote:
        return [
            "sudo", "-n", "-u", "lightdm",
            "--preserve-env=XDG_RUNTIME_DIR,PIPEWIRE_RUNTIME_DIR",
            f"/usr/bin/{binary}",
        ]
    return [binary]


def _audio_env(remote=None):
    env = dict(os.environ)
    if remote is None:
        remote = AUDIO_REMOTE
    if remote:
        env["XDG_RUNTIME_DIR"] = LIGHTDM_RUNTIME
        env["PIPEWIRE_RUNTIME_DIR"] = LIGHTDM_RUNTIME
    return env


def _read_dump(remote):
    cmd = _audio_prefix("pw-dump", remote)
    try:
        out = subprocess.check_output(
            cmd, text=True, stderr=subprocess.DEVNULL,
            env=_audio_env(remote), timeout=10,
        )
        return json.loads(out)
    except Exception:
        return []


def _sources_from_dump(objects):
    sources = []
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        info = obj.get("info") or {}
        props = info.get("props") or {}
        if props.get("media.class") != "Audio/Source":
            continue
        name = props.get("node.name") or ""
        desc = props.get("node.description") or name
        api = props.get("api.bluez5") or props.get("bluez5.codec") or ""
        sources.append({
            "id": obj.get("id"),
            "name": name,
            "desc": desc,
            "bluez": "bluez" in name.lower() or bool(api),
        })
    return sources


def audio_sources():
    global AUDIO_REMOTE
    local = _sources_from_dump(_read_dump(False))
    if local:
        AUDIO_REMOTE = False
        return local
    if Path(LIGHTDM_RUNTIME).is_dir():
        remote = _sources_from_dump(_read_dump(True))
        if remote:
            AUDIO_REMOTE = True
            return remote
    AUDIO_REMOTE = False
    return local


def pick_source(value=None):
    sources = audio_sources()
    if value:
        return value, sources
    if not sources:
        return None, sources
    for s in sources:
        if s["bluez"]:
            return str(s["id"]), sources
    return str(sources[0]["id"]), sources


def print_sources(sources):
    if not sources:
        print("No hay fuentes de audio (micrófonos) disponibles en PipeWire.")
        return
    if AUDIO_REMOTE:
        print("(usando la sesión de audio de lightdm para el Bluetooth)",
              file=sys.stderr)
    for s in sources:
        mark = " [bluetooth]" if s["bluez"] else ""
        print(f'{s["id"]:>4}  {s["name"]}  ({s["desc"]}){mark}')


def _sinks_from_dump(objects):
    sinks = []
    for obj in objects:
        if obj.get("type") != "PipeWire:Interface:Node":
            continue
        info = obj.get("info") or {}
        props = info.get("props") or {}
        if props.get("media.class") != "Audio/Sink":
            continue
        name = props.get("node.name") or ""
        desc = props.get("node.description") or name
        api = props.get("api.bluez5") or props.get("bluez5.codec") or ""
        sinks.append({
            "id": obj.get("id"),
            "name": name,
            "desc": desc,
            "bluez": "bluez" in name.lower() or bool(api),
        })
    return sinks


def audio_sinks():
    global AUDIO_REMOTE
    local = _sinks_from_dump(_read_dump(False))
    if any(s["bluez"] for s in local):
        AUDIO_REMOTE = False
        return local
    if Path(LIGHTDM_RUNTIME).is_dir():
        remote = _sinks_from_dump(_read_dump(True))
        if any(s["bluez"] for s in remote):
            AUDIO_REMOTE = True
            return remote
        if remote and not local:
            AUDIO_REMOTE = True
            return remote
    return local


def pick_sink(value=None):
    sinks = audio_sinks()
    if value:
        for s in sinks:
            if str(s["id"]) == str(value) or s["name"] == value:
                return str(s["id"]), s, sinks
        return None, None, sinks
    for s in sinks:
        if s["bluez"]:
            return str(s["id"]), s, sinks
    return None, None, sinks


def play_wav(wav_path, sink=None, timeout=45):
    path = Path(wav_path)
    if not path.is_file():
        return False, ""
    target, info, _ = pick_sink(sink)
    if not target:
        print("TTS: no hay audífono Bluetooth conectado para reproducir.",
              file=sys.stderr)
        return False, ""
    try:
        with wave.open(str(path), "rb") as w:
            rate = w.getframerate()
            channels = w.getnchannels()
            width = w.getsampwidth()
    except Exception as exc:
        print(f"TTS: no se pudo leer el WAV ({exc}).", file=sys.stderr)
        return False, ""
    if width != 2:
        print("TTS: el WAV no es PCM de 16 bits.", file=sys.stderr)
        return False, ""
    cmd = _audio_prefix("pw-cat", None) + [
        "--playback", "--target", target,
        "--format", "s16", "--rate", str(rate),
        "--channels", str(channels), str(path),
    ]
    try:
        subprocess.run(
            cmd, check=True, timeout=timeout, env=_audio_env(None),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except Exception as exc:
        detail = ""
        if isinstance(exc, subprocess.CalledProcessError):
            detail = (exc.stderr or b"").decode("utf-8", "replace").strip()
        print(f"TTS: no se pudo reproducir por Bluetooth ({detail or exc}).",
              file=sys.stderr)
        return False, ""
    return True, (info or {}).get("desc", "")


def _resample(samples, src_rate, dst_rate):
    if src_rate == dst_rate:
        return samples
    out_len = int(len(samples) * dst_rate / src_rate)
    out = []
    step = src_rate / dst_rate
    pos = 0.0
    for _ in range(out_len):
        idx = int(pos)
        frac = pos - idx
        if idx + 1 < len(samples):
            value = samples[idx] * (1.0 - frac) + samples[idx + 1] * frac
        else:
            value = samples[idx]
        out.append(int(value))
        pos += step
    return out


def transcribe_http(model, url, duration):
    import struct
    import urllib.request
    from array import array

    import vosk

    req = urllib.request.Request(url, headers={"User-Agent": "JarvisCAN"})
    with urllib.request.urlopen(req, timeout=15) as resp:
        header = resp.read(12)
        if header[:4] != b"RIFF" or header[8:12] != b"WAVE":
            raise RuntimeError("la URL no entrega un WAV válido")
        fmt = None
        while True:
            chunk_header = resp.read(8)
            if len(chunk_header) < 8:
                raise RuntimeError("WAV sin chunk de datos")
            chunk_id, chunk_size = struct.unpack("<4sI", chunk_header)
            if chunk_id == b"fmt ":
                body = resp.read(chunk_size)
                if len(body) < 16:
                    raise RuntimeError("WAV con formato incompleto")
                fmt = struct.unpack("<HHIIHH", body[:16])
            elif chunk_id == b"data":
                break
            else:
                if chunk_size > 10_000_000:
                    raise RuntimeError("WAV con chunk gigante inesperado")
                resp.read(chunk_size)
        if not fmt:
            raise RuntimeError("WAV sin chunk fmt")
        audio_format, channels, rate, _byte_rate, _block, bits = fmt
        if audio_format != 1 or bits != 16 or channels < 1:
            raise RuntimeError(
                f"formato WAV no soportado: fmt={audio_format} bits={bits} canales={channels}"
            )
        target_bytes = int(duration * rate) * channels * 2
        chunks = []
        got = 0
        deadline = time.monotonic() + duration + 5
        while got < target_bytes and time.monotonic() < deadline:
            data = resp.read(min(65536, target_bytes - got))
            if not data:
                break
            chunks.append(data)
            got += len(data)
        raw = b"".join(chunks)
    if not raw:
        return ""
    samples = array("h")
    samples.frombytes(raw[: len(raw) // 2 * 2])
    if sys.byteorder != "little":
        samples.byteswap()
    if channels > 1:
        mono = array("h")
        frames = len(samples) // channels
        for i in range(frames):
            base = i * channels
            mono.append(sum(samples[base:base + channels]) // channels)
        samples = mono
    samples = _resample(samples, rate, SAMPLE_RATE)
    peak = max((abs(s) for s in samples), default=0)
    if peak > 0:
        gain = min(4.0, 26000.0 / peak)
        if gain > 1.0:
            samples = [max(-32768, min(32767, int(s * gain))) for s in samples]
    rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
    pcm = array("h", samples).tobytes()
    if sys.byteorder != "little":
        pcm = array("h", samples)
        pcm.byteswap()
        pcm = pcm.tobytes()
    pieces = []
    for i in range(0, len(pcm), 4000):
        if rec.AcceptWaveform(pcm[i:i + 4000]):
            text = json.loads(rec.Result()).get("text", "").strip()
            if text:
                pieces.append(text)
    final = json.loads(rec.FinalResult()).get("text", "").strip()
    if final:
        pieces.append(final)
    return " ".join(pieces).strip()


def record_and_transcribe(model, source, duration, url=None):
    import vosk

    if url:
        return transcribe_http(model, url, duration)

    rec = vosk.KaldiRecognizer(model, SAMPLE_RATE)
    cmd = _audio_prefix("pw-cat") + [
        "--record", "--target", str(source),
        "--rate", str(SAMPLE_RATE), "--channels", "1",
        "--format", "s16", "--raw", "-",
    ]
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        bufsize=0, env=_audio_env(),
    )
    pieces = []
    stderr = b""
    start = time.monotonic()
    try:
        while time.monotonic() - start < duration:
            ready, _, _ = select.select([proc.stdout], [], [], 0.5)
            if not ready:
                if proc.poll() is not None:
                    break
                continue
            data = os.read(proc.stdout.fileno(), CHUNK)
            if not data:
                break
            if rec.AcceptWaveform(data):
                text = json.loads(rec.Result()).get("text", "").strip()
                if text:
                    pieces.append(text)
                break
        final = json.loads(rec.FinalResult()).get("text", "").strip()
        if final:
            pieces.append(final)
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=2)
        try:
            stderr = proc.stderr.read() or b""
        except Exception:
            pass
    if proc.returncode not in (0, -15, -9) and stderr:
        sys.stderr.write(stderr.decode("utf-8", "replace"))
    return " ".join(pieces).strip()


def ask(text, show_query=False):
    cmd = [sys.executable, str(ROOT / "scripts" / "jarvis-can-ask.py")]
    if show_query:
        cmd.append("--show-query")
    cmd.append(text)
    env = dict(os.environ)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    res = subprocess.run(
        cmd, cwd=str(ROOT), text=True, capture_output=True, env=env,
    )
    if res.returncode != 0:
        msg = (res.stderr or res.stdout or "").strip()
        raise RuntimeError(msg or f"ask-can falló con código {res.returncode}")
    return res.stdout.strip()


def _tts_text(text, profile="human-lite"):
    text = text.strip()
    text = re.sub(r"\s*\(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z\)", "", text)
    replacements = (
        ("km/h", "kilómetros por hora"),
        ("°C", "grados"),
        ("%", "por ciento"),
        ("RPM", "revoluciones por minuto"),
        ("kPa", "kilopascales"),
        ("g/s", "gramos por segundo"),
    )
    for old, new in replacements:
        text = text.replace(old, new)
    text = re.sub(r"\s+", " ", text).strip()
    if profile == "human":
        text = text.replace(";", ".")
        text = re.sub(r"\s*:\s*", ", ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if text and text[-1] not in ".!?":
            text += "."
    return text


def _piper_env(piper_bin):
    env = dict(os.environ)
    libdir = str(Path(piper_bin).parent)
    current = env.get("LD_LIBRARY_PATH")
    env["LD_LIBRARY_PATH"] = f"{libdir}:{current}" if current else libdir
    return env


def _run_piper(spoken, output_path, piper_bin, piper_model, piper_data,
               length_scale, noise_scale, noise_w, sentence_silence):
    cmd = [
        str(piper_bin),
        "--model", str(piper_model),
        "--output_file", str(output_path),
        "--length_scale", f"{length_scale:.3f}",
        "--noise_scale", f"{noise_scale:.3f}",
        "--noise_w", f"{noise_w:.3f}",
        "--sentence_silence", f"{sentence_silence:.3f}",
        "--quiet",
    ]
    if piper_data.is_dir():
        cmd.extend(["--espeak_data", str(piper_data)])
    try:
        subprocess.run(
            cmd, input=spoken + "\n", text=True, check=True, timeout=120,
            env=_piper_env(piper_bin), stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
    except subprocess.TimeoutExpired:
        raise RuntimeError("Piper tardó demasiado")
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or "").strip()
        raise RuntimeError(err or "Piper falló")


def _concat_wavs(paths, output_path, gap_seconds):
    with wave.open(str(paths[0]), "rb") as first:
        channels = first.getnchannels()
        sampwidth = first.getsampwidth()
        framerate = first.getframerate()
    with wave.open(str(output_path), "wb") as out:
        out.setnchannels(channels)
        out.setsampwidth(sampwidth)
        out.setframerate(framerate)
        for index, path in enumerate(paths):
            with wave.open(str(path), "rb") as part:
                out.writeframes(part.readframes(part.getnframes()))
            if index + 1 < len(paths) and gap_seconds > 0:
                frames = int(framerate * gap_seconds)
                out.writeframes(b"\x00" * frames * channels * sampwidth)


def _synth_piper(spoken, tmp_wav, piper_bin, piper_model, piper_data,
                 length_scale, noise_scale=DEFAULT_TTS_NOISE_SCALE,
                 noise_w=DEFAULT_TTS_NOISE_W,
                 sentence_silence=DEFAULT_TTS_SENTENCE_SILENCE,
                 prosody=False):
    piper_bin = Path(piper_bin)
    piper_model = Path(piper_model)
    piper_data = Path(piper_data)
    if not piper_bin.is_file():
        raise RuntimeError(f"Piper no está instalado: {piper_bin}")
    if not piper_model.is_file():
        raise RuntimeError(f"No existe el modelo Piper: {piper_model}")
    if not prosody:
        _run_piper(spoken, tmp_wav, piper_bin, piper_model, piper_data,
                   length_scale, noise_scale, noise_w, sentence_silence)
        return
    sentences = [
        part.strip()
        for part in re.split(r"(?<=[.!?])\s+", spoken)
        if part.strip()
    ]
    if len(sentences) <= 1:
        _run_piper(spoken, tmp_wav, piper_bin, piper_model, piper_data,
                   length_scale, noise_scale, noise_w, sentence_silence)
        return
    factors = (1.0, 1.035, 0.985, 1.02, 0.995)
    segments = []
    try:
        for index, sentence in enumerate(sentences):
            segment = tmp_wav.with_name(f"{tmp_wav.stem}.seg{index:02d}.wav")
            segment.unlink(missing_ok=True)
            factor = factors[index % len(factors)]
            local_w = max(0.0, noise_w + ((index % 3) - 1) * 0.03)
            _run_piper(
                sentence, segment, piper_bin, piper_model, piper_data,
                length_scale * factor, noise_scale, local_w, 0.0,
            )
            segments.append(segment)
        _concat_wavs(segments, tmp_wav, sentence_silence)
    finally:
        for segment in segments:
            segment.unlink(missing_ok=True)


def _synth_espeak(spoken, tmp_wav, voice, speed):
    try:
        subprocess.run(
            ["espeak-ng", "-v", voice, "-s", str(speed), "-w", str(tmp_wav), spoken],
            check=True, timeout=30,
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
        )
    except FileNotFoundError:
        raise RuntimeError("espeak-ng no está instalado")
    except subprocess.TimeoutExpired:
        raise RuntimeError("espeak-ng tardó demasiado")
    except subprocess.CalledProcessError as exc:
        err = (exc.stderr or b"").decode("utf-8", "replace").strip()
        raise RuntimeError(err or "espeak-ng falló")


def write_tts(text, out_dir=None, engine="auto", piper_bin=None, piper_model=None,
              piper_data=None, length_scale=None, voice="es", speed=150,
              play_audio="auto", sink=None, profile=None,
              noise_scale=None, noise_w=None, sentence_silence=None):
    profile = profile or DEFAULT_TTS_PROFILE
    if profile not in TTS_PROFILES:
        profile = "human-lite"
    params = TTS_PROFILES[profile]
    if length_scale is None:
        length_scale = params["length_scale"]
    if noise_scale is None:
        noise_scale = params["noise_scale"]
    if noise_w is None:
        noise_w = params["noise_w"]
    if sentence_silence is None:
        sentence_silence = params["sentence_silence"]
    out_dir = Path(out_dir) if out_dir else DEFAULT_TTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    wav_path = out_dir / "last_answer.wav"
    tmp_wav = out_dir / ".last_answer.tmp.wav"
    spoken = _tts_text(text, profile=profile)
    if not spoken:
        return None
    if tmp_wav.exists():
        tmp_wav.unlink()
    piper_bin = Path(piper_bin) if piper_bin else DEFAULT_PIPER_BIN
    piper_model = Path(piper_model) if piper_model else DEFAULT_PIPER_MODEL
    piper_data = Path(piper_data) if piper_data else DEFAULT_PIPER_DATA
    piper_ready = piper_bin.is_file() and piper_model.is_file()
    requested = engine
    if engine == "auto":
        engine = "piper" if piper_ready else "espeak"
    used_engine = "espeak"
    if engine == "piper":
        try:
            _synth_piper(
                spoken, tmp_wav, piper_bin, piper_model, piper_data,
                length_scale, noise_scale, noise_w, sentence_silence,
                prosody=(profile == "human"),
            )
            used_engine = "piper"
        except Exception as exc:
            if requested == "piper":
                raise
            _synth_espeak(spoken, tmp_wav, voice, speed)
            print(f"TTS: Piper falló ({exc}); se usó espeak-ng.", file=sys.stderr)
    else:
        _synth_espeak(spoken, tmp_wav, voice, speed)
    os.replace(tmp_wav, wav_path)
    played = False
    sink_desc = ""
    if play_audio != "off":
        played, sink_desc = play_wav(wav_path, sink)
        if play_audio == "on" and not played:
            raise RuntimeError("no se pudo reproducir por el audífono Bluetooth")
    meta = {
        "mtime": wav_path.stat().st_mtime,
        "ts": time.time(),
        "text": text.strip(),
        "played_on_device": played,
        "audio_sink": sink_desc,
        "tts_engine": used_engine,
        "tts_profile": profile,
        "tts_model": piper_model.name if used_engine == "piper" else None,
    }
    tmp_json = out_dir / ".last_answer.json.tmp"
    tmp_json.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_json, out_dir / "last_answer.json")
    return wav_path


def _tts_options(args):
    return {
        "engine": args.tts_engine,
        "piper_bin": args.piper_bin,
        "piper_model": args.tts_model,
        "length_scale": args.tts_length_scale,
        "voice": args.tts_voice,
        "speed": args.tts_speed,
        "play_audio": args.play_audio,
        "sink": args.sink,
        "profile": args.tts_profile,
        "noise_scale": args.tts_noise_scale,
        "noise_w": args.tts_noise_w,
        "sentence_silence": args.tts_sentence_silence,
    }


def main():
    ap = argparse.ArgumentParser(
        description="Consulta por voz al sistema CAN usando Vosk + Ollama.",
    )
    ap.add_argument("--model", default=str(DEFAULT_MODEL))
    ap.add_argument("--source", default=None,
                    help="ID o nombre de la fuente PipeWire")
    ap.add_argument("--url", default=None,
                    help="URL de audio WAV (por ejemplo IP Webcam /audio.wav)")
    ap.add_argument("--duration", type=float, default=8.0,
                    help="segundos máximos de escucha (default 8)")
    ap.add_argument("--auto", action="store_true",
                    help="escucha continua sin pulsar Enter")
    ap.add_argument("--once", action="store_true",
                    help="una sola consulta y salir")
    ap.add_argument("--query", default=None,
                    help="salta el micrófono y consulta este texto")
    ap.add_argument("--show-query", action="store_true",
                    help="muestra la ruta SQL generada")
    ap.add_argument("--no-tts", action="store_true",
                    help="no genera audio de respuesta")
    ap.add_argument("--tts-engine", choices=("auto", "piper", "espeak"),
                    default=DEFAULT_TTS_ENGINE,
                    help="motor de voz: auto, piper o espeak-ng (default auto)")
    ap.add_argument("--tts-model",
                    default=os.environ.get("PIPER_MODEL", str(DEFAULT_PIPER_MODEL)),
                    help="modelo Piper .onnx")
    ap.add_argument("--piper-bin",
                    default=os.environ.get("PIPER_BIN", str(DEFAULT_PIPER_BIN)),
                    help="binario piper")
    ap.add_argument("--tts-length-scale", type=float, default=None,
                    help="velocidad de Piper: >1 más lento (según perfil)")
    ap.add_argument("--tts-profile", choices=tuple(TTS_PROFILES),
                    default=DEFAULT_TTS_PROFILE,
                    help="prosodia: flat, human o human-lite "
                         "(default human-lite en V2)")
    ap.add_argument("--tts-noise-scale", type=float, default=None,
                    help="noise_scale de Piper (según perfil)")
    ap.add_argument("--tts-noise-w", type=float, default=None,
                    help="noise_w de Piper (según perfil)")
    ap.add_argument("--tts-sentence-silence", type=float, default=None,
                    help="segundos de pausa entre frases (según perfil)")
    ap.add_argument("--tts-test", default=None,
                    help="genera TTS de este texto y sale")
    ap.add_argument("--tts-voice", default="es",
                    help="voz de espeak-ng (fallback, default es)")
    ap.add_argument("--tts-speed", type=int, default=150,
                    help="velocidad de espeak-ng (fallback, default 150)")
    ap.add_argument("--play-audio", choices=("auto", "on", "off"),
                    default=os.environ.get("JARVIS_PLAY_AUDIO", "auto"),
                    help="reproducir en el audífono Bluetooth (default auto)")
    ap.add_argument("--sink", default=None,
                    help="ID o nombre del sink PipeWire para la respuesta")
    ap.add_argument("--list-sources", action="store_true")
    args = ap.parse_args()

    params = TTS_PROFILES[args.tts_profile]
    if args.tts_length_scale is None:
        args.tts_length_scale = _env_float(
            "JARVIS_TTS_LENGTH_SCALE", params["length_scale"])
    if args.tts_noise_scale is None:
        args.tts_noise_scale = _env_float(
            "JARVIS_TTS_NOISE_SCALE", params["noise_scale"])
    if args.tts_noise_w is None:
        args.tts_noise_w = _env_float(
            "JARVIS_TTS_NOISE_W", params["noise_w"])
    if args.tts_sentence_silence is None:
        args.tts_sentence_silence = _env_float(
            "JARVIS_TTS_SENTENCE_SILENCE", params["sentence_silence"])

    if args.tts_test:
        try:
            path = write_tts(args.tts_test, **_tts_options(args))
            print(path)
            return 0
        except Exception as exc:
            print(f"TTS: {exc}", file=sys.stderr)
            return 2

    if args.list_sources:
        print_sources(audio_sources())
        return 0

    if args.query:
        answer = ask(args.query, args.show_query)
        print(answer)
        if not args.no_tts:
            try:
                write_tts(answer, **_tts_options(args))
            except Exception as exc:
                print(f"TTS: {exc}", file=sys.stderr)
        return 0

    ensure_vosk_path()
    import vosk
    vosk.SetLogLevel(-1)

    if not Path(args.model).is_dir():
        print(f"No existe el modelo Vosk: {args.model}", file=sys.stderr)
        return 2
    source = None
    if args.url:
        print(f"Fuente de audio: {args.url}", file=sys.stderr)
    else:
        source, sources = pick_source(args.source)
        if not source:
            print("No hay micrófono disponible. Emparejá el manos libre Bluetooth.",
                  file=sys.stderr)
            print_sources(sources)
            return 2
        if AUDIO_REMOTE:
            print("Audio Bluetooth vía sesión de audio de lightdm.", file=sys.stderr)

    print("Cargando modelo Vosk...", file=sys.stderr)
    model = vosk.Model(args.model)
    if source:
        print(f"Micrófono: {source}", file=sys.stderr)
    print("Listo. Hablá claro y de cerca del micrófono.", file=sys.stderr)

    try:
        while True:
            if not args.auto:
                try:
                    cmd = input("Enter para hablar (q para salir): ").strip().lower()
                except EOFError:
                    break
                if cmd in ("q", "quit", "salir"):
                    break
            print("Escuchando...", file=sys.stderr)
            text = record_and_transcribe(model, source, args.duration, args.url)
            if not text:
                print("No se entendió nada.", file=sys.stderr)
                if args.once:
                    return 3
                continue
            print(f"Vos: {text}")
            try:
                answer = ask(text, args.show_query)
                print(answer)
                if not args.no_tts:
                    try:
                        write_tts(answer, **_tts_options(args))
                    except Exception as exc:
                        print(f"TTS: {exc}", file=sys.stderr)
            except Exception as exc:
                print(f"Error consultando: {exc}", file=sys.stderr)
            if args.once:
                break
    except KeyboardInterrupt:
        print("\nChau.", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
