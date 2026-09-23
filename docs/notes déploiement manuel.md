1. Sur l’ordinateur où la recette a été exécutée
Attribuer le nom de livraison et exporter l’image :

```bash
docker tag chauffeur-stm:candidate-20260923-csv chauffeur-stm:livraison-2026-09-23

docker save -o /tmp/chauffeur-stm-2026-09-23.tar \
  chauffeur-stm:livraison-2026-09-23
```
2. Transférer le fichier

Par SSH, par exemple, en adaptant l’utilisateur et l’adresse :

```bash
scp /tmp/chauffeur-stm-2026-09-23.tar utilisateur@serveur-prod:/tmp/
```
3. Sur l’ordinateur de production
Importer l’image :

```bash
docker load -i /tmp/chauffeur-stm-2026-09-23.tar
```
Cette commande n’arrête pas l’application actuelle. On peut donc transférer et importer l’image à l’avance.
Ensuite, depuis le dossier du projet de production :

1. Conserver une référence à l’ancienne image pour le retour arrière.
2. Arrêter l’application et sauvegarder les données et la configuration.
3. Remplacer la section build: de Compose par : 
    
`    image: chauffeur-stm:livraison-2026-09-23
`

4. Conserver les volumes et paramètres propres à la production.
5. Démarrer :

```bash
docker compose up -d --no-build
```
Le code applicatif étant inclus dans l’image, un git pull n’est pas nécessaire pour faire tourner cette livraison. La configuration Compose doit toutefois être mise à jour.
