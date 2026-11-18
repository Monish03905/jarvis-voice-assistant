"""
JARVIS Sound System
Handles playing audio files and sound effects.
"""

import os
import logging
import subprocess
import platform
from config import SOUNDS_DIR

logger = logging.getLogger(__name__)

def _play_audio(sound_path: str) -> bool:
    """Internal helper to play audio using available methods."""
    try:
        # Try pygame first
        try:
            import pygame  # type: ignore
            pygame.mixer.init()
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
            return True
        except ImportError:
            logger.debug("pygame not available")
        except Exception as e:
            logger.debug(f"pygame playback failed: {e}")

        # Try playsound second
        try:
            import playsound  # type: ignore
            playsound.playsound(sound_path, block=False)
            return True
        except ImportError:
            logger.debug("playsound not available")
        except Exception as e:
            logger.debug(f"playsound playback failed: {e}")

        # Fallback to system commands
        system = platform.system().lower()
        try:
            if system == "windows":
                subprocess.run(["cmd", "/c", "start", sound_path], check=False)
            elif system == "darwin":
                subprocess.run(["afplay", sound_path], check=False)
            else:
                subprocess.run(["aplay", sound_path], check=False)
            return True
        except Exception as e:
            logger.error(f"Subprocess playback failed: {e}")
            return False

    except Exception as e:
        logger.error(f"Audio playback error: {e}")
        return False

def play_boot_sound() -> bool:
    """Play the JARVIS boot sound."""
    try:
        boot_sound_path = os.path.join(SOUNDS_DIR, "boot.wav")

        if not os.path.exists(boot_sound_path):
            logger.warning(f"Boot sound file not found: {boot_sound_path}")
            return False

        return _play_audio(boot_sound_path)

    except Exception as e:
        logger.error(f"Failed to play boot sound: {e}")
        return False

def play_sound(sound_name: str) -> bool:
    """Play a named sound file."""
    try:
        sound_path = os.path.join(SOUNDS_DIR, f"{sound_name}.wav")

        if not os.path.exists(sound_path):
            logger.warning(f"Sound file not found: {sound_path}")
            return False

        return _play_audio(sound_path)

    except Exception as e:
        logger.error(f"Failed to play sound {sound_name}: {e}")
        return False