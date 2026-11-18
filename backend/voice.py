"""Voice engine: wake word, speech-to-text, text-to-speech, speaker lock.

Pipeline
--------
openWakeWord ("hey jarvis") -> record command -> faster-whisper -> voiceprint
check -> agent. Speech is played through Edge-TTS with a British voice.

Every stage degrades gracefully: if a heavy dependency is missing the engine
falls back to a simpler implementation instead of crashing the assistant.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import numpy as np

import config as cfg

log = logging.getLogger(__name__)

_WAKE_ASSETS = {
    "hey_jarvis_v0.1.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/hey_jarvis_v0.1.onnx",
    "melspectrogram.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/melspectrogram.onnx",
    "embedding_model.onnx": "https://github.com/dscripka/openWakeWord/releases/download/v0.5.1/embedding_model.onnx",
}


def _ensure_wake_assets() -> None:
    """Fetch the openWakeWord ONNX assets on first run (they are not shipped in the wheel)."""
    try:
        import shutil
        import urllib.request

        import openwakeword  # type: ignore

        base = Path(openwakeword.__file__).resolve().parent / "resources" / "models"
        base.mkdir(parents=True, exist_ok=True)
        for name, url in _WAKE_ASSETS.items():
            target = base / name
            if target.exists() and target.stat().st_size > 100_000:
                continue
            log.info("Downloading wake-word asset %s", name)
            tmp = target.with_suffix(target.suffix + ".part")
            with urllib.request.urlopen(url, timeout=45) as response, open(tmp, "wb") as handle:
                shutil.copyfileobj(response, handle)
            tmp.replace(target)
    except Exception as exc:
        log.warning("Wake-word asset download failed: %s", exc)

SAMPLE_RATE = 16000
BLOCK = 1280  # 80 ms at 16 kHz - openWakeWord's expected chunk


# ---------------------------------------------------------------------------
# Speaker verification
# ---------------------------------------------------------------------------
class SpeakerVerifier:
    """Resemblyzer voiceprint with a numpy-only fallback."""

    def __init__(self) -> None:
        self.path = Path(cfg.VOICEPRINT_PATH)
        self._encoder = None
        self._mode = "none"
        self._print: Optional[np.ndarray] = None
        self._init_backend()
        self._load()

    def _init_backend(self) -> None:
        try:
            from resemblyzer import VoiceEncoder  # type: ignore

            self._encoder = VoiceEncoder("cpu", verbose=False)
            self._mode = "resemblyzer"
            log.info("Speaker verification: resemblyzer")
        except Exception as exc:
            log.warning("resemblyzer unavailable (%s); using spectral fallback", exc)
            self._mode = "spectral"

    # ---------------------------------------------------------------- helpers
    def _embed(self, audio: np.ndarray, sr: int = SAMPLE_RATE) -> Optional[np.ndarray]:
        audio = np.asarray(audio, dtype=np.float32).flatten()
        if audio.size < sr * 0.6:
            return None
        if np.max(np.abs(audio)) > 1.5:
            audio = audio / 32768.0
        try:
            if self._mode == "resemblyzer" and self._encoder is not None:
                from resemblyzer import preprocess_wav  # type: ignore

                wav = preprocess_wav(audio, source_sr=sr)
                vec = self._encoder.embed_utterance(wav)
            else:
                vec = self._spectral_embedding(audio, sr)
            norm = np.linalg.norm(vec)
            return vec / norm if norm else None
        except Exception as exc:
            log.warning("embedding failed: %s", exc)
            return None

    @staticmethod
    def _spectral_embedding(audio: np.ndarray, sr: int) -> np.ndarray:
        """Cheap timbre fingerprint: log-mel-ish band energies per frame."""
        frame, hop = 400, 160
        if audio.size < frame:
            audio = np.pad(audio, (0, frame - audio.size))
        frames = np.lib.stride_tricks.sliding_window_view(audio, frame)[::hop]
        window = np.hanning(frame)
        spec = np.abs(np.fft.rfft(frames * window, axis=1))
        freqs = np.fft.rfftfreq(frame, 1.0 / sr)
        bands = np.array_split(np.arange(len(freqs)), 32)
        energy = np.array([spec[:, b].mean(axis=1) for b in bands]).T
        energy = np.log(energy + 1e-8)
        feat = np.concatenate([energy.mean(axis=0), energy.std(axis=0)])
        return feat.astype(np.float64)

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._print = np.load(self.path)
                log.info("Voiceprint loaded (%s)", self._mode)
            except Exception as exc:
                log.warning("Could not load voiceprint: %s", exc)

    # ------------------------------------------------------------------ API
    @property
    def enrolled(self) -> bool:
        return self._print is not None

    @property
    def mode(self) -> str:
        return self._mode

    def enroll(self, audio: np.ndarray, sr: int = SAMPLE_RATE) -> tuple[bool, float]:
        """Build a voiceprint from several windows of the same recording."""
        audio = np.asarray(audio, dtype=np.float32).flatten()
        if np.max(np.abs(audio)) > 1.5:
            audio = audio / 32768.0
        if audio.size < sr * 3:
            return False, 0.0
        window = sr * 2
        vectors = []
        for start in range(0, max(1, audio.size - window), window // 2):
            vec = self._embed(audio[start:start + window], sr)
            if vec is not None:
                vectors.append(vec)
        if not vectors:
            return False, 0.0
        mean = np.mean(vectors, axis=0)
        mean /= np.linalg.norm(mean) or 1.0
        self.path.parent.mkdir(parents=True, exist_ok=True)
        np.save(self.path, mean)
        self._print = mean
        spread = float(np.mean([np.dot(v, mean) for v in vectors]))
        return True, spread

    def verify(self, audio: np.ndarray, sr: int = SAMPLE_RATE) -> tuple[bool, float]:
        if not cfg.VOICE_LOCK_ENABLED:
            return True, 1.0
        if self._print is None:
            return False, 0.0
        vec = self._embed(audio, sr)
        if vec is None:
            return False, 0.0
        score = float(np.dot(vec, self._print))
        threshold = cfg.VOICE_MATCH_THRESHOLD
        if self._mode == "spectral":
            threshold = max(threshold, 0.88)
        return score >= threshold, round(score, 3)

    def clear(self) -> None:
        if self.path.exists():
            self.path.unlink()
        self._print = None


# ---------------------------------------------------------------------------
# Speech-to-text
# ---------------------------------------------------------------------------
class Transcriber:
    def __init__(self) -> None:
        self._model = None
        self._lock = threading.Lock()
        self._failed = False

    def _ensure(self):
        if self._model is not None or self._failed:
            return self._model
        with self._lock:
            if self._model is not None or self._failed:
                return self._model
            try:
                from faster_whisper import WhisperModel  # type: ignore

                log.info("Loading faster-whisper model %s ...", cfg.STT_MODEL)
                self._model = WhisperModel(
                    cfg.STT_MODEL,
                    device=cfg.STT_DEVICE,
                    compute_type=cfg.STT_COMPUTE_TYPE,
                    download_root=str(cfg.MODELS_DIR),
                )
                log.info("Whisper ready.")
            except Exception as exc:
                log.error("Whisper unavailable: %s", exc)
                self._failed = True
        return self._model

    def warm(self) -> None:
        threading.Thread(target=self._ensure, daemon=True).start()

    def transcribe(self, audio: np.ndarray, sr: int = SAMPLE_RATE) -> str:
        audio = np.asarray(audio, dtype=np.float32).flatten()
        if np.max(np.abs(audio)) > 1.5:
            audio = audio / 32768.0
        if audio.size < sr * 0.25:
            return ""
        model = self._ensure()
        if model is None:
            return ""
        try:
            segments, info = model.transcribe(
                audio,
                language="en",
                beam_size=1,
                vad_filter=True,
                condition_on_previous_text=False,
            )
            text = " ".join(seg.text for seg in segments).strip()
            return re.sub(r"\s+", " ", text)
        except Exception as exc:
            log.warning("transcription failed: %s", exc)
            return ""


# ---------------------------------------------------------------------------
# Text-to-speech
# ---------------------------------------------------------------------------
class Speaker:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._speaking = threading.Event()
        self._pyttsx3 = None
        self._sentence = re.compile(r"[^.!?]+[.!?]?")

    @property
    def busy(self) -> bool:
        return self._speaking.is_set()

    def _chunks(self, text: str) -> list[str]:
        parts = [p.strip() for p in self._sentence.findall(text or "") if p.strip()]
        return parts or ([text] if text else [])

    def speak(self, text: str) -> None:
        text = (text or "").strip()
        if not text:
            return
        with self._lock:
            self._speaking.set()
            try:
                for chunk in self._chunks(text):
                    if not self._speak_chunk(chunk):
                        self._pyttsx3_speak(chunk)
            except Exception as exc:
                log.warning("TTS failed: %s", exc)
                try:
                    self._pyttsx3_speak(text)
                except Exception:
                    pass
            finally:
                self._speaking.clear()

    def _speak_chunk(self, text: str) -> bool:
        if cfg.TTS_ENGINE in {"off", "none", "mute"}:
            return True
        if cfg.TTS_ENGINE == "pyttsx3":
            return False
        if cfg.TTS_ENGINE == "elevenlabs" and cfg.ELEVENLABS_API_KEY:
            if self._elevenlabs(text):
                return True
        return self._edge(text)

    def _edge(self, text: str) -> bool:
        try:
            import edge_tts  # type: ignore
        except Exception:
            return False
        try:
            import hashlib

            cache_dir = Path(cfg.CACHE_DIR) / "tts"
            cache_dir.mkdir(parents=True, exist_ok=True)
            key = hashlib.sha1(
                f"{text}|{cfg.TTS_VOICE}|{cfg.TTS_RATE}".encode("utf-8")
            ).hexdigest()[:20]
            cached = cache_dir / f"{key}.mp3"
            if cached.exists() and cached.stat().st_size > 1024:
                return self._play_file(cached)
        except Exception:
            cached = None

        tmp = Path(tempfile.gettempdir()) / f"jarvis_tts_{os.getpid()}_{int(time.time()*1000)}.mp3"
        try:
            async def synth():
                comm = edge_tts.Communicate(text, cfg.TTS_VOICE, rate=cfg.TTS_RATE)
                await comm.save(str(tmp))

            asyncio.run(synth())
            if cached:
                try:
                    tmp.replace(cached)
                    tmp = cached
                except Exception:
                    pass
            return self._play_file(tmp)
        except Exception as exc:
            log.debug("edge-tts failed: %s", exc)
            return False
        finally:
            if cached is None or tmp != cached:
                try:
                    tmp.unlink(missing_ok=True)
                except Exception:
                    pass

    def _elevenlabs(self, text: str) -> bool:
        try:
            import requests  # local import keeps startup fast

            r = requests.post(
                f"https://api.elevenlabs.io/v1/text-to-speech/{cfg.ELEVENLABS_VOICE_ID}",
                headers={"xi-api-key": cfg.ELEVENLABS_API_KEY},
                json={"text": text, "model_id": "eleven_turbo_v2_5"},
                timeout=30,
            )
            if r.status_code != 200:
                return False
            tmp = Path(tempfile.gettempdir()) / f"jarvis_el_{int(time.time()*1000)}.mp3"
            tmp.write_bytes(r.content)
            try:
                return self._play_file(tmp)
            finally:
                tmp.unlink(missing_ok=True)
        except Exception as exc:
            log.debug("elevenlabs failed: %s", exc)
            return False

    @staticmethod
    def _play_file(path: Path) -> bool:
        try:
            import miniaudio  # type: ignore
            import sounddevice as sd  # type: ignore

            decoded = miniaudio.decode_file(str(path))
            samples = np.frombuffer(decoded.samples, dtype=np.int16)
            if decoded.nchannels > 1:
                samples = samples.reshape(-1, decoded.nchannels).mean(axis=1).astype(np.int16)
            sd.play(samples, samplerate=decoded.sample_rate, blocking=True)
            return True
        except Exception:
            pass
        # ffplay is present on most machines that already have ffmpeg
        try:
            ffplay = subprocess.run(
                ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", str(path)],
                timeout=120,
            )
            return ffplay.returncode == 0
        except Exception:
            return False

    def _pyttsx3_speak(self, text: str) -> None:
        if self._pyttsx3 is None:
            import pyttsx3  # type: ignore

            engine = pyttsx3.init()
            engine.setProperty("rate", int(185 * (cfg.VOICE_SPEED or 1.0)))
            engine.setProperty("volume", 0.95)
            for voice in engine.getProperty("voices"):
                if "english" in (voice.name or "").lower() and (
                    "great britain" in (voice.name or "").lower() or "george" in (voice.name or "").lower()
                ):
                    engine.setProperty("voice", voice.id)
                    break
            self._pyttsx3 = engine
        self._pyttsx3.say(text)
        self._pyttsx3.runAndWait()


# ---------------------------------------------------------------------------
# Microphone helpers
# ---------------------------------------------------------------------------
def list_microphones() -> list[dict]:
    try:
        import sounddevice as sd  # type: ignore

        devices = []
        for idx, dev in enumerate(sd.query_devices()):
            if dev.get("max_input_channels", 0) > 0:
                devices.append({"index": idx, "name": dev["name"]})
        return devices
    except Exception:
        return []


def _open_input():
    import sounddevice as sd  # type: ignore

    device = None
    if cfg.MIC_DEVICE not in (None, ""):
        try:
            device = int(cfg.MIC_DEVICE)
        except ValueError:
            device = cfg.MIC_DEVICE
    return sd.InputStream(
        channels=1,
        samplerate=SAMPLE_RATE,
        blocksize=BLOCK,
        dtype="int16",
        device=device,
    )


def record_command(max_seconds: float = 12.0, silence: float = 0.9,
                   min_seconds: float = 0.5) -> np.ndarray:
    """Standalone recording used for voice enrollment and the web UI."""
    chunks: list[np.ndarray] = []
    speech_started = False
    silent_for = 0.0
    elapsed = 0.0
    with _open_input() as stream:
        # estimate noise floor
        noise = []
        for _ in range(5):
            data, _ = stream.read(BLOCK)
            noise.append(float(np.sqrt(np.mean(data.astype(np.float32) ** 2))))
        floor = max(120.0, float(np.mean(noise)) * 2.2)
        while elapsed < max_seconds:
            data, _ = stream.read(BLOCK)
            chunks.append(data.copy())
            elapsed += BLOCK / SAMPLE_RATE
            rms = float(np.sqrt(np.mean(data.astype(np.float32) ** 2)))
            if rms > floor:
                speech_started = True
                silent_for = 0.0
            elif speech_started:
                silent_for += BLOCK / SAMPLE_RATE
            if speech_started and silent_for >= silence and elapsed >= min_seconds:
                break
    if not chunks:
        return np.zeros(0, dtype=np.int16)
    return np.concatenate(chunks).flatten()


# ---------------------------------------------------------------------------
# Wake-word engine
# ---------------------------------------------------------------------------
class VoiceEngine:
    def __init__(self) -> None:
        self.transcriber = Transcriber()
        self.speaker = Speaker()
        self._verifier: Optional[SpeakerVerifier] = None
        self._verifier_lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._oww = None
        self._state_cb: Optional[Callable[[str], None]] = None

    @property
    def verifier(self) -> SpeakerVerifier:
        # Loading resemblyzer pulls in torch (~10-15 s), so do it lazily and only once.
        if self._verifier is None:
            with self._verifier_lock:
                if self._verifier is None:
                    self._verifier = SpeakerVerifier()
        return self._verifier

    @property
    def enrolled(self) -> bool:
        return self._verifier.enrolled if self._verifier else Path(cfg.VOICEPRINT_PATH).exists()

    @property
    def mode(self) -> str:
        return self._verifier.mode if self._verifier else "loading"

    def forget_voiceprint(self) -> None:
        if self._verifier is not None:
            self._verifier.clear()
        else:
            Path(cfg.VOICEPRINT_PATH).unlink(missing_ok=True)

    # ------------------------------------------------------------------ state
    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._stop.set()

    def enroll(self, seconds: int | None = None) -> tuple[bool, float, str]:
        seconds = seconds or cfg.VOICE_ENROLL_SECONDS
        self.speaker.speak(
            "Please read this sentence aloud: The quick brown fox jumps over the lazy dog, "
            "and Jarvis keeps the house in order."
        )
        time.sleep(0.4)
        audio = record_command(max_seconds=seconds, silence=1.2, min_seconds=seconds * 0.5)
        ok, score = self.verifier.enroll(audio.astype(np.float32) / 32768.0)
        if ok:
            self.speaker.speak("Voice profile saved. I will only take orders from you now.")
        else:
            self.speaker.speak("I could not capture enough speech. Please try again.")
        return ok, round(score, 3), self.verifier.mode

    def test_voice(self) -> tuple[bool, float]:
        self.speaker.speak("Say a few words so I can check your voice.")
        time.sleep(0.3)
        audio = record_command(max_seconds=6, silence=0.8, min_seconds=1.0)
        return self.verifier.verify(audio.astype(np.float32) / 32768.0)

    # ------------------------------------------------------------- wake model
    def _load_oww(self):
        if self._oww is not None:
            return self._oww
        try:
            from openwakeword.model import Model  # type: ignore

            _ensure_wake_assets()
            self._oww = Model(wakeword_models=["hey_jarvis"], inference_framework="onnx")
            log.info("openWakeWord 'hey_jarvis' loaded")
            return self._oww
        except Exception as exc:
            log.warning("openWakeWord unavailable: %s", exc)
            return None

    # ------------------------------------------------------------------- loop
    def run_loop(self, on_command: Callable[[str, bool, float], None],
                 on_state: Optional[Callable[[str], None]] = None) -> None:
        """Blocking loop; start it in a daemon thread."""
        self._stop.clear()
        self._state_cb = on_state
        _ = self.verifier  # load the voiceprint model in this worker thread
        self.transcriber.warm()
        wake_model = self._load_oww()
        if wake_model is None:
            self._whisper_loop(on_command)
            return

        self._emit("LISTENING")
        buffer: list[np.ndarray] = []
        triggered = False
        speech_started = False
        silence = 0.0
        elapsed = 0.0
        noise = []
        floor = 180.0

        try:
            with _open_input() as stream:
                # calibrate background noise while waking up
                for _ in range(8):
                    data, _ = stream.read(BLOCK)
                    noise.append(float(np.sqrt(np.mean(data.astype(np.float32) ** 2))))
                floor = max(150.0, float(np.mean(noise)) * 2.0)

                while not self._stop.is_set():
                    data, _ = stream.read(BLOCK)
                    pcm = data.flatten()

                    if not triggered:
                        if self.speaker.busy:
                            time.sleep(0.01)
                            continue
                        try:
                            scores = wake_model.predict(pcm)
                            score = float(max(scores.values())) if scores else 0.0
                        except Exception:
                            score = 0.0
                        if score >= cfg.WAKE_THRESHOLD:
                            log.info("Wake word detected (%.2f)", score)
                            triggered = True
                            buffer = []
                            speech_started = False
                            silence = 0.0
                            elapsed = 0.0
                            try:
                                wake_model.reset()
                            except Exception:
                                pass
                            self._emit("HEARD")
                            self.speaker.speak("Yes?")
                            self._emit("LISTENING")
                        continue

                    buffer.append(pcm.copy())
                    elapsed += BLOCK / SAMPLE_RATE
                    rms = float(np.sqrt(np.mean(pcm.astype(np.float32) ** 2)))
                    if rms > floor:
                        speech_started = True
                        silence = 0.0
                    elif speech_started:
                        silence += BLOCK / SAMPLE_RATE

                    done = (speech_started and silence >= 0.9 and elapsed > 0.6) or elapsed > 12
                    if not done:
                        continue

                    triggered = False
                    audio = np.concatenate(buffer).astype(np.float32) / 32768.0
                    self._emit("PROCESSING")
                    text = self.transcriber.transcribe(audio)
                    if text:
                        ok, score = self.verifier.verify(audio)
                        self._emit("VERIFYING")
                        on_command(text, ok, score)
                    self._emit("LISTENING")
        except Exception as exc:
            log.exception("Voice loop crashed: %s", exc)
            self._emit("ERROR")
        finally:
            try:
                if self._oww is not None:
                    self._oww.reset()
            except Exception:
                pass

    def _whisper_loop(self, on_command: Callable[[str, bool, float], None]) -> None:
        """Fallback: listen in short windows and look for the wake word."""
        self._emit("LISTENING")
        while not self._stop.is_set():
            if self.speaker.busy:
                time.sleep(0.2)
                continue
            audio = record_command(max_seconds=4.0, silence=0.7, min_seconds=0.4)
            if audio.size == 0:
                continue
            audio_f = audio.astype(np.float32) / 32768.0
            text = self.transcriber.transcribe(audio_f)
            if not text:
                continue
            low = text.lower()
            if "jarvis" not in low and cfg.WAKE_WORD not in low:
                continue
            remainder = re.sub(r".*?(hey\s+)?jarvis[,:]?", "", low).strip()
            if len(remainder.split()) < 2:
                self.speaker.speak("Yes?")
                audio = record_command(max_seconds=12, silence=0.9)
                audio_f = audio.astype(np.float32) / 32768.0
                remainder = self.transcriber.transcribe(audio_f)
                text = remainder
            if text:
                ok, score = self.verifier.verify(audio_f)
                on_command(text, ok, score)

    def _emit(self, state: str) -> None:
        if self._state_cb:
            try:
                self._state_cb(state)
            except Exception:
                pass

    def start(self, on_command, on_state=None) -> None:
        if os.getenv("VOICE_DISABLED", "").lower() in {"1", "true", "yes"}:
            log.info("Microphone loop disabled via VOICE_DISABLED.")
            return
        if self.running:
            return
        self._stop.clear()
        # Drain any dead thread before replacing it.
        if self._thread is not None:
            self._thread.join(timeout=1)
        self._thread = threading.Thread(
            target=self.run_loop, args=(on_command, on_state), daemon=True, name="voice-loop"
        )
        self._thread.start()
