# Documentation — Répertoire Évènements

## Vue d'ensemble
Ce répertoire contient les données des événements affectant les arrêts des lignes STM. Chaque fichier JSON représente une ligne et une direction spécifique.

## Convention de nommage des fichiers
Format: `{numero_ligne}_{direction}.json`

**Exemples:**
- `24_est.json` — Ligne 24, direction Est
- `24_ouest.json` — Ligne 24, direction Ouest
- `131_nord.json` — Ligne 131, direction Nord
- `150_est.json` — Ligne 150, direction Est

**Directions acceptées:** est, ouest, nord, sud

## Structure JSON

### Racine du fichier
```json
{
  "ligne": "string",           // Numéro de la ligne (ex: "24")
  "direction": "string",       // Direction (est, ouest, nord, sud)
  "events": [...]              // Tableau des événements
}
```

### Structure d'un événement
```json
{
  "evenement_id": "string",              // ID unique de l'événement (ex: "10075400")
  "titre": "string",                     // Type d'événement (ex: "Annulation d'arrêts")
  "motif": "string",                     // Raison (ex: "Travaux", "Situation Incontrôlable")
  "date_heure_debut": "ISO 8601|null",   // Date/heure début (ex: "2026-01-06T12:00:00")
  "date_heure_fin": "ISO 8601|null",     // Date/heure fin ou null si indéfinie
  "effectif": "string",                  // Période d'application (ex: "En tout temps", "Seulement entre 12:00 et 19:00 chaque jour")
  "arrets": [                            // Tableau des arrêts affectés
    {
      "id": "string",                    // Code d'arrêt (ex: "52653")
      "nom": "string"                    // Nom de l'arrêt (ex: "Sherbrooke / Plessis")
    }
  ],
  "commentaire": "string|undefined"      // Commentaire optionnel
}
```

## Spécifications des champs

### evenement_id
- **Type:** Chaîne numérique unique
- **Obligatoire:** Oui
- **Format:** Entre 6 et 10 chiffres
- **Exemple:** "10075400"

### titre
- **Type:** Chaîne
- **Obligatoire:** Oui
- **Valeurs courantes:**
  - "Annulation d'arrêts"
  - "Arrêt déplacé"
  - "Modification de trajet"
  - "Changement d'horaire"

### motif
- **Type:** Chaîne
- **Obligatoire:** Oui
- **Valeurs courantes:**
  - "Travaux" — Travaux de construction/infrastructure
  - "Situation Incontrôlable" — Événements imprévisibles
  - "Événement spécial" — Manifestations, fermetures
  - "Maintenance" — Entretien du service

### date_heure_debut
- **Type:** ISO 8601 ou null
- **Obligatoire:** Oui
- **Format:** "YYYY-MM-DDTHH:MM:SS" (ex: "2026-01-06T12:00:00")
- **Fuseau horaire:** Heure locale de Montréal (pas de Z)

### date_heure_fin
- **Type:** ISO 8601 ou null
- **Obligatoire:** Oui (mais peut être null)
- **Format:** ISO 8601 ou `null` si la fin est indéfinie
- **Exemple:** `"2026-12-31T19:00:00"` ou `null`

### effectif
- **Type:** Chaîne descriptive
- **Obligatoire:** Oui
- **Exemples:**
  - "En tout temps" — Toute la journée, tous les jours
  - "Seulement entre 12:00 et 19:00 chaque jour" — Horaires restreints
  - "Lundi au vendredi" — Jours de semaine uniquement
  - "Fins de semaine seulement" — Samedi/dimanche

### arrets_annules
- **Type:** Tableau d'objets
- **Obligatoire:** Oui (tableau vide `[]` si aucun arrêt annulé)
- **Structure:** Chaque arrêt contient `id` (chaîne) et `nom` (chaîne)
- **Exemple:**
  ```json
  [
    {"id": "52653", "nom": "Sherbrooke / Plessis"},
    {"id": "54019", "nom": "Sherbrooke / De Champlain (Hôpital Notre-Dame)"}
  ]
  ```

