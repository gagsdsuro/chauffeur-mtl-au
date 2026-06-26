# Projet chauffeur-stm — Volet « détours »

État au 2026-06-25. Objectif : récupérer automatiquement les détours d'une ligne/sens
depuis le portail employé STM, (éventuellement à la demande à partir de chauffeur-stm), sans scraper le DOM rendu.

---

## 1. Acquis (fonctionnel et testé)

### Endpoint API identifié
```
GET https://employe.stm.info/resume-journee/panel/detour/{ligne}/{sens}
```
- Paramétrable par ligne (`10`) et sens (`S`, etc.).
- Rejouable hors navigateur (confirmé via `curl` en terminal).
- Réponse : **JSON enveloppant un fragment HTML** → `{"countDeviations": N, "html": "<fragment>"}`.

### Authentification (couple à durée de vie limitée)
| Élément | Rôle | Indice |
|---|---|---|
| Cookie `TS01846...` | jeton de session | préfixe `TS` → F5 BIG-IP (WAF) |
| Header `X-CSRF-Token` | anti-CSRF, lié à la session | 40 car., signature type Laravel |

Cookie + CSRF forment une **paire** : si l'un expire, l'autre devient inutile.

### Headers — tri effectué
- **À garder** : `X-Requested-With: XMLHttpRequest`, `Referer`, `User-Agent`.
- **Jetables** : `X-NewRelic-ID`, `sec-ch-ua*`, `Sec-Fetch-*`, `Connection`, `Accept-Language`.

### Parser — `parse_event.py`
- **Zéro dépendance** (lib standard : `json`, `re`, `html.parser`). Pas de `bs4`.
- Entrée : réponse brute (fichier ou stdin). Sortie : dict structuré.
- Mini-arbre DOM maison (`find` / `find_all` avec flag `direct=` pour le 1er niveau).
- Testé OK sur échantillon réel (ligne 10 Sud, 1 événement).

Modèle de sortie :
```
ligne, sens, count_deviations
evenements[] : numero, type, motif, date_debut, date_fin (null si « non définie »),
               effectif, arrets[{code, nom}], description_gd[], commentaire
```

Chaînage prévu :
```bash
curl '.../detour/10/S' -H '...' | python3 parse_event.py
```

---

## 2. Reste à faire

### Volet session — patron hybride Playwright + appel API (prochaine étape)
Cible : rendre l'appel autonome pour une tâche planifiée ou pour un appel à partir de chauffeur-stm, sans recapture manuelle.

1. **Playwright** fait le login une fois et persiste la session (`storageState`).
2. Récupérer le **CSRF token** depuis la page (à localiser : `<meta name="csrf-token">` ou cookie `XSRF-TOKEN`).
3. Lancer les appels via `context.request.get(...)` → réutilise automatiquement les cookies de session.
4. Passer la sortie à `parse_event.py`.

Avantage : login automatisé + appels API stables, sans scraper le DOM.

### Questions ouvertes à trancher
- **2FA au login ?** Détermine si Playwright peut tout automatiser ou s'il faut une session semi-manuelle.
- **Emplacement exact du CSRF token** dans la page (meta vs cookie).
- **Nom complet de la clé de cookie** (`TS01846` + suffixe ?).
- **Durée de vie réelle de la session** → fréquence de re-login.
- **Format `ligne/sens`** : le regex du titre suppose `Détour / 10 Sud`. Valider sur lignes école (`10E`) / sens Est-Ouest, ou passer `ligne`/`sens` en arguments puisqu'ils sont connus à l'appel.

---

## 3. Fichiers
- `parse_event.py` — parser détours, sans dépendance, fonctionnel.
