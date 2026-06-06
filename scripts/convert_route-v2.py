import json
import re

def parse_route_text(texte):
    """
    Parse le texte de route avec plusieurs parcours et retourne un dictionnaire JSON
    """
    lignes = texte.strip().split('\n')
    
    # Extraction de l'en-tête (ligne et direction)
    first_line = lignes[0]  # "Gauche-Droite / 195 Ouest"
    
    # Parse la première ligne
    match = re.match(r'(.+?)\s*/\s*(\d+)\s+(Est|Ouest|Nord|Sud)', first_line)
    if match:
        type_route = match.group(1).strip()
        line_number = match.group(2)          # "195"
        direction = match.group(3).lower()    # "ouest"
    else:
        line_number = "XXX"
        direction = "est"
    
    # Trouver tous les parcours
    parcours_list = []
    parcours_indices = []
    
    for i, ligne in enumerate(lignes):
        if "Parcours" in ligne and "ID" in ligne:
            parcours_indices.append(i)
    
    # Parser chaque parcours
    for idx, parcours_start in enumerate(parcours_indices):
        # Déterminer où ce parcours se termine
        if idx + 1 < len(parcours_indices):
            parcours_end = parcours_indices[idx + 1]
        else:
            parcours_end = len(lignes)
        
        parcours_lines = lignes[parcours_start:parcours_end]
        
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
            match = re.search(r'(\w+(?:\s+\w+|-)*(?:\s+\w+)*)\s+(\d{5})', ligne)
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
            if re.search(r'\d{5}', ligne_clean):
                continue
            # Ajouter les directions
            if any(prefix in ligne_clean for prefix in ['Via -', 'Gauche -', 'Droite -']):
                directions.append(ligne_clean)
        
        # Ajouter ce parcours à la liste
        parcours_dict = {
            "id": parcours_id,
            "name": parcours_name,
            "start": start_station,
            "start_code": start_code,
            "end": end_station,
            "end_code": end_code,
            "direction": directions
        }
        parcours_list.append(parcours_dict)
    
    # Construction du JSON final
    result = {
        "ligne": line_number,
        "direction": direction,
        "routes": [
            {
                "line_number": line_number,
                "direction": direction,
                "parcours": parcours_list
            }
        ]
    }
    
    return result

# Utilisation
# Lire depuis un fichier texte
with open('route.txt', 'r', encoding='utf-8') as f:
    texte = f.read()

# Convertir
result = parse_route_text(texte)

# Afficher dans le terminal
print(json.dumps(result, ensure_ascii=False, indent=2))

# Sauvegarder en JSON
with open('route.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

print("\n✓ Fichier 'route.json' créé avec succès!")
