"""Chargement, validation et sauvegarde de la configuration.

Règle directrice : le run horaire ne doit JAMAIS planter à cause de la config.
Une clé manquante est remplacée par son défaut, un fichier corrompu est mis de
côté et remplacé par les défauts. Tout est loggé.
"""

from __future__ import annotations

import copy
import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from . import paths

log = logging.getLogger(__name__)

CONFIG_VERSION = 1

ANCHORS = {
    "top-left": (0.0, 0.0),
    "top": (0.5, 0.0),
    "top-right": (1.0, 0.0),
    "left": (0.0, 0.5),
    "center": (0.5, 0.5),
    "right": (1.0, 0.5),
    "bottom-left": (0.0, 1.0),
    "bottom": (0.5, 1.0),
    "bottom-right": (1.0, 1.0),
}

ELEMENT_DEFAULTS: dict[str, Any] = {
    "id": "",
    "type": "",
    "enabled": True,
    "anchor": "top-left",
    "dx": 0,
    "dy": 0,
    "scale": 1.0,
    "z": 0,
    "options": {},
}

DEFAULT_CONFIG: dict[str, Any] = {
    "version": CONFIG_VERSION,
    # Chemins vides = valeurs calculées (voir paths.py). Renseigne-les pour
    # pointer ailleurs (ex. un dossier d'assets partagé).
    "assets_dir": "",
    "output_path": "",
    "background": {
        "day": "background/day.png",
        "night": "background/night.png",
        "day_start_hour": 7,
        "night_start_hour": 19,
    },
    "weather": {
        "enabled": True,
        "api_key": "b03e11fb78b499fc7bd029dc4a90a701",
        # Purement informatif : la GUI le remplit lors d'une recherche de ville
        # pour que tu voies un nom plutôt que deux nombres.
        "location_name": "",
        "lat": 43.4519,
        "lon": 4.9850,
        # Au-delà de refresh_minutes on retente un appel réseau.
        "refresh_minutes": 30,
        # En cas d'échec réseau, on accepte le cache jusqu'à cet âge.
        # Passé ce délai, l'élément météo est simplement masqué.
        "max_stale_minutes": 240,
        "timeout_seconds": 8,
    },
    # Transposition exacte du script d'origine. Les `z` reproduisent l'ordre
    # des paste() : month, meteo, date, day - donc la date passe par-dessus
    # l'icône météo, ce qui était le comportement d'origine.
    #
    # dx/dy acceptent un entier ou une expression (voir renderer.eval_offset) :
    # les positions d'origine dépendaient des largeurs réelles des PNG, on ne
    # peut donc pas les figer en constantes.
    "elements": [
        {"id": "month", "type": "month", "z": 0,
         "dx": 30, "dy": 30},
        {"id": "weather", "type": "weather", "z": 1,
         "dx": "month.w + date.w", "dy": 30},
        {"id": "date", "type": "day_number", "z": 2,
         "dx": "30 + month.w - 20", "dy": 25},
        {"id": "weekday", "type": "weekday", "z": 3,
         "dx": "round((30 + month.w + date.w + weather.w) / 4)", "dy": 100},
    ],
}


# --------------------------------------------------------------------------- #
# Fusion / normalisation
# --------------------------------------------------------------------------- #

def _merge(default: Any, user: Any) -> Any:
    """Fusion récursive : l'utilisateur écrase, les clés absentes retombent
    sur le défaut. Les listes ne sont pas fusionnées élément par élément
    (les `elements` sont traités à part)."""
    if isinstance(default, dict) and isinstance(user, dict):
        out = dict(default)
        for key, value in user.items():
            out[key] = _merge(default.get(key), value) if key in default else value
        return out
    return default if user is None else user


