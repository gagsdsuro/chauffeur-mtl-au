# Politique de sécurité

## Signaler une vulnérabilité

N'ouvrez **pas** de ticket public. Utilisez le signalement privé de GitHub
(onglet *Security* → *Report a vulnerability*) en décrivant le problème et les étapes pour le
reproduire. N'y joignez aucune donnée réelle (journées, cartes agent, cookies, matricules).

## Déploiement sûr

- L'application n'est **pas** conçue pour être exposée directement sur Internet. `docker-compose.yml`
  lie le port 8501 à `127.0.0.1` : placez un **reverse-proxy HTTPS** devant pour tout autre accès.
- Activez `CHAUFFEUR_MODE_STRICT=1` : sans compte ni mode strict, l'authentification par PIN est facultative.
- Les cookies de session du portail employé, `data/users.json` et les clés API sont sensibles :
  permissions `0600`, jamais versionnés (le dossier `data/` et `Installation/config/secrets*.json`
  sont ignorés par git).
- Utilisez votre propre clé API GTFS temps réel ; ne la partagez pas.
- Ne publiez jamais le contenu de `data/` (données personnelles et information interne).
