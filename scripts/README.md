# parse_gd.py exemple

``` bash
python3 parse_gd.py < ~/chauffeur-mtl-au/data/raw/new-gd.txt

============================================================
RAPPORT: Importer Gauche-Droite
============================================================

[OK] Fichier mis a jour: gd195_est.json
   Ligne: 195
   Direction: est
   Total parcours: 1

[OK] Aucun changement detecte

[LOCALISATION] ~/chauffeur-mtl-au/scripts
============================================================


============================================================
RAPPORT: Importer Gauche-Droite
============================================================

[OK] Fichier mis a jour: gd195_ouest.json
   Ligne: 195
   Direction: ouest
   Total parcours: 2

[CHANGEMENTS] (1):
   - Parcours 22 (Parcours secondaire): +NOUVEAU (Station Angrignon -> École Dorval-Jean-XXIII (Dawson / No 1301), 37 directions)

[LOCALISATION] ~/chauffeur-mtl-au/scripts
============================================================
```

# carte_agent.py exemple

```bash
python3 carte_agent.py --pdf ../data/ca/carte-agent-2026-06-04.pdf --out ../data/ca/toto2.pdf --gtfs ../data/gtfs/gtfs_stm/ --date 2026-06-04
[INFO] Date retenue : 2026-06-04
[INFO] Lignes détectées : ['496', '198', '211']
[INFO] GTFS : ../data/gtfs/gtfs_stm
[INFO] Services actifs pour 2026-06-04 (thursday) : 9
[INFO] Chargement stops.txt...
[INFO] Chargement trips.txt...
[INFO] Trips pertinents : 371
[INFO] Scan stop_times.txt (premier arrêt de chaque trip)...
[INFO] Premiers arrêts trouvés : 371 trips
[INFO]   Ligne 496: 73 dir0 (Terminus Dorval) | 72 dir1 (Station Lionel-Groulx / Saint-)
[INFO]   Ligne 198: 47 dir0 (Terminus Dorval) | 44 dir1 (Station Angrignon (des Trinita)
[INFO]   Ligne 211: 62 dir0 (Station Kirkland) | 73 dir1 (Station Lionel-Groulx)
[INFO]   Ligne 496: 5 segment(s)
[INFO]     dep=16:41 -> Prec=16:32 (premier segment uniquement)
[INFO]   Ligne 198: 1 segment(s)
[INFO]     dep=19:01 -> Prec=18:31 (premier segment uniquement)
[INFO]   Ligne 211: 2 segment(s)
[INFO]     dep=22:05 -> Prec=21:36 (premier segment uniquement)
[INFO] OK — PDF annoté : ../data/ca/toto2.pdf

Carte 528 — 16:39 -> 25:46
Lignes : 496, 198, 211
Sortie : ../data/ca/toto2.pdf
```

# rapport_gd.py exemple 

```bash
python3 rapport_gd.py --ligne 195 --direction ouest --date 2026-06-05 --base ~/chauffeur-mtl-au
→ Ligne 195 ouest — 2026-06-05
  Base projet : ~/chauffeur-mtl-au
  58 arrêts GTFS, 33 instructions G-D, 4 événements actifs
  ✅ Rapport écrit: ~/chauffeur-mtl-au/scripts/rapport_195_ouest_2026-06-05.html
```
