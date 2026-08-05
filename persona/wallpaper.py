"""Application du fond d'écran sous Windows.

Isolé dans son propre module et importé paresseusement pour que le reste du
projet (rendu, config, GUI) reste testable sur une machine non-Windows.
"""

from __future__ import annotations

import logging
from pathlib import Path

log = logging.getLogger(__name__)

# Styles acceptés par la clé de registre WallpaperStyle.
STYLES = {
    "fill": "10",
    "fit": "6",
    "stretch": "2",
    "center": "0",
    "span": "22",
}


def set_wallpaper(path: Path, style: str = "fill") -> None:
    """Définit le fond d'écran. Le chemin doit être absolu."""
    import win32api
    import win32con
    import win32gui

    key = win32api.RegOpenKeyEx(
        win32con.HKEY_CURRENT_USER,
        "Control Panel\\Desktop",
        0,
        win32con.KEY_SET_VALUE,
    )
    try:
        win32api.RegSetValueEx(key, "WallpaperStyle", 0, win32con.REG_SZ,
                               STYLES.get(style, STYLES["fill"]))
        win32api.RegSetValueEx(key, "TileWallpaper", 0, win32con.REG_SZ, "0")
    finally:
        win32api.RegCloseKey(key)

    # SPIF_UPDATEINIFILE (1) écrit le changement, SPIF_SENDWININICHANGE (2)
    # notifie les applications ouvertes.
    win32gui.SystemParametersInfo(
        win32con.SPI_SETDESKWALLPAPER,
        str(Path(path).resolve()),
        1 | 2,
    )
    log.info("Fond d'écran appliqué (%s, style=%s)", path, style)
