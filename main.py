"""Point d'entrée unique.

    persona.exe              génère et applique le fond d'écran (tâche planifiée)
    persona.exe --config     ouvre l'interface de configuration
    persona.exe --dry-run    génère l'image sans toucher au fond d'écran

Le code de retour est non nul en cas d'échec : le Planificateur de tâches
l'affiche dans la colonne « Résultat de la dernière exécution ».
"""

from __future__ import annotations

import argparse
import logging
import sys

from persona import config as config_mod
from persona import logging_setup, paths, renderer

log = logging.getLogger("persona.main")


def generate(dry_run: bool = False) -> int:
    cfg = config_mod.load()
    path = renderer.render_to_file(cfg)

    if dry_run:
        log.info("--dry-run : fond d'écran non appliqué")
        return 0

    from persona import wallpaper
    wallpaper.set_wallpaper(path)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="persona", description="Persona wallpaper")
    parser.add_argument("--config", action="store_true",
                        help="ouvrir l'interface de configuration")
    parser.add_argument("--dry-run", action="store_true",
                        help="générer l'image sans l'appliquer")
    parser.add_argument("--verbose", action="store_true", help="logs DEBUG")
    args = parser.parse_args(argv)

    logging_setup.setup(args.verbose)
    log.info("Démarrage (config=%s, log=%s)", paths.config_path(), paths.log_path())

    try:
        if args.config:
            from persona import gui
            return gui.run(config_mod.load())
        return generate(args.dry_run)
    except Exception:
        # Attrape-tout volontaire : en mode --windowed il n'y a pas de console,
        # donc une trace non loggée serait définitivement perdue.
        log.exception("Échec de l'exécution")
        return 1


if __name__ == "__main__":
    sys.exit(main())
