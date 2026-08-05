"""Registre des types d'éléments.

Chaque type est une fonction `(ctx, element) -> Image | None`. Renvoyer None
signifie « rien à dessiner » (asset manquant, météo indisponible...) : le
renderer saute simplement l'élément.

Ajouter une fonctionnalité = ajouter une fonction décorée ici. Ni le renderer
ni la GUI n'ont besoin d'être modifiés.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable

from PIL import Image

from . import weather as weather_mod

log = logging.getLogger(__name__)

# Listes explicites plutôt que strftime("%b") / strftime("%a") : ces formats
# dépendent de la locale LC_TIME du processus. Aujourd'hui Python démarre en
# locale "C" donc ça donne "jan"/"mon", mais n'importe quelle bibliothèque qui
# appelle setlocale() casserait silencieusement les chemins de fichiers.
MONTHS = ["jan", "feb", "mar", "apr", "may", "jun",
          "jul", "aug", "sep", "oct", "nov", "dec"]
WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

ELEMENTS: dict[str, Callable] = {}


def element(name: str):
    """Décorateur d'enregistrement d'un type d'élément."""
    def decorator(fn: Callable) -> Callable:
        ELEMENTS[name] = fn
        return fn
    return decorator


@dataclass
class Ctx:
    """Contexte partagé par tous les éléments d'un même rendu."""

    now: datetime
    assets: Path
    config: dict
    _weather: str | None = field(default=None, init=False, repr=False)
    _weather_done: bool = field(default=False, init=False, repr=False)

    def weather(self) -> str | None:
        """Météo, résolue au premier appel seulement.

        Si aucun élément météo n'est activé, aucun appel réseau n'a lieu.
        """
        if not self._weather_done:
            self._weather = weather_mod.current(self.config["weather"])
            self._weather_done = True
        return self._weather

    def is_night(self) -> bool:
        background = self.config["background"]
        start = int(background["day_start_hour"])
        end = int(background["night_start_hour"])
        hour = self.now.hour
        if start <= end:
            return not (start <= hour < end)
        # Cas où la plage "jour" franchit minuit (ex. 20h -> 4h)
        return not (hour >= start or hour < end)

    def open(self, *parts: str) -> Image.Image | None:
        """Ouvre un asset relatif au dossier assets, ou None s'il manque."""
        path = self.assets.joinpath(*parts)
        if not path.exists():
            log.warning("Asset manquant : %s", path)
            return None
        try:
            return Image.open(path).convert("RGBA")
        except Exception:
            log.exception("Asset illisible : %s", path)
            return None


def _concat_horizontal(images: list[Image.Image], spacing: int = 0) -> Image.Image:
    width = sum(i.width for i in images) + spacing * (len(images) - 1)
    height = max(i.height for i in images)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    x = 0
    for image in images:
        canvas.alpha_composite(image, (x, 0))
        x += image.width + spacing
    return canvas


# --------------------------------------------------------------------------- #
# Types d'éléments
# --------------------------------------------------------------------------- #

@element("month")
def render_month(ctx: Ctx, element_cfg: dict) -> Image.Image | None:
    """Nom du mois. assets/months/<jan..dec>.png"""
    return ctx.open("months", f"{MONTHS[ctx.now.month - 1]}.png")


@element("weekday")
def render_weekday(ctx: Ctx, element_cfg: dict) -> Image.Image | None:
    """Jour de la semaine, variante jour/nuit.

    assets/days/<day|night>/<mon..sun>.png
    Option `force_variant` : "day" ou "night" pour figer la variante.
    """
    variant = element_cfg["options"].get("force_variant")
    if variant not in ("day", "night"):
        variant = "night" if ctx.is_night() else "day"
    return ctx.open("days", variant, f"{WEEKDAYS[ctx.now.weekday()]}.png")


@element("day_number")
def render_day_number(ctx: Ctx, element_cfg: dict) -> Image.Image | None:
    """Numéro du jour composé chiffre par chiffre. assets/date/<0..9>.png

    Options :
      - `zero_pad` (bool, défaut False) : 07 au lieu de 7
      - `spacing` (int, défaut 0) : espace entre les chiffres, peut être négatif
    """
    options = element_cfg["options"]
    text = f"{ctx.now.day:02d}" if options.get("zero_pad") else str(ctx.now.day)

    digits = [ctx.open("date", f"{char}.png") for char in text]
    if any(digit is None for digit in digits):
        return None
    return _concat_horizontal(digits, int(options.get("spacing", 0)))


@element("weather")
def render_weather(ctx: Ctx, element_cfg: dict) -> Image.Image | None:
    """Icône météo. assets/meteo/<sun|cloud|rain|snow>.png"""
    condition = ctx.weather()
    if condition is None:
        return None
    return ctx.open("meteo", f"{condition}.png")


@element("image")
def render_image(ctx: Ctx, element_cfg: dict) -> Image.Image | None:
    """Image statique arbitraire. Option `path`, relative au dossier assets.

    Permet d'ajouter un logo, un cadre ou une décoration sans toucher au code.
    """
    relative = element_cfg["options"].get("path")
    if not relative:
        log.warning("Élément image %r sans option 'path'", element_cfg["id"])
        return None
    return ctx.open(*Path(relative).parts)
