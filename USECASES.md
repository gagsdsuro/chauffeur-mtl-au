# Cas d'utilisation — chauffeur-stm

Ce document décrit les interactions des utilisateurs avec le système, indépendamment de l'interface. Il sert de référence pour l'ergonomie et l'évolution des fonctionnalités.

---

## Rôles

| Rôle | Description |
|------|-------------|
| **Chauffeur** | Chauffeur d'autobus STM. Prépare et consulte les données de sa journée de travail. |
| **Chauffeur-admin** | Chauffeur assurant l'entretien courant des données du système. |

---

## Chauffeur — Préparation de la journée (la veille)

**Contexte :** La veille de la journée de travail, généralement en soirée. La carte agent et la journée sont disponibles vers 17h.

1. S'assure que les données hebdomadaires (GTFS) sont à jour.
2. Charge la carte agent du lendemain, effectue les annotations et imprime la version annotée en PDF.
3. Charge le fichier journée du lendemain.
4. Vérifie que les Gauche-Droite des lignes de la journée sont disponibles et récents (moins de 90 jours).
5. Extrait une première version des événements pour les lignes du jour.
6. Au besoin, génère et analyse le Rapport V2 (routes, événements, détours).
7. Au besoin, génère le Rapport quotidien (PDF recto-verso prêt à imprimer).
8. Vérifie que la carte agent annotée, le Rapport quotidien et le Rapport V2 sont disponibles pour consultation le lendemain.

---

## Chauffeur — Préparation avant le départ

**Contexte :** Quelques heures avant de prendre la route, à domicile ou au garage.

**Pré-requis :** La connexion au portail employé doit être active (session valide).

1. Rafraîchit les données des événements pour les lignes de la journée.
2. Au besoin, génère et analyse une nouvelle version du Rapport V2.
3. Au besoin, génère une nouvelle version du Rapport quotidien en PDF et l'imprime.

---

## Chauffeur — En route

**Contexte :** Aux terminus, en pause ou en interligne. Interaction principalement sur téléphone, limitée au tableau de bord.

1. Au besoin, rafraîchit les données des événements pour les lignes restantes.
2. Au besoin, génère et consulte une nouvelle version du Rapport V2.
3. Au besoin, consulte plus en détail un Gauche-Droite ou les événements d'une ligne et direction spécifique.
4. Au besoin, géolocalise le prochain bus à récupérer.

---

## Chauffeur-admin — Entretien des données

**Contexte :** Périodiquement, pour maintenir le système en bon état.

1. Révise les fichiers Gauche-Droite et supprime les fichiers obsolètes (plus d'un an).
2. Révise les fichiers Événements et supprime les fichiers obsolètes (plus de 3 mois).
3. Révise les fichiers Rapport et supprime les fichiers obsolètes (plus de 3 mois).
4. Révise les fichiers Journée et supprime les fichiers obsolètes (plus d'un an).
5. Révise les fichiers Carte agent et supprime les fichiers obsolètes (plus d'un an).
6. Au besoin, consulte les journaux d'activité.