def _normalize_element(raw: dict, index: int) -> dict:
    element = _merge(ELEMENT_DEFAULTS, raw if isinstance(raw, dict) else {})

    if not element.get("id"):
        element["id"] = f"{element.get('type') or 'element'}-{index}"

    if element.get("anchor") not in ANCHORS:
        log.warning("Ancre inconnue %r sur %r, retour à top-left",
                    element.get("anchor"), element["id"])
        element["anchor"] = "top-left"

    try:
        element["scale"] = float(element.get("scale", 1.0))
    except (TypeError, ValueError):
        element["scale"] = 1.0
    if element["scale"] <= 0:
        element["scale"] = 1.0

    # dx/dy : entier, ou expression texte évaluée au rendu (renderer.eval_offset).
    for key in ("dx", "dy"):
        value = element.get(key, 0)
        if isinstance(value, str):
            stripped = value.strip()
            try:
                element[key] = int(stripped)
            except ValueError:
                element[key] = stripped or 0
        else:
            try:
                element[key] = int(value)
            except (TypeError, ValueError):
                element[key] = 0

    try:
        element["z"] = int(element.get("z", 0))
    except (TypeError, ValueError):
        element["z"] = 0

    element["enabled"] = bool(element.get("enabled", True))
    if not isinstance(element.get("options"), dict):
        element["options"] = {}

    return element


def defaults() -> dict:
    """Config par défaut, normalisée (les éléments sont écrits en forme courte
    dans DEFAULT_CONFIG pour rester lisibles)."""
    return normalize(copy.deepcopy(DEFAULT_CONFIG))


def normalize(raw: dict) -> dict:
    """Complète et corrige une config brute. Ne lève jamais."""
    elements_raw = raw.get("elements")
    if not isinstance(elements_raw, list):
        elements_raw = copy.deepcopy(DEFAULT_CONFIG["elements"])

    cfg = _merge(DEFAULT_CONFIG, {k: v for k, v in raw.items() if k != "elements"})
    cfg["elements"] = [_normalize_element(e, i) for i, e in enumerate(elements_raw)]

    seen: set[str] = set()
    for element in cfg["elements"]:
        base = element["id"]
        suffix = 2
        while element["id"] in seen:
            element["id"] = f"{base}-{suffix}"
            suffix += 1
        seen.add(element["id"])

    return cfg


def migrate(raw: dict) -> dict:
    """Point d'entrée des migrations de schéma.

    Ajoute un bloc `if version < N` à chaque changement cassant, et incrémente
    CONFIG_VERSION. Aujourd'hui il n'y a rien à faire, mais le crochet existe.
    """
    version = raw.get("version", 0)
    if version > CONFIG_VERSION:
        log.warning("Config en version %s, plus récente que %s attendue.",
                    version, CONFIG_VERSION)
    raw["version"] = CONFIG_VERSION
    return raw


# --------------------------------------------------------------------------- #
# I/O
# --------------------------------------------------------------------------- #

def load(path: Path | None = None) -> dict:
    """Charge la config. Crée le fichier avec les défauts s'il n'existe pas."""
    path = path or paths.config_path()

    if not path.exists():
        log.info("Aucune config, création des défauts dans %s", path)
        cfg = defaults()
        save(cfg, path)
        return cfg

    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            raise ValueError("la racine du JSON doit être un objet")
    except Exception:
        backup = path.with_name(f"{path.stem}.broken-{int(time.time())}.json")
        log.exception("Config illisible, mise de côté dans %s", backup)
        try:
            path.replace(backup)
        except OSError:
            log.exception("Impossible de déplacer la config corrompue")
        return defaults()

    return normalize(migrate(raw))


def save(cfg: dict, path: Path | None = None) -> None:
    """Écriture atomique : on écrit à côté puis on remplace, pour ne jamais
    laisser un fichier tronqué si le processus meurt en cours d'écriture."""
    path = path or paths.config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)
    log.info("Config enregistrée dans %s", path)


# --------------------------------------------------------------------------- #
# Accès dérivés
# --------------------------------------------------------------------------- #

def assets_dir(cfg: dict) -> Path:
    return Path(cfg["assets_dir"]) if cfg.get("assets_dir") else paths.default_assets_dir()


def output_path(cfg: dict) -> Path:
    return Path(cfg["output_path"]) if cfg.get("output_path") else paths.default_output_path()
