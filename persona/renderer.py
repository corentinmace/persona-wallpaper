"""Composition du fond d'écran.

`render_layers()` est le point de vérité unique : le CLI l'utilise via
`compose()` pour produire l'image finale, la GUI l'utilise directement pour
afficher chaque élément comme un objet déplaçable sur son canvas. Il n'y a donc
pas deux chemins de rendu qui pourraient diverger.
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import NamedTuple

from PIL import Image

from . import config as config_mod
from .config import ANCHORS
from .elements import ELEMENTS, Ctx

log = logging.getLogger(__name__)

try:  # Pillow >= 9.1
    RESAMPLE = Image.Resampling.LANCZOS
except AttributeError:  # pragma: no cover
    RESAMPLE = Image.LANCZOS


class Layer(NamedTuple):
    element: dict            # la config de l'élément (id, anchor, dx, dy...)
    image: Image.Image       # image déjà mise à l'échelle
    position: tuple[int, int]  # coin haut-gauche, en pixels du fond


def place(bg_size: tuple[int, int], img_size: tuple[int, int],
          anchor: str, dx: int, dy: int) -> tuple[int, int]:
    """Convertit (ancre, décalage) en coordonnées absolues.

    `ax * (bg - img)` interpole entre « collé au bord gauche » (ax=0) et
    « collé au bord droit » (ax=1). Le décalage est toujours appliqué dans le
    sens des coordonnées écran : pour éloigner du bord droit, dx est négatif.
    """
    ax, ay = ANCHORS.get(anchor, ANCHORS["top-left"])
    return (
        round(ax * (bg_size[0] - img_size[0])) + dx,
        round(ay * (bg_size[1] - img_size[1])) + dy,
    )


_TRAILING_CONST = re.compile(r"\s*([+-])\s*(\d+)\s*$")


def shift_offset(value, delta: int):
    """Décale un dx/dy de `delta`, qu'il soit entier ou expression.

    C'est ce qui rend le glisser-déposer compatible avec les expressions : au
    lieu de remplacer `"30 + month.w - 20"` par une constante - ce qui figerait
    la mise en page sur la largeur du mois courant - on produit
    `"30 + month.w + 27"`. La disposition relative survit au déplacement.

    Un `+ N` / `- N` déjà présent en fin de chaîne est absorbé plutôt
    qu'empilé, sinon dix déplacements donneraient dix termes accolés. C'est
    toujours valide : si une expression correcte se termine par un entier sans
    parenthèse fermante derrière, ce terme est forcément au niveau supérieur.
    """
    if delta == 0:
        return value
    if isinstance(value, (int, float)):
        return int(value) + delta

    text = str(value).strip()
    match = _TRAILING_CONST.search(text)
    if match:
        signed = int(match.group(2)) * (1 if match.group(1) == "+" else -1)
        total = signed + delta
        base = text[:match.start()].rstrip()
        if not base:
            return total
        if total == 0:
            return base
        return f"{base} {'+' if total > 0 else '-'} {abs(total)}"

    return f"{text} {'+' if delta > 0 else '-'} {abs(delta)}"


def load_background(ctx: Ctx) -> Image.Image:
    background_cfg = ctx.config["background"]
    key = "night" if ctx.is_night() else "day"
    relative = background_cfg[key]

    path = ctx.assets / relative
    if path.exists():
        return Image.open(path).convert("RGBA")

    log.error("Fond %s introuvable (%s), repli sur un fond uni", key, path)
    return Image.new("RGBA", (1920, 1080), (20, 20, 30, 255))


class Size:
    """Taille exposée aux expressions dx/dy sous la forme `nom.w` / `nom.h`."""

    __slots__ = ("w", "h")

    def __init__(self, w: int, h: int):
        self.w, self.h = w, h

    def __repr__(self) -> str:  # pragma: no cover
        return f"Size({self.w}, {self.h})"


SAFE_FUNCS = {"round": round, "min": min, "max": max, "abs": abs, "int": int}


def eval_offset(value, namespace: dict) -> int:
    """Résout un dx/dy qui peut être un entier ou une expression.

    Les positions du script d'origine étaient relatives aux largeurs réelles
    des PNG (`month.width + date.width`) : on ne peut pas les représenter par
    des constantes. Variables disponibles : `bg.w/.h`, `self.w/.h`, et
    `<id>.w/.h` pour tout élément dont l'identifiant est un nom Python valide.

    L'évaluation se fait sans builtins, avec une poignée de fonctions
    numériques. Ce n'est pas un bac à sable étanche - mais le fichier évalué
    est le config.json de l'utilisateur, qui a déjà les droits de l'exe.
    """
    if isinstance(value, (int, float)):
        return int(value)
    try:
        return int(eval(str(value), {"__builtins__": {}}, namespace))
    except Exception as exc:
        log.warning("Expression invalide %r (%s), décalage mis à 0", value, exc)
        return 0


def render_layers(cfg: dict, now: datetime | None = None) -> tuple[Image.Image, list[Layer]]:
    """Rend le fond et chaque élément activé, sans les fusionner.

    Deux passes : on rend d'abord toutes les images pour connaître leurs
    tailles, puis on résout les positions - sinon une expression ne pourrait
    pas référencer un élément rendu après elle.
    """
    ctx = Ctx(now=now or datetime.now(), assets=config_mod.assets_dir(cfg), config=cfg)
    background = load_background(ctx)

    # --- Passe 1 : rendu ---------------------------------------------------
    rendered: list[tuple[dict, Image.Image]] = []
    for element_cfg in sorted(cfg["elements"], key=lambda e: e["z"]):
        if not element_cfg["enabled"]:
            continue

        renderer = ELEMENTS.get(element_cfg["type"])
        if renderer is None:
            log.warning("Type d'élément inconnu %r (id %r), ignoré",
                        element_cfg["type"], element_cfg["id"])
            continue

        try:
            image = renderer(ctx, element_cfg)
        except Exception:
            log.exception("Échec du rendu de l'élément %r", element_cfg["id"])
            continue

        if image is None:
            continue

        scale = element_cfg["scale"]
        if scale != 1.0:
            size = (max(1, round(image.width * scale)), max(1, round(image.height * scale)))
            image = image.resize(size, RESAMPLE)

        rendered.append((element_cfg, image))

    # --- Passe 2 : positions ----------------------------------------------
    namespace = dict(SAFE_FUNCS)
    namespace["bg"] = Size(*background.size)
    for element_cfg, image in rendered:
        if element_cfg["id"].isidentifier():
            namespace[element_cfg["id"]] = Size(*image.size)

    layers: list[Layer] = []
    for element_cfg, image in rendered:
        scope = dict(namespace, self=Size(*image.size))
        dx = eval_offset(element_cfg["dx"], scope)
        dy = eval_offset(element_cfg["dy"], scope)
        layers.append(Layer(element_cfg, image,
                            place(background.size, image.size,
                                  element_cfg["anchor"], dx, dy)))

    return background, layers


def compose(cfg: dict, now: datetime | None = None) -> Image.Image:
    """Image finale prête à être enregistrée."""
    background, layers = render_layers(cfg, now)
    canvas = background.copy()
    for layer in layers:
        canvas.alpha_composite(layer.image, layer.position)
    return canvas


def render_to_file(cfg: dict, now: datetime | None = None):
    """Compose et enregistre. Renvoie le chemin du fichier produit.

    On aplatit sur du RGB : un PNG avec canal alpha passe mal comme fond
    d'écran Windows selon les versions.
    """
    image = compose(cfg, now)
    flat = Image.new("RGB", image.size, (0, 0, 0))
    flat.paste(image, (0, 0), image)

    destination = config_mod.output_path(cfg)
    destination.parent.mkdir(parents=True, exist_ok=True)
    flat.save(destination, format="PNG")
    log.info("Fond d'écran écrit dans %s", destination)
    return destination
