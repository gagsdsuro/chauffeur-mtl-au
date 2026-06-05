# Documentation — Répertoire Gauche-Droite

## Vue d'ensemble

Ce répertoire contient les **itinéraires complets** (Gauche-Droite) des lignes STM. Chaque fichier représente une ligne et une direction spécifique et trajets associés.

Les données "Gauche-Droite" (G-D) sont utilisées pour:
- Planifier les trajets exacts
- Générer les rapports journaliers des chauffeurs
- Détecter les variations de trajet (parcours principal vs secondaire)

## Convention de nommage des fichiers

Format: `{numero_ligne}_{direction}.json`

**Exemples:**
- `22_est.json` — Ligne 22, direction Est
- `24_ouest.json` — Ligne 24, direction Ouest
- `131_sud.json` — Ligne 131, direction Sud
- `136_nord.json` — Ligne 136, direction Nord
- `85e_est.json` — Ligne 85E, direction Est (note le 'e' minuscule)

**Directions acceptées:** est, ouest, nord, sud (minuscules)

## Structure JSON

### Racine du fichier

```json
{
  "ligne": "string",           // Numéro de la ligne (ex: "22")
  "direction": "string",       // Direction (est, ouest, nord, sud)
  "routes": [...]              // Tableau des itinéraires
}
```

### Structure d'une route

```json
{
  "line_number": "string",     // Numéro de ligne (ex: "22")
  "direction": "string",       // Direction (Est, Ouest, Nord, Sud - Capitalisée)
  "parcours": [...]            // Tableau des trajets pour cette direction
}
```

### Structure d'un parcours

```json
{
  "id": "number",                       // Identifiant unique du parcours (ex: 1, 2, 3)
  "name": "string",                     // Nom du parcours (ex: "Parcours principal", "Parcours secondaire")
  "start": "string",                    // Nom complet du point de départ (ex: "Station Assomption (de l'Assomption / Chauveau)")
  "start_code": "number",               // Code STM de l'arrêt de départ (ex: 54306)
  "end": "string",                      // Nom complet du point d'arrivée
  "end_code": "number",                 // Code STM de l'arrêt d'arrivée
  "direction": [                        // Tableau des directions du parcours (Gauche/Droite/Via)
    "Gauche/Droite/Via - Nom",
    ...
  ]
}
```

### Format des directions

Chaque élément du tableau `direction` suit le format:

```
[Direction] - [Nom de la rue]
```

**Directions:**

Ces termes décrivent la **direction du virage ou du trajet** dans le parcours, comme si on lisait des directions d'un GPS:

- `Gauche` — Tourner à gauche sur cette rue
- `Droite` — Tourner à droite sur cette rue
- `Via` — Continuer tout droit via cette rue (pas de virage)

**Clarifications et cas complexes:**

Dans certains cas, le nom de la rue peut inclure des clarifications supplémentaires entre la direction et le nom:

- `Via - vers aut. 40 Ouest` → "Continuer via vers l'autoroute 40 Ouest"
- `Gauche - vers Crémazie dir. Est` → "Tourner à gauche vers Crémazie direction Est"
- `Via - vers Crémazie dir. E` → "Continuer via vers Crémazie direction Est"

Ces clarifications aident le chauffeur à identifier le trajet exact en cas d'intersections complexes ou d'autoroutes.

**Exemples concrets:**
- `Via - Rue Principale` → "Continuer tout droit via Rue Principale"
- `Gauche - Sherbrooke` → "Tourner à gauche sur Sherbrooke"
- `Droite - Notre-Dame` → "Tourner à droite sur Notre-Dame"
- `Via - Terminus Villa-Maria` → "Continuer via Terminus Villa-Maria"
- `Via - vers aut. 40 Ouest` → "Continuer vers l'autoroute 40 Ouest"
- `Gauche - vers Crémazie dir. Est` → "Tourner à gauche vers Crémazie direction Est"

**Exemple de séquence:**
```json
"direction": [
  "Via - De l'Assomption",          // Continuer sur De l'Assomption
  "Droite - Chauveau",               // Tourner à droite sur Chauveau
  "Droite - Dickson",                // Tourner à droite sur Dickson
  "Gauche - Notre-Dame",             // Tourner à gauche sur Notre-Dame
  "Gauche - des Futailles"           // Tourner à gauche sur des Futailles
]
```

