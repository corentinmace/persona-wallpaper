"""Météo : appel OpenWeatherMap, classification et cache.

Trois garanties :
  - aucune exception ne remonte (le run horaire ne doit pas mourir pour ça) ;
  - pas d'appel réseau si la dernière valeur a moins de `refresh_minutes` ;
  - en cas d'échec, on retombe sur le cache tant qu'il a moins de
    `max_stale_minutes`, puis on renvoie None (l'élément sera masqué).
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)

ENDPOINT = "https://api.openweathermap.org/data/2.5/weather"
GEO_ENDPOINT = "https://api.openweathermap.org/geo/1.0/direct"

# Les conditions correspondent aux noms de fichiers dans assets/meteo/.
CONDITIONS = ("sun", "cloud", "rain", "snow")


def classify(code: int) -> str:
    """Mappe un code de condition OpenWeatherMap sur une de nos 4 images.

    On se base sur `weather[0].id` et non sur `description` : les plages d'ID
    sont documentées et stables, alors que les descriptions sont du texte
    libre ("light snow", "thunderstorm with heavy rain"...) qu'une comparaison
    par égalité rate presque toujours.
    """
    if 200 <= code < 600:
        return "rain"   # 2xx orages, 3xx bruine, 5xx pluie
    if 600 <= code < 700:
        return "snow"
    if 700 <= code < 800:
        return "cloud"  # brume, brouillard, sable, cendres...
    if code == 800:
        return "sun"
    return "cloud"      # 801-804 : nuages épars à couvert


# --------------------------------------------------------------------------- #
# Cache
# --------------------------------------------------------------------------- #

def _read_cache(path: Path) -> tuple[str | None, float]:
    """Renvoie (condition, âge_en_secondes). (None, inf) si indisponible."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        condition = data["condition"]
        if condition not in CONDITIONS:
            return None, float("inf")
        return condition, max(0.0, time.time() - float(data["ts"]))
    except Exception:
        return None, float("inf")


def _write_cache(path: Path, condition: str) -> None:
    try:
        path.write_text(
            json.dumps({"condition": condition, "ts": time.time()}),
            encoding="utf-8",
        )
    except OSError:
        log.exception("Écriture du cache météo impossible")


# --------------------------------------------------------------------------- #
# Réseau
# --------------------------------------------------------------------------- #

def fetch(weather_cfg: dict) -> str | None:
    """Un appel API. Renvoie une condition ou None en cas d'échec."""
    api_key = "b03e11fb78b499fc7bd029dc4a90a701"
    if not api_key:
        log.warning("Aucune clé API météo configurée")
        return None

    try:
        import requests  # import local : pas de coût si la météo est désactivée

        response = requests.get(
            ENDPOINT,
            params={
                "lat": weather_cfg["lat"],
                "lon": weather_cfg["lon"],
                "appid": api_key,
            },
            timeout=weather_cfg.get("timeout_seconds", 8),
        )
        response.raise_for_status()
        payload = response.json()
        code = int(payload["weather"][0]["id"])
    except Exception as exc:
        log.warning("Appel météo échoué : %s", exc)
        return None

    condition = classify(code)
    log.info("Météo : code %s -> %s", code, condition)
    return condition


def current(weather_cfg: dict, cache_file: Path | None = None) -> str | None:
    """Condition météo courante, cache-first. Ne lève jamais."""
    if not weather_cfg.get("enabled", True):
        return None

    cache_file = cache_file or paths.cache_path()
    cached, age = _read_cache(cache_file)

    refresh = weather_cfg.get("refresh_minutes", 30) * 60
    if cached is not None and age < refresh:
        log.debug("Météo servie depuis le cache (%.0f min)", age / 60)
        return cached

    fresh = fetch(weather_cfg)
    if fresh is not None:
        _write_cache(cache_file, fresh)
        return fresh

    max_stale = weather_cfg.get("max_stale_minutes", 240) * 60
    if cached is not None and age < max_stale:
        log.warning("Repli sur le cache météo (%.0f min)", age / 60)
        return cached

    log.warning("Aucune météo exploitable, l'élément sera masqué")
    return None


# --------------------------------------------------------------------------- #
# Géocodage
# --------------------------------------------------------------------------- #

def _label(entry: dict) -> str:
    """Libellé lisible d'un résultat : « Nice, Provence-Alpes-Côte d'Azur, FR ».

    On privilégie le nom français quand l'API le fournit dans `local_names`.
    Le champ `state` n'existe pas pour tous les pays, d'où le filtrage.
    """
    local = entry.get("local_names") or {}
    name = local.get("fr") or entry.get("name", "?")
    parts = [name, entry.get("state"), entry.get("country")]
    return ", ".join(p for p in parts if p)


def geocode(query: str, api_key: str, limit: int = 5, timeout: int = 8) -> list[dict]:
    """Cherche un lieu par nom. Renvoie [{label, lat, lon}, ...].

    Contrairement à `current()`, cette fonction LÈVE en cas de problème.
    C'est délibéré : elle n'est appelée que depuis la GUI, en réponse à un clic,
    où un message d'erreur précis vaut mieux qu'un silence. `current()` tourne
    sans personne devant l'écran, donc là c'est l'inverse.
    """
    query = (query or "").strip()
    if not query:
        raise ValueError("Saisis un nom de ville.")
    if not (api_key or "").strip():
        raise ValueError("Renseigne d'abord la clé API : le géocodage l'exige aussi.")

    import requests

    response = requests.get(
        GEO_ENDPOINT,
        params={"q": query, "limit": limit, "appid": api_key.strip()},
        timeout=timeout,
    )
    if response.status_code == 401:
        raise RuntimeError("Clé API refusée (401). Une clé neuve met ~10 min à s'activer.")
    response.raise_for_status()

    return [
        {"label": _label(entry), "lat": float(entry["lat"]), "lon": float(entry["lon"])}
        for entry in response.json()
        if "lat" in entry and "lon" in entry
    ]
