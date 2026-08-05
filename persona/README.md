# Persona Wallpaper

Génère un fond d'écran style Persona en composant plusieurs images (fond
jour/nuit, mois, date, jour de la semaine, météo) et l'applique sous Windows.

## Deux modes, un seul exécutable

```
main.exe            génère et applique le fond d'écran  (tâche planifiée)
main.exe --config   ouvre l'interface de configuration
main.exe --dry-run  génère l'image sans l'appliquer     (debug)
main.exe --verbose  logs DEBUG
```

## Emplacement des fichiers

| Quoi | Où |
|---|---|
| Config | `%APPDATA%\persona-wallpaper\config.json` |
| Log (rotatif) | `%LOCALAPPDATA%\persona-wallpaper\persona.log` |
| Cache météo | `%LOCALAPPDATA%\persona-wallpaper\weather-cache.json` |
| Image générée | `%LOCALAPPDATA%\persona-wallpaper\wallpaper.png` |
| Assets | `assets\` à côté de l'exe, soit `dist\assets\` (modifiable dans la config) |

## Assets attendus

```
assets/
  background/day.png          background/night.png
  date/0.png … date/9.png
  months/jan.png … months/dec.png
  days/day/mon.png … sun.png   days/night/mon.png … sun.png
  meteo/sun.png  cloud.png  rain.png  snow.png
```

Les noms sont figés dans `persona/elements.py` (`MONTHS`, `WEEKDAYS`,
`weather.CONDITIONS`). Ils ne dépendent pas de la locale du système.

## Développement

```bash
pip install -r requirements.txt
python main.py --config
python main.py --dry-run --verbose
```

## Lieu de la météo

Onglet **Météo** de la GUI : tape un nom de ville, clique sur *Chercher*, choisis
dans la liste (les homonymes sont fréquents - Nice en France et Nice dans
l'Illinois). Les champs latitude/longitude sont remplis pour toi et restent
éditables si tu préfères des coordonnées exactes.

La recherche passe par l'API Geocoding d'OpenWeather, incluse dans le plan
gratuit et utilisant la même clé. Elle tourne dans un thread : un appel réseau
dans le thread Tk gèlerait la fenêtre.

`weather.location_name` est purement informatif - seuls `lat` et `lon` sont
utilisés au rendu.

## Positions

`dx` / `dy` acceptent un entier **ou** une expression, parce que la mise en page
d'origine était relative aux largeurs réelles des PNG (elles varient : les mois
font de 76 à 104 px, les chiffres de 62 à 72, les jours de 156 à 198).

Variables disponibles : `bg.w` / `bg.h`, `self.w` / `self.h`, et `<id>.w` /
`<id>.h` pour tout élément dont l'identifiant est un nom Python valide.
Fonctions : `round`, `min`, `max`, `abs`, `int`.

```json
{ "id": "weather", "dx": "month.w + date.w", "dy": 30 }
```

Les valeurs par défaut reproduisent le script d'origine au pixel près
(vérifié sur une année complète × 2 tranches horaires × 4 météos).

Déplacer un élément à la souris **décale** son expression au lieu de la
remplacer : `"30 + month.w - 20"` déplacé de 47 px devient
`"30 + month.w + 27"`. La mise en page relative survit donc au déplacement, et
un `+ N` en fin de chaîne est absorbé plutôt qu'empilé.

## Sélection multiple

| Geste | Effet |
|---|---|
| Clic sur un élément | le sélectionne seul |
| Ctrl+clic / Maj+clic | ajoute ou retire de la sélection |
| Cadre tracé sur le fond | sélectionne tout ce qu'il touche (Ctrl pour cumuler) |
| Glisser un élément sélectionné | déplace toute la sélection |
| Flèches | 1 px - avec Maj, 10 px |
| Ctrl+clic dans la liste | même chose, côté arbre |

Le formulaire s'adapte : *Activé*, *Ancre* et *Échelle* s'appliquent à toute la
sélection, tandis que *Décalage X/Y* et les options sont désactivés en mode
multiple - il n'y a pas de valeur commune à afficher, et en montrer une
inviterait à écraser les autres.

Un champ laissé vide n'est pas appliqué : c'est ce qui permet de changer l'ancre
de cinq éléments sans toucher à leurs échelles.

## Build

```bat
pip install pyinstaller
build.bat
```

Produit **`dist\main.exe`** et copie `assets\` dans `dist\assets\` : c'est le
chemin qu'attend une tâche planifiée existante pointant sur `main.exe`.

Le build est en `--onefile --windowed`. Contrepartie du `--onefile` :
l'exécutable se décompresse dans `%TEMP%` à chaque lancement, ce qui ajoute une
à deux secondes. Sans importance pour une tâche horaire ; si ça te gêne un jour,
`--onedir` supprime ce coût mais produit `dist\main\main.exe`, donc il faudrait
repointer la tâche.

Les assets ne sont volontairement pas embarqués dans l'exe : ils restent
remplaçables sans rebuild.

## Tâche planifiée

- Action : `C:\...\dist\main.exe`
- Démarrer dans : `C:\...\dist\` (obligatoire : c'est là que sont cherchés les assets)
- Déclencheur : toutes les heures, indéfiniment
- Cocher « Exécuter la tâche dès que possible après un démarrage planifié
  manqué » (PC éteint ou en veille à l'heure pile)
- Ne PAS cocher « Exécuter même si l'utilisateur n'est pas connecté » :
  `SPI_SETDESKWALLPAPER` agit sur la session interactive courante

La colonne « Résultat de la dernière exécution » affiche le code de retour :
`0x0` = succès, `0x1` = échec, détails dans `persona.log`.

## Ajouter un type d'élément

Dans `persona/elements.py` :

```python
@element("hour")
def render_hour(ctx, element_cfg):
    return ctx.open("hours", f"{ctx.now.hour:02d}.png")
```

Il apparaît automatiquement dans la liste déroulante « Ajouter » de la GUI.
Ni `renderer.py` ni `gui.py` n'ont besoin d'être modifiés.
