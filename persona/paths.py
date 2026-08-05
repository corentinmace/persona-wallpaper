"""Résolution des chemins de l'application.

Les chemins diffèrent selon qu'on tourne depuis les sources ou depuis un .exe
PyInstaller. En mode --onefile, sys.executable pointe sur l'exe alors que
__file__ pointe dans le dossier temporaire d'extraction (sys._MEIPASS) : c'est
pour ça qu'on ne peut pas se contenter de __file__.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "persona-wallpaper"


def is_frozen() -> bool:
    """True si on tourne depuis un exécutable PyInstaller."""
    return getattr(sys, "frozen", False)


def app_dir() -> Path:
    """Dossier de l'exe (build) ou racine du projet (sources).

    C'est le dossier à côté duquel on attend le dossier `assets/`.
    """
    if is_frozen():
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def _ensure(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def config_dir() -> Path:
    """%APPDATA%\\persona-wallpaper - config utilisateur, à sauvegarder."""
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / ".config"
    return _ensure(root / APP_NAME)


def data_dir() -> Path:
    """%LOCALAPPDATA%\\persona-wallpaper - cache, logs, image générée.

    Contenu jetable : ne pas y mettre de config.
    """
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / ".cache"
    return _ensure(root / APP_NAME)


def config_path() -> Path:
    return config_dir() / "config.json"


def cache_path() -> Path:
    return data_dir() / "weather-cache.json"


def log_path() -> Path:
    return data_dir() / "persona.log"


def default_assets_dir() -> Path:
    return app_dir() / "assets"


def default_output_path() -> Path:
    return data_dir() / "wallpaper.png"