Cela décrit le parcours exact du bus: "Continuer sur Assomption, puis tourner à droite sur Chauveau, puis à droite sur Dickson, puis à gauche sur Notre-Dame, puis à gauche sur des Futailles".

## Spécifications des champs

### ligne
- **Type:** Chaîne numérique
- **Obligatoire:** Oui
- **Format:** 1-3 chiffres, optionnellement suivi d'une lettre (ex: "22", "85e", "358")
- **Exemple:** "22"

### direction (à la racine)
- **Type:** Chaîne minuscule
- **Obligatoire:** Oui
- **Valeurs acceptées:** est, ouest, nord, sud
- **Exemple:** "est"

### line_number
- **Type:** Chaîne
- **Obligatoire:** Oui
- **Format:** Doit correspondre à `ligne`
- **Exemple:** "22"

### direction (dans routes)
- **Type:** Chaîne capitalisée
- **Obligatoire:** Oui
- **Valeurs acceptées:** Est, Ouest, Nord, Sud
- **Exemple:** "Est"

### id (parcours)
- **Type:** Nombre entier
- **Obligatoire:** Oui
- **Plage:** 1-99 (généralement 1-5 par ligne)
- **Règle:** IDs uniques par direction (ne pas répéter d'une direction à l'autre)
- **Exemple:** 1, 2, 3

### name
- **Type:** Chaîne
- **Obligatoire:** Oui
- **Valeurs courantes:**
  - "Parcours principal" — Le trajet principal/le plus fréquent
  - "Parcours secondaire" — Trajet alternatif ou moins fréquent
  - "Parcours weekend" — Trajet spécifique aux fins de semaine
  - Descriptions spécifiques (ex: "Via Station Centrale")

### start / end
- **Type:** Chaîne (nom complet du lieu)
- **Obligatoire:** Oui
- **Format:** "Lieu (Intersection)" quand applicable
- **Exemples:**
  - "Station Assomption (de l'Assomption / Chauveau)"
  - "Montgomery / Sherbrooke"
  - "Terminus Villa-Maria"

### start_code / end_code
- **Type:** Nombre entier
- **Obligatoire:** Oui
- **Format:** Code STM à 5 chiffres
- **Exemple:** 54306, 52819

### direction
- **Type:** Tableau de chaînes
- **Obligatoire:** Oui (au minimum 1 direction)
- **Format:** "[Direction] - [Nom]" (Gauche, Droite, ou Via)
- **Règles:**
  - L'ordre reflète la séquence du parcours (comme un GPS)
- **Exemples:**
  ```json
  [
    "Via - de l'Assomption",
    "Droite - Chauveau",
    "Droite - Dickson",
    "Gauche - Notre-Dame",
    "Gauche - des Futailles"
  ]
  ```

## Titres de parcours courants

| Titre | Description |
|-------|-------------|
| Parcours principal | Itinéraire standard, le plus fréquent |
| Parcours secondaire | Variation alternative, moins fréquente |
| Parcours weekend | Spécifique aux samedis/dimanches |
| Parcours scolaire | Modification pour horaires scolaires |
| Parcours été/hiver | Variation saisonnière |

## Règles de normalisation

### Structure des fichiers

✅ **À faire:**
- Utiliser des noms de fichiers cohérents: `{numero}_{direction}.json`
- Maintenir un seul fichier par direction (pas de "22_est_ouest.json")
- Inclure toutes les directions disponibles (Est ET Ouest si applicables)
- Garder `ligne` et `line_number` synchronisés

❌ **À éviter:**
- Fichiers combinant 2 directions (ex: "22_est_ouest.json")
- Incohérence entre `ligne` et `line_number`
- Capitalization mélangée (est vs Est vs EST)
- Espaces ou caractères spéciaux dans les noms de fichiers

### Données

✅ **À faire:**
- Utiliser le format "Lieu (Intersection)" pour clarté
- Inclure "Via" pour les trajets intermédiaires
- Maintenir l'ordre chronologique des étapes du parcours
- Utiliser les codes STM officiels

❌ **À éviter:**
- Codes STM manquants ou incorrects
- Étapes du parcours sans direction (Gauche/Droite/Via)
- Noms d'étapes ambigus ou incomplets
- Parcours avec moins de 1 étape de parcours

## Exemple complet

**Fichier:** `22_est.json`

