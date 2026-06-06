import json
import re
from collections import defaultdict

def parse_route_text(texte):
    """
    Parse le texte de route avec plusieurs lignes, directions et parcours
    Retourne un dictionnaire organisé par ligne et direction
    """
    lignes = texte.strip().split('\n\n')  # Séparer par paragraphes vides
    
    # Structure pour organiser les données
    routes_data = defaultdict(lambda: defaultdict(lambda: {
        "ligne": None,
        "direction": None,
        "routes": []
    }))
    
    current_line = None
    current_direction = None
    
    for bloc in lignes:
        if not bloc.strip():
            continue
        
        bloc_lines = bloc.strip().split('\n')
        
        # Vérifier si c'est une en-tête de ligne
        first_line = bloc_lines[0]
        match_header = re.match(r'(.+?)\s*/\s*(\d+)\s+(Est|Ouest|Nord|Sud)', first_line)
        
        if match_header:
            # C'est une nouvelle ligne/direction
            current_line = match_header.group(2)      # Le numéro (195)
            current_direction = match_header.group(3).lower()  # La direction (est, ouest, etc.)
            
            # Initialiser la structure pour cette ligne/direction
            routes_data[current_line][current_direction] = {
                "ligne": current_line,
                "direction": current_direction,
                "routes": [
                    {
                        "line_number": current_line,
                        "direction": current_direction,
                        "parcours": []
                    }
                ]
            }
            
            # Traiter les parcours dans ce bloc
            parcours_indices = []
            for i, ligne in enumerate(bloc_lines):
                if "Parcours" in ligne and "ID" in ligne:
                    parcours_indices.append(i)
            
            # Parser chaque parcours
            for idx, parcours_start in enumerate(parcours_indices):
                # Déterminer où ce parcours se termine
                if idx + 1 < len(parcours_indices):
                    parcours_end = parcours_indices[idx + 1]
                else:
                    parcours_end = len(bloc_lines)
                
                parcours_lines = bloc_lines[parcours_start:parcours_end]
                
                # Extraction du nom et de l'ID
                header_line = parcours_lines[0]
                match_name = re.match(r'(Parcours\s+\w+)', header_line)
                match_id = re.search(r'ID\s*(\d+)', header_line)
                
                parcours_name = match_name.group(1) if match_name else "Parcours"
                parcours_id = int(match_id.group(1)) if match_id else idx + 1
                
                # Extraction des stations de départ et arrivée
                start_station = None
                start_code = None
                end_station = None
                end_code = None
                
                for ligne in parcours_lines:
                    match = re.search(r'(.+?)\s+(\d{5})$', ligne.strip())
                    if match:
                        station_name = match.group(1).strip()
                        station_code = int(match.group(2))
                        
                        if start_station is None:
                            start_station = station_name
                            start_code = station_code
                        else:
                            end_station = station_name
                            end_code = station_code
                
                # Extraction des directions
                directions = []
                skip_patterns = ['Imprimer', 'Parcours', 'Date de mise à jour', 'ID']
                
                for ligne in parcours_lines:
                    ligne_clean = ligne.strip()
                    # Ignorer les lignes vides et les lignes à sauter
                    if not ligne_clean or any(pattern in ligne for pattern in skip_patterns):
                        continue
                    # Ignorer les lignes avec des codes (5 chiffres)
                    if re.search(r'\d{5}$', ligne_clean):
                        continue
                    # Ajouter les directions
                    if any(prefix in ligne_clean for prefix in ['Via -', 'Gauche -', 'Droite -']):
                        directions.append(ligne_clean)
                
                # Ajouter ce parcours
                parcours_dict = {
                    "id": parcours_id,
                    "name": parcours_name,
                    "start": start_station,
                    "start_code": start_code,
                    "end": end_station,
                    "end_code": end_code,
                    "direction": directions
                }
                
                routes_data[current_line][current_direction]["routes"][0]["parcours"].append(parcours_dict)
    
    return routes_data


# Utilisation
# Lire depuis un fichier texte
with open('route.txt', 'r', encoding='utf-8') as f:
    texte = f.read()

# Convertir
routes_data = parse_route_text(texte)

# Créer un fichier JSON pour chaque ligne/direction
fichiers_crees = []

for ligne in routes_data:
    for direction in routes_data[ligne]:
        # Créer le nom du fichier
        filename = f"gd{ligne}-{direction}.json"
        
        # Récupérer les données pour cette ligne/direction
        data = routes_data[ligne][direction]
        
        # Sauvegarder le fichier JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        fichiers_crees.append(filename)
        print(f"✓ Fichier créé : {filename}")

print(f"\n✓ Total : {len(fichiers_crees)} fichier(s) créé(s) avec succès!")
