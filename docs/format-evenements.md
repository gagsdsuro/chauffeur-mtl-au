# Format des fichiers d'évènements

Les fichiers `data/Events/<ligne>_<direction>.json` contiennent les évènements
d'une ligne et d'une direction. La direction est en minuscule parmi `est`,
`ouest`, `nord` et `sud`.

Un fichier prêt à copier et adapter est disponible dans
[`docs/gabarits/evenements.json`](gabarits/evenements.json).

## Structure

```json
{
  "ligne": "10",
  "direction": "nord",
  "detours": [
    {
      "evenement_id": "11205733",
      "titre": "Détour avec annulation d'arrêt",
      "motif": "Travaux",
      "date_heure_debut": "2026-08-06T06:50:00",
      "date_heure_fin": null,
      "effectif": "En tout temps",
      "arrets_annules": [
        {"id": "53051", "nom": "Station Papineau"}
      ],
      "commentaire": null,
      "arrets_ajoutes": [
        {"id": "53047", "nom": "Station temporaire"}
      ],
      "description_gd": "VIA CARTIER\nG/ DE MAISONNEUVE\nVIA RR"
    }
  ]
}
```

## Règles

- `evenement_id`, `titre`, `motif` et `effectif` sont des chaînes obligatoires.
- Les dates utilisent le format ISO 8601 local de Montréal. Une fin inconnue ou
  indéterminée est représentée par `null`.
- `arrets_annules` contient les arrêts touchés sous la forme `{id, nom}`. Selon
  le titre, un arrêt peut être déplacé ou faire l'objet d'une information sans
  être réellement supprimé.
- `arrets_ajoutes` est normalement une liste d'objets `{id, nom}`. Les lecteurs
  acceptent aussi les anciennes chaînes libres et les identifiants vides pour
  les arrêts temporaires sans code officiel.
- `description_gd` est une chaîne optionnelle. Depuis la normalisation de
  l'affichage, chaque instruction source est séparée par `\n`. Les anciennes
  chaînes aplaties restent acceptées et sont découpées au mieux à la lecture.
- `commentaire` est une chaîne optionnelle ou `null`.
- Un même `evenement_id` peut apparaître plusieurs fois lorsqu'il possède des
  plages horaires ou des impacts distincts. Les comparaisons se font donc par
  groupe d'ID et conservent toutes les variantes.

Les importeurs sont la source de vérité pour la normalisation. Ils remplacent
la liste `detours` par la réponse courante du portail; les événements retirés
sont consignés dans le compte rendu et le journal.
