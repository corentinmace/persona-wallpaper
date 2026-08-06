"""GUI de configuration (Tkinter).

Le cœur de l'interface est l'aperçu : chaque élément est un objet distinct du
canvas qu'on déplace à la souris, et le relâchement recalcule (dx, dy) via
`renderer.unplace()`. Les champs numériques restent disponibles pour un
ajustement fin, mais on ne se sert d'eux qu'en dernier recours.
"""

from __future__ import annotations

import copy
import json
import logging
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from PIL import ImageTk

from . import config as config_mod
from . import renderer
from . import weather as weather_mod
from .config import ANCHORS
from .elements import ELEMENTS

log = logging.getLogger(__name__)

PREVIEW_MAX = (760, 430)

HINT = ("Glisse les éléments pour les positionner. Ctrl+clic ajoute à la "
        "sélection, les flèches déplacent d'un pixel (10 avec Maj).")


class App(tk.Tk):
    def __init__(self, cfg: dict):
        super().__init__()
        self.title("Persona Wallpaper - configuration")
        self.minsize(1120, 620)

        self.cfg = copy.deepcopy(cfg)
        self.dirty = False

        self._photo_refs: list[ImageTk.PhotoImage] = []
        self._items: dict[int, dict] = {}       # id d'item canvas -> infos calque
        self._preview_scale = 1.0
        self._bg_size = (1920, 1080)
        self._drag = None
        self._rubber = None
        self._refresh_job = None
        self._loading = False

        self._build_ui()
        self.refresh_preview()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ------------------------------------------------------------------ #
    # Construction de l'interface
    # ------------------------------------------------------------------ #

    def _build_ui(self) -> None:
        paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        paned.pack(fill=tk.BOTH, expand=True, padx=8, pady=8)

        left = ttk.Frame(paned)
        self.canvas = tk.Canvas(left, background="#1a1a1a", highlightthickness=0,
                                width=PREVIEW_MAX[0], height=PREVIEW_MAX[1])
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind("<ButtonPress-1>", self._on_press)
        self.canvas.bind("<B1-Motion>", self._on_motion)
        self.canvas.bind("<ButtonRelease-1>", self._on_release)
        for key in ("Left", "Right", "Up", "Down"):
            self.canvas.bind(f"<Key-{key}>", self._on_arrow)
            self.canvas.bind(f"<Shift-Key-{key}>", self._on_arrow)
        self.canvas.config(takefocus=True)

        self.hint = ttk.Label(left, text=HINT, wraplength=740, justify="left")
        self.hint.pack(anchor="w", pady=(6, 0))
        paned.add(left, weight=3)

        right = ttk.Frame(paned)
        notebook = ttk.Notebook(right)
        notebook.pack(fill=tk.BOTH, expand=True)
        notebook.add(self._build_elements_tab(notebook), text="Éléments")
        notebook.add(self._build_weather_tab(notebook), text="Météo")
        notebook.add(self._build_general_tab(notebook), text="Général")
        paned.add(right, weight=2)

        bar = ttk.Frame(self)
        bar.pack(fill=tk.X, padx=8, pady=(0, 8))
        ttk.Button(bar, text="Rafraîchir l'aperçu", command=self.refresh_preview).pack(side=tk.LEFT)
        ttk.Button(bar, text="Enregistrer et appliquer",
                   command=self.save_and_apply).pack(side=tk.RIGHT)
        ttk.Button(bar, text="Enregistrer", command=self.save).pack(side=tk.RIGHT, padx=6)

    def _build_elements_tab(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=8)

        self.tree = ttk.Treeview(frame, columns=("type", "on"), show="headings",
                                 height=8, selectmode="extended")
        self.tree.heading("type", text="Type")
        self.tree.heading("on", text="Actif")
        self.tree.column("type", width=150)
        self.tree.column("on", width=50, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._load_form())

        buttons = ttk.Frame(frame)
        buttons.pack(fill=tk.X, pady=6)
        self.new_type = tk.StringVar(value=sorted(ELEMENTS)[0])
        ttk.Combobox(buttons, textvariable=self.new_type, values=sorted(ELEMENTS),
                     state="readonly", width=12).pack(side=tk.LEFT)
        ttk.Button(buttons, text="Ajouter", command=self._add_element).pack(side=tk.LEFT, padx=4)
        ttk.Button(buttons, text="Supprimer", command=self._remove_element).pack(side=tk.LEFT)
        ttk.Button(buttons, text="▲", width=3,
                   command=lambda: self._move_z(-1)).pack(side=tk.RIGHT)
        ttk.Button(buttons, text="▼", width=3,
                   command=lambda: self._move_z(1)).pack(side=tk.RIGHT, padx=4)

        form = ttk.LabelFrame(frame, text="Sélection", padding=8)
        form.pack(fill=tk.X)
        form.columnconfigure(1, weight=1)

        self.form_title = ttk.Label(form, text="", foreground="#444")
        self.form_title.grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))

        self.f_enabled = tk.BooleanVar(value=True)
        self.f_anchor = tk.StringVar(value="top-left")
        self.f_dx = tk.StringVar(value="0")
        self.f_dy = tk.StringVar(value="0")
        self.f_scale = tk.StringVar(value="1.0")

        check = ttk.Checkbutton(form, text="Activé", variable=self.f_enabled,
                                command=self._apply_form)
        check.grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 6))

        ttk.Label(form, text="Ancre").grid(row=2, column=0, sticky="w")
        combo = ttk.Combobox(form, textvariable=self.f_anchor, values=list(ANCHORS),
                             state="readonly", width=14)
        combo.grid(row=2, column=1, sticky="w")
        self.f_anchor.trace_add("write", lambda *_: self._apply_form())

        entries = {}
        for row, (label, key, var) in enumerate(
            [("Décalage X", "dx", self.f_dx), ("Décalage Y", "dy", self.f_dy),
             ("Échelle", "scale", self.f_scale)], start=3):
            ttk.Label(form, text=label).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(form, textvariable=var, width=14)
            entry.grid(row=row, column=1, sticky="w")
            entry.bind("<Return>", lambda _e: self._apply_form())
            entry.bind("<FocusOut>", lambda _e: self._apply_form())
            entries[key] = entry
        self.entry_dx, self.entry_dy = entries["dx"], entries["dy"]

        ttk.Label(form, text="Options (JSON)").grid(row=6, column=0, sticky="nw", pady=(6, 0))
        self.f_options = tk.Text(form, height=4, width=26)
        self.f_options.grid(row=6, column=1, sticky="we", pady=(6, 0))
        self.f_options.bind("<FocusOut>", lambda _e: self._apply_form())

        self.form_widgets = [check, combo, self.f_options, *entries.values()]

        self._reload_tree()
        return frame

    def _build_weather_tab(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=8)
        weather_cfg = self.cfg["weather"]

        self.w_enabled = tk.BooleanVar(value=weather_cfg["enabled"])
        ttk.Checkbutton(frame, text="Activer la météo", variable=self.w_enabled,
                        command=self._apply_weather).pack(anchor="w", pady=(0, 8))

        # --- Recherche de lieu --------------------------------------------
        place = ttk.LabelFrame(frame, text="Lieu", padding=8)
        place.pack(fill=tk.X, pady=(0, 10))

        search = ttk.Frame(place)
        search.pack(fill=tk.X)
        self.geo_query = tk.StringVar()
        entry = ttk.Entry(search, textvariable=self.geo_query)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        entry.bind("<Return>", lambda _e: self._search_location())
        self.geo_button = ttk.Button(search, text="Chercher", command=self._search_location)
        self.geo_button.pack(side=tk.LEFT, padx=(6, 0))

        self._geo_results: list[dict] = []
        self.geo_choice = tk.StringVar()
        self.geo_combo = ttk.Combobox(place, textvariable=self.geo_choice,
                                      state="disabled", values=[])
        self.geo_combo.pack(fill=tk.X, pady=(6, 0))
        self.geo_combo.bind("<<ComboboxSelected>>", self._pick_location)

        self.geo_status = ttk.Label(
            place, foreground="#666", wraplength=340, justify="left",
            text=weather_cfg.get("location_name") or "Lieu défini par coordonnées.")
        self.geo_status.pack(anchor="w", pady=(6, 0))

        # --- Champs bruts --------------------------------------------------
        self.w_vars: dict[str, tk.StringVar] = {}
        fields = [
            ("lat", "Latitude"),
            ("lon", "Longitude"),
            ("refresh_minutes", "Rafraîchir après (min)"),
            ("max_stale_minutes", "Cache acceptable jusqu'à (min)"),
            ("timeout_seconds", "Timeout (s)"),
        ]
        for key, label in fields:
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=2)
            ttk.Label(row, text=label, width=28).pack(side=tk.LEFT)
            var = tk.StringVar(value=str(weather_cfg[key]))
            self.w_vars[key] = var
            field = ttk.Entry(row, textvariable=var)
            field.pack(side=tk.LEFT, fill=tk.X, expand=True)
            field.bind("<FocusOut>", lambda _e: self._apply_weather())


        return frame

    # ------------------------------------------------------------------ #
    # Recherche de lieu
    # ------------------------------------------------------------------ #

    def _search_location(self) -> None:
        """Lance la recherche dans un thread : un appel réseau dans le thread
        Tk gèlerait la fenêtre le temps de la réponse."""
        self.geo_button.config(state="disabled")
        self.geo_status.config(text="Recherche…", foreground="#666")
        threading.Thread(
            target=self._search_worker,
            args=(self.geo_query.get(), self.w_vars["api_key"].get()),
            daemon=True,
        ).start()

    def _search_worker(self, query: str, api_key: str) -> None:
        try:
            results, error = weather_mod.geocode(query, api_key), None
        except Exception as exc:
            results, error = [], exc
        # Tkinter n'est pas thread-safe : on repasse par la boucle d'événements.
        self.after(0, self._search_done, results, error)

    def _search_done(self, results: list[dict], error: Exception | None) -> None:
        self.geo_button.config(state="normal")

        if error is not None:
            self.geo_status.config(text=str(error), foreground="#b00020")
            return
        if not results:
            self.geo_status.config(text="Aucun lieu trouvé.", foreground="#b00020")
            self.geo_combo.config(values=[], state="disabled")
            return

        self._geo_results = results
        labels = [r["label"] for r in results]
        self.geo_combo.config(values=labels, state="readonly")
        self.geo_status.config(
            text=f"{len(results)} résultat(s) - choisis dans la liste.", foreground="#666")
        if len(results) == 1:
            self.geo_choice.set(labels[0])
            self._pick_location()

    def _pick_location(self, _event=None) -> None:
        chosen = next((r for r in self._geo_results if r["label"] == self.geo_choice.get()), None)
        if chosen is None:
            return
        self.w_vars["lat"].set(f"{chosen['lat']:.4f}")
        self.w_vars["lon"].set(f"{chosen['lon']:.4f}")
        self.cfg["weather"]["location_name"] = chosen["label"]
        self.geo_status.config(text=chosen["label"], foreground="#0a7a30")
        self._apply_weather()

    def _build_general_tab(self, parent) -> ttk.Frame:
        frame = ttk.Frame(parent, padding=8)

        hours = ttk.LabelFrame(frame, text="Jour / nuit", padding=8)
        hours.pack(fill=tk.X)
        self.g_day = tk.StringVar(value=str(self.cfg["background"]["day_start_hour"]))
        self.g_night = tk.StringVar(value=str(self.cfg["background"]["night_start_hour"]))
        for row, (label, var) in enumerate([("Début du jour (h)", self.g_day),
                                            ("Début de la nuit (h)", self.g_night)]):
            ttk.Label(hours, text=label, width=22).grid(row=row, column=0, sticky="w", pady=2)
            entry = ttk.Entry(hours, textvariable=var, width=6)
            entry.grid(row=row, column=1, sticky="w")
            entry.bind("<FocusOut>", lambda _e: self._apply_general())

        for title, key, is_dir in [("Dossier des assets", "assets_dir", True),
                                   ("Image générée", "output_path", False)]:
            box = ttk.LabelFrame(frame, text=title, padding=8)
            box.pack(fill=tk.X, pady=(8, 0))
            var = tk.StringVar(value=self.cfg.get(key, ""))
            setattr(self, f"g_{key}", var)
            entry = ttk.Entry(box, textvariable=var)
            entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
            entry.bind("<FocusOut>", lambda _e: self._apply_general())
            ttk.Button(box, text="...", width=3,
                       command=lambda k=key, d=is_dir: self._browse(k, d)).pack(side=tk.LEFT, padx=4)

        ttk.Label(frame, text="Laisser vide = valeur par défaut.",
                  foreground="#666").pack(anchor="w", pady=(6, 0))
        return frame

    # ------------------------------------------------------------------ #
    # Liste d'éléments
    # ------------------------------------------------------------------ #

    def _reload_tree(self, select: list[str] | str | None = None) -> None:
        if select is None:
            keep = self._selected_ids()
        elif isinstance(select, str):
            keep = [select]
        else:
            keep = list(select)

        self.tree.delete(*self.tree.get_children())
        for element in sorted(self.cfg["elements"], key=lambda e: e["z"]):
            self.tree.insert("", "end", iid=element["id"],
                             values=(element["type"], "oui" if element["enabled"] else "non"))

        keep = [i for i in keep if self.tree.exists(i)]
        if not keep and self.cfg["elements"]:
            keep = [self.cfg["elements"][0]["id"]]
        if keep:
            self.tree.selection_set(keep)
        self._load_form()

    def _selected_ids(self) -> list[str]:
        return list(self.tree.selection())

    def _selected_id(self) -> str | None:
        selection = self._selected_ids()
        return selection[0] if selection else None

    def _selected_elements(self) -> list[dict]:
        chosen = set(self._selected_ids())
        return [e for e in self.cfg["elements"] if e["id"] in chosen]

    def _selected(self) -> dict | None:
        elements = self._selected_elements()
        return elements[0] if len(elements) == 1 else None

    def _load_form(self) -> None:
        elements = self._selected_elements()
        self._loading = True

        if not elements:
            self.form_title.config(text="Aucune sélection")
            self._set_form_state("disabled")
            self._loading = False
            self._highlight_selection()
            return

        multiple = len(elements) > 1
        self.form_title.config(
            text=f"{len(elements)} éléments sélectionnés" if multiple
            else f"Élément « {elements[0]['id']} » ({elements[0]['type']})")
        self._set_form_state("normal")

        self.f_enabled.set(all(e["enabled"] for e in elements))

        anchors = {e["anchor"] for e in elements}
        self.f_anchor.set(anchors.pop() if len(anchors) == 1 else "")

        if multiple:
            # dx/dy n'ont pas de valeur commune : on les neutralise plutôt que
            # d'afficher celle du premier, qui inviterait à écraser les autres.
            self.f_dx.set(""); self.f_dy.set("")
            self.entry_dx.config(state="disabled"); self.entry_dy.config(state="disabled")
            scales = {e["scale"] for e in elements}
            self.f_scale.set(str(scales.pop()) if len(scales) == 1 else "")
            self.f_options.delete("1.0", tk.END)
            self.f_options.config(state="disabled")
        else:
            element = elements[0]
            self.entry_dx.config(state="normal"); self.entry_dy.config(state="normal")
            self.f_dx.set(str(element["dx"]))
            self.f_dy.set(str(element["dy"]))
            self.f_scale.set(str(element["scale"]))
            self.f_options.config(state="normal")
            self.f_options.delete("1.0", tk.END)
            self.f_options.insert("1.0", json.dumps(element["options"], ensure_ascii=False))

        self._loading = False
        self._highlight_selection()

    def _set_form_state(self, state: str) -> None:
        for widget in self.form_widgets:
            widget.config(state=state)

    def _apply_form(self) -> None:
        """Applique le formulaire à TOUTE la sélection.

        Un champ laissé vide n'est pas appliqué : c'est ce qui permet de
        changer l'ancre de cinq éléments sans écraser leurs échelles.
        """
        if self._loading:
            return
        elements = self._selected_elements()
        if not elements:
            return
        multiple = len(elements) > 1

        for element in elements:
            element["enabled"] = self.f_enabled.get()
            if self.f_anchor.get():
                element["anchor"] = self.f_anchor.get()

        raw_scale = self.f_scale.get().strip()
        if raw_scale:
            try:
                scale = float(raw_scale)
                if scale > 0:
                    for element in elements:
                        element["scale"] = scale
            except ValueError:
                pass

        if not multiple:
            element = elements[0]
            # dx/dy acceptent un entier ou une expression ("month.w + date.w").
            for key, var in (("dx", self.f_dx), ("dy", self.f_dy)):
                raw = var.get().strip()
                try:
                    element[key] = int(raw)
                except ValueError:
                    element[key] = raw or 0
            try:
                options = json.loads(self.f_options.get("1.0", tk.END).strip() or "{}")
                if isinstance(options, dict):
                    element["options"] = options
            except json.JSONDecodeError:
                pass  # saisie en cours, on ne casse rien

        self._touch()
        self._reload_tree()
        self.schedule_refresh()

    def _add_element(self) -> None:
        element_type = self.new_type.get()
        existing = {e["id"] for e in self.cfg["elements"]}
        index = 1
        while f"{element_type}-{index}" in existing:
            index += 1
        new = dict(config_mod.ELEMENT_DEFAULTS)
        new.update({
            "id": f"{element_type}-{index}",
            "type": element_type,
            "options": {},
            "z": max((e["z"] for e in self.cfg["elements"]), default=-1) + 1,
        })
        self.cfg["elements"].append(new)
        self._touch()
        self._reload_tree(new["id"])
        self.schedule_refresh()

    def _remove_element(self) -> None:
        element = self._selected()
        if element is None:
            return
        self.cfg["elements"].remove(element)
        self._touch()
        self._reload_tree()
        self.schedule_refresh()

    def _move_z(self, direction: int) -> None:
        ordered = sorted(self.cfg["elements"], key=lambda e: e["z"])
        element = self._selected()
        if element is None:
            return
        index = ordered.index(element)
        target = index + direction
        if not 0 <= target < len(ordered):
            return
        ordered[index], ordered[target] = ordered[target], ordered[index]
        for z, item in enumerate(ordered):
            item["z"] = z
        self._touch()
        self._reload_tree(element["id"])
        self.schedule_refresh()

    # ------------------------------------------------------------------ #
    # Onglets météo / général
    # ------------------------------------------------------------------ #

    def _apply_weather(self) -> None:
        weather_cfg = self.cfg["weather"]
        weather_cfg["enabled"] = self.w_enabled.get()
        casts = {"api_key": str, "lat": float, "lon": float,
                 "refresh_minutes": int, "max_stale_minutes": int, "timeout_seconds": int}
        for key, cast in casts.items():
            try:
                weather_cfg[key] = "b03e11fb78b499fc7bd029dc4a90a701"
            except ValueError:
                self.w_vars[key].set(str(weather_cfg[key]))
        self._touch()
        self.schedule_refresh()

    def _apply_general(self) -> None:
        background = self.cfg["background"]
        for key, var in (("day_start_hour", self.g_day), ("night_start_hour", self.g_night)):
            try:
                background[key] = max(0, min(23, int(var.get())))
            except ValueError:
                pass
            var.set(str(background[key]))
        self.cfg["assets_dir"] = self.g_assets_dir.get().strip()
        self.cfg["output_path"] = self.g_output_path.get().strip()
        self._touch()
        self.schedule_refresh()

    def _browse(self, key: str, is_dir: bool) -> None:
        chosen = (filedialog.askdirectory() if is_dir
                  else filedialog.asksaveasfilename(defaultextension=".png"))
        if chosen:
            getattr(self, f"g_{key}").set(chosen)
            self._apply_general()

    # ------------------------------------------------------------------ #
    # Aperçu
    # ------------------------------------------------------------------ #

    def schedule_refresh(self, delay_ms: int = 180) -> None:
        """Anti-rebond : évite de recomposer à chaque frappe."""
        if self._refresh_job is not None:
            self.after_cancel(self._refresh_job)
        self._refresh_job = self.after(delay_ms, self.refresh_preview)

    def refresh_preview(self) -> None:
        self._refresh_job = None
        self.canvas.delete("all")
        self._photo_refs.clear()
        self._items.clear()

        try:
            background, layers = renderer.render_layers(config_mod.normalize(self.cfg),
                                                        datetime.now())
        except Exception as exc:
            log.exception("Aperçu impossible")
            self.canvas.create_text(20, 20, anchor="nw", fill="#ff8080",
                                    text=f"Aperçu impossible :\n{exc}")
            return

        self._bg_size = background.size
        scale = min(PREVIEW_MAX[0] / background.width,
                    PREVIEW_MAX[1] / background.height, 1.0)
        self._preview_scale = scale

        size = (max(1, round(background.width * scale)), max(1, round(background.height * scale)))
        photo = ImageTk.PhotoImage(background.resize(size, renderer.RESAMPLE))
        self._photo_refs.append(photo)
        self.canvas.config(width=size[0], height=size[1])
        self.canvas.create_image(0, 0, anchor="nw", image=photo)

        for layer in layers:
            layer_size = (max(1, round(layer.image.width * scale)),
                          max(1, round(layer.image.height * scale)))
            layer_photo = ImageTk.PhotoImage(layer.image.resize(layer_size, renderer.RESAMPLE))
            self._photo_refs.append(layer_photo)
            item = self.canvas.create_image(
                round(layer.position[0] * scale), round(layer.position[1] * scale),
                anchor="nw", image=layer_photo,
            )
            self._items[item] = {"id": layer.element["id"], "size": layer.image.size}

        self._highlight_selection()

    def _highlight_selection(self) -> None:
        self.canvas.delete("selection")
        chosen = set(self._selected_ids())
        for item, info in self._items.items():
            if info["id"] not in chosen:
                continue
            x1, y1, x2, y2 = self.canvas.bbox(item)
            self.canvas.create_rectangle(x1 - 1, y1 - 1, x2 + 1, y2 + 1,
                                         outline="#4da3ff", dash=(3, 2), tags="selection")

    # ------------------------------------------------------------------ #
    # Sélection et déplacement
    # ------------------------------------------------------------------ #

    def _item_at(self, x: int, y: int) -> int | None:
        """Élément le plus haut sous le curseur, ou None sur le fond."""
        for item in reversed(self.canvas.find_overlapping(x, y, x, y)):
            if item in self._items:
                return item
        return None

    def _on_press(self, event) -> None:
        self.canvas.focus_set()
        additive = bool(event.state & 0x0005)  # Maj (0x1) ou Ctrl (0x4)
        item = self._item_at(event.x, event.y)

        if item is None:
            # Clic sur le fond : on démarre un cadre de sélection. Sans
            # modificateur, il remplace la sélection courante.
            if not additive:
                self.tree.selection_set([])
            self._rubber = {"x": event.x, "y": event.y,
                            "base": self._selected_ids() if additive else [],
                            "rect": self.canvas.create_rectangle(
                                event.x, event.y, event.x, event.y,
                                outline="#4da3ff", dash=(2, 2), tags="rubber")}
            return

        element_id = self._items[item]["id"]
        selection = self._selected_ids()
        if additive:
            selection = ([i for i in selection if i != element_id]
                         if element_id in selection else selection + [element_id])
            self.tree.selection_set(selection)
        elif element_id not in selection:
            # Saisir un élément hors sélection le sélectionne seul ; en saisir
            # un déjà sélectionné conserve le groupe, sinon on ne pourrait
            # jamais déplacer plusieurs éléments d'un coup.
            self.tree.selection_set([element_id])

        self._drag = {"x": event.x, "y": event.y, "dx": 0, "dy": 0,
                      "items": [i for i, info in self._items.items()
                                if info["id"] in self._selected_ids()]}

    def _on_motion(self, event) -> None:
        if self._rubber is not None:
            self.canvas.coords(self._rubber["rect"], self._rubber["x"], self._rubber["y"],
                               event.x, event.y)
            return
        if self._drag is None:
            return
        step_x, step_y = event.x - self._drag["x"], event.y - self._drag["y"]
        for item in self._drag["items"]:
            self.canvas.move(item, step_x, step_y)
        self._drag.update(x=event.x, y=event.y,
                          dx=self._drag["dx"] + step_x, dy=self._drag["dy"] + step_y)
        self._highlight_selection()

    def _on_release(self, _event) -> None:
        if self._rubber is not None:
            x1, y1, x2, y2 = self.canvas.coords(self._rubber["rect"])
            self.canvas.delete(self._rubber["rect"])
            touched = [self._items[i]["id"]
                       for i in self.canvas.find_overlapping(min(x1, x2), min(y1, y2),
                                                             max(x1, x2), max(y1, y2))
                       if i in self._items]
            self.tree.selection_set(list(dict.fromkeys(self._rubber["base"] + touched)))
            self._rubber = None
            return

        if self._drag is None:
            return
        drag, self._drag = self._drag, None
        if drag["dx"] == 0 and drag["dy"] == 0:
            return

        # Le décalage écran est converti à l'échelle du fond, puis appliqué en
        # relatif : les expressions sont décalées, pas remplacées.
        self._shift_selection(round(drag["dx"] / self._preview_scale),
                              round(drag["dy"] / self._preview_scale))

    def _shift_selection(self, dx: int, dy: int) -> None:
        elements = self._selected_elements()
        if not elements or (dx == 0 and dy == 0):
            return
        for element in elements:
            element["dx"] = renderer.shift_offset(element["dx"], dx)
            element["dy"] = renderer.shift_offset(element["dy"], dy)
        self._touch()
        self._load_form()
        self.schedule_refresh(60)

    def _on_arrow(self, event) -> None:
        step = 10 if event.state & 0x0001 else 1
        deltas = {"Left": (-step, 0), "Right": (step, 0),
                  "Up": (0, -step), "Down": (0, step)}
        if event.keysym in deltas:
            self._shift_selection(*deltas[event.keysym])
            return "break"

    # ------------------------------------------------------------------ #
    # Sauvegarde
    # ------------------------------------------------------------------ #

    def _touch(self) -> None:
        self.dirty = True
        self.title("Persona Wallpaper - configuration *")

    def save(self) -> bool:
        try:
            config_mod.save(config_mod.normalize(self.cfg))
        except Exception as exc:
            messagebox.showerror("Enregistrement impossible", str(exc))
            return False
        self.dirty = False
        self.title("Persona Wallpaper - configuration")
        return True

    def save_and_apply(self) -> None:
        if not self.save():
            return
        try:
            from . import wallpaper
            path = renderer.render_to_file(config_mod.normalize(self.cfg))
            wallpaper.set_wallpaper(path)
        except Exception as exc:
            log.exception("Application impossible")
            messagebox.showerror("Application impossible", str(exc))
            return
        messagebox.showinfo("Fait", "Fond d'écran régénéré et appliqué.")

    def _on_close(self) -> None:
        if self.dirty:
            answer = messagebox.askyesnocancel("Quitter", "Enregistrer les modifications ?")
            if answer is None:
                return
            if answer and not self.save():
                return
        self.destroy()


def run(cfg: dict) -> int:
    App(cfg).mainloop()
    return 0