### arrets_ajoutes
- **Type:** Tableau de chaînes
- **Obligatoire:** Oui (tableau vide `[]` si aucun arrêt ajouté)
- **Usage:** Arrêts temporaires créés en remplacement d'arrêts annulés (pas d'ID officiel STM)
- **Exemple:**
  ```json
  ["Temp. - Brown Owl / Elm", "56472 - Notre-Dame / Saint-Pierre"]
  ```

### commentaire
- **Type:** Chaîne
- **Obligatoire:** Non (peut être omis ou null)
- **Usage:** Notes supplémentaires, détails spécifiques
- **Exemples:**
  - "LUNDI AU VENDREDI 12H00 À 19H00"
  - "BIXI"
  - "*** ARRÊT TEMPORAIRE DÉCARIE / SHERBROOKE ***"

## Titres d'événements courants

| Titre | Description |
|-------|-------------|
| Annulation d'arrêts | L'arrêt n'est pas desservi pendant la période |
| Arrêt déplacé | L'arrêt est temporairement relocalisé |
| Modification de trajet | La route est modifiée |
| Changement d'horaire | Les horaires sont affectés |
| Fermeture temporaire | Service suspendu |

## Règles de validation

✅ **À faire:**
- Utiliser le format ISO 8601 pour les dates/heures
- Inclure les arrêts annulés dans `arrets_annules`, les arrêts ajoutés dans `arrets_ajoutes`
- S'assurer que `date_heure_debut` ≤ `date_heure_fin` (si fin définie)
- Fournir des descriptions claires et cohérentes
- Maintenir les événements triés par `date_heure_debut` (du plus récent au plus ancien)

❌ **À éviter:**
- Espaces ou caractères spéciaux dans les noms de fichiers (sauf `_`)
- Dates/heures incohérentes ou mal formatées
- IDs d'événement dupliqués
- Arrêts manquants ou vides

## Exemple complet

**Fichier:** `24_est.json`
```json
{
  "ligne": "24",
  "direction": "est",
  "events": [
    {
      "evenement_id": "10075400",
      "titre": "Annulation d'arrêts",
      "motif": "Situation Incontrôlable",
      "date_heure_debut": "2026-01-06T12:00:00",
      "date_heure_fin": "2026-12-31T19:00:00",
      "effectif": "Seulement entre 12:00 et 19:00 chaque jour",
      "arrets": [
        {
          "id": "52653",
          "nom": "Sherbrooke / Plessis"
        },
        {
          "id": "54019",
          "nom": "Sherbrooke / De Champlain (Hôpital Notre-Dame)"
        }
      ],
      "commentaire": "LUNDI AU VENDREDI 12H00 À 19H00"
    }
  ]
}
```

## Mise à jour des fichiers

Lors de l'ajout ou de la modification d'événements:

1. **Localisez le fichier** correspondant à la ligne et la direction
2. **Vérifiez les IDs d'événement** pour éviter les doublons
3. **Formatez correctement** les dates en ISO 8601
4. **Maintenez la cohérence** des structures
5. **Testez le JSON** pour s'assurer qu'il est valide
6. **Triez les événements** pour faciliter la lecture (optionnel mais recommandé)

## Outils recommandés

- **Validation JSON:** Utiliser un linter JSON ou un validateur en ligne
- **Formatage:** Indentation de 2 espaces pour la lisibilité
- **Édition:** Éditeur de texte avec support JSON (VS Code, etc.)

## Questions fréquentes

**Q: Que faire si un événement s'applique à plusieurs arrêts?**  
A: Ajouter tous les arrêts au tableau `arrets` du même événement.

**Q: Comment représenter une fin indéfinie?**  
A: Utiliser `null` pour `date_heure_fin`.

**Q: Et si je dois créer un nouveau fichier pour une ligne?**  
A: Créer un fichier `{numero}_{direction}.json` avec la structure racine (`ligne`, `direction`, `events`).

**Q: Dois-je supprimer les anciens événements?**  
A: Garder l'historique tant que c'est pertinent. Supprimer seulement si nécessaire pour des raisons de performance.

---

*Dernière mise à jour: 2026-05-16*
