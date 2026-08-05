"""Logging.

Le Planificateur de tâches n'affiche aucune sortie : sans fichier de log, un
run raté est totalement invisible. C'est le premier outil de diagnostic.
"""

from __future__ import annotations

import logging
import sys
from logging.handlers import RotatingFileHandler

from . import paths

FORMAT = "%(asctime)s %(levelname)-7s %(name)-18s %(message)s"


def setup(verbose: bool = False) -> None:
    root = logging.getLogger()
    root.setLevel(logging.DEBUG if verbose else logging.INFO)
    root.handlers.clear()

    formatter = logging.Formatter(FORMAT)

    try:
        file_handler = RotatingFileHandler(
            paths.log_path(), maxBytes=512_000, backupCount=2, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)
    except OSError:
        pass  # Disque plein / droits : on continue sans log fichier.

    # En mode --windowed il n'y a pas de console : le handler est inoffensif
    # mais inutile, on ne l'ajoute donc que quand un stderr existe vraiment.
    if sys.stderr is not None:
        stream_handler = logging.StreamHandler(sys.stderr)
        stream_handler.setFormatter(formatter)
        root.addHandler(stream_handler)

    # requests/urllib3 sont bavards en DEBUG.
    logging.getLogger("urllib3").setLevel(logging.WARNING)