```json
{
  "ligne": "22",
  "direction": "est",
  "routes": [
    {
      "line_number": "22",
      "direction": "Est",
      "parcours": [
        {
          "id": 2,
          "name": "Parcours principal",
          "start": "Station Assomption (de l'Assomption / Chauveau)",
          "start_code": 54306,
          "end": "Georges-V / Notre-Dame",
          "end_code": 54428,
          "direction": [
            "Via - de l'Assomption",
            "Droite - Chauveau",
            "Droite - Dickson",
            "Gauche - Notre-Dame",
            "Gauche - des Futailles",
            "Via - vers Tellier dir. E",
            "Via - Tellier",
            "Droite - De Boucherville",
            "Gauche - Notre-Dame",
            "Gauche - Georges-V"
          ]
        }
      ]
    }
  ]
}
```

**Interprétation du parcours:**

Le tableau `stops` décrit le trajet exact du bus, comme des directions GPS:

1. `Via - de l'Assomption` → Continuer tout droit via De l'Assomption
2. `Droite - Chauveau` → Tourner à droite sur Chauveau
3. `Droite - Dickson` → Tourner à droite sur Dickson
4. `Gauche - Notre-Dame` → Tourner à gauche sur Notre-Dame
5. `Gauche - des Futailles` → Tourner à gauche sur des Futailles
6. Continuer...

**Lecture complète:** "Commencer à la Station Assomption, continuer via De l'Assomption, tourner à droite sur Chauveau, tourner à droite sur Dickson, tourner à gauche sur Notre-Dame, tourner à gauche sur des Futailles, continuer via vers Tellier dir. E, continuer via Tellier, tourner à droite sur De Boucherville, tourner à gauche sur Notre-Dame, tourner à gauche sur Georges-V, et terminer à Georges-V / Notre-Dame."

## Conversion des fichiers existants

Si vous avez des fichiers au format ancien (combinant 2 directions):

**Avant:**
```
22_est_ouest.json (contient Est ET Ouest)
```

**Après:**
```
22_est.json  (contient uniquement Est)
22_ouest.json (contient uniquement Ouest)
```

**Processus:**
1. Lire le fichier combiné
2. Extraire les données pour "Est"
3. Créer `22_est.json` avec ces données
4. Extraire les données pour "Ouest"
5. Créer `22_ouest.json` avec ces données

## Outils recommandés

- **Validation JSON:** Linter JSON ou validateur en ligne
- **Formatage:** Indentation de 2 espaces
- **Édition:** Éditeur avec support JSON (VS Code, etc.)

## Questions fréquentes

**Q: Que faire si une ligne n'a qu'une seule direction?**  
A: Créer un seul fichier avec cette direction (ex: `777_nord_sud.json` → `777_nord.json` + `777_sud.json`)

**Q: Comment gérer les lignes combinées (ex: "85/85e")?**  
A: Créer des fichiers séparés: `85_est.json` et `85e_est.json` (lignes distinctes)

**Q: Quelle est la différence entre "Via" et "Gauche/Droite"?**  
A: Tous les trois décrivent la direction du parcours comme une liste d'instructions:
- "Via - Rue" = Continuer tout droit via cette rue (pas de virage)
- "Gauche - Rue" = Tourner à gauche sur cette rue
- "Droite - Rue" = Tourner à droite sur cette rue

La différence est que "Via" est généralement un trajet intermédiaire, tandis que "Gauche/Droite" représentent les virages.

**Q: Puis-je modifier l'ID d'un parcours?**  
A: Les IDs doivent être stables (ne pas changer sans raison). Ils servent de clés de référence.

## Mise à jour des fichiers

Lors de la modification d'itinéraires:

1. **Localisez le fichier** correspondant à la ligne et direction
2. **Vérifiez les parcours existants** pour éviter les doublons
3. **Ajoutez ou modifiez** le parcours approprié
4. **Mettez à jour les étapes du parcours** dans l'ordre correct
5. **Validez le JSON** pour la syntaxe
6. **Documentez les changements** (date, raison)

---

## Historique de normalisation

- **2026-05-16:** Normalisation des fichiers G-D avec convention uniforme {ligne}_{direction}.json
- **Avant:** Fichiers combinant 2 directions (22_est_ouest.json)

---

*Dernière mise à jour: 2026-05-16*
