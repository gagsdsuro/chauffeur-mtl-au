import json
import re
from collections import defaultdict

def parse_route_text(texte):
    """
    Parse le texte de route avec plusieurs lignes, directions et parcours
    Retourne un dictionnaire organisé par ligne et direction
    """
    
    # Structure pour organiser les données
    routes_data = defaultdict(lambda: defaultdict(lambda: {
        "ligne": None,
        "direction": None,
        "routes": []
    }))
    
    lignes = texte.strip().split('\n')
    
    current_line = None
    current_direction = None
    current_route_data = None
    
    i = 0
    while i < len(lignes):
        ligne = lignes[i].strip()
        
        # Vérifier si c'est une en-tête de ligne/direction
        match_header = re.match(r'(.+?)\s*/\s*(\d+)\s+(Est|Ouest|Nord|Sud)', ligne)
        
        if match_header:
            # Nouvelle ligne/direction détectée
            current_line = match_header.group(2)
            current_direction = match_header.group(3).lower()
            
            # Créer la structure pour cette ligne/direction
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
            current_route_data = routes_data[current_line][current_direction]["routes"][0]
            
            # Traiter les lignes jusqu'à la prochaine en-tête ou fin du fichier
            i += 1
            while i < len(lignes):
                next_ligne = lignes[i].strip()
                
                # Vérifier si on a une nouvelle en-tête
                if re.match(r'(.+?)\s*/\s*(\d+)\s+(Est|Ouest|Nord|Sud)', next_ligne):
                    break
                
                # Vérifier si c'est un début de parcours
                if "Parcours" in next_ligne and "ID" in next_ligne:
                    # Extraire le nom du parcours (avant "ID")
                    # match_name = re.match(r'(Parcours\s+\w+)', next_ligne)
                    # APRÈS (capture tous les mots avant "ID")
                    match_name = re.match(r'(Parcours\s+\w+(?:\s+\w+)*)\s*ID', next_ligne)

                    match_id = re.search(r'ID\s*(\d+)', next_ligne)
                    
                    parcours_name = match_name.group(1) if match_name else "Parcours"
                    parcours_id = int(match_id.group(1)) if match_id else 1
                    
                    # Collecter les lignes du parcours
                    parcours_lines = [next_ligne]
                    i += 1
                    
                    # Continuer jusqu'au prochain parcours ou nouvelle ligne/direction
                    while i < len(lignes):
                        parcours_ligne = lignes[i].strip()
                        
                        # Arrêter si on trouve une nouvelle ligne/direction
                        if re.match(r'(.+?)\s*/\s*(\d+)\s+(Est|Ouest|Nord|Sud)', parcours_ligne):
                            break
                        
                        # Arrêter si on trouve un nouveau parcours
                        if "Parcours" in parcours_ligne and "ID" in parcours_ligne and parcours_ligne != next_ligne:
                            break
                        
                        parcours_lines.append(parcours_ligne)
                        i += 1
                    
                    # Parser le parcours
                    start_station = None
                    start_code = None
                    end_station = None
                    end_code = None
                    
                    for pline in parcours_lines:
                        match = re.search(r'(.+?)\s+(\d{5})$', pline)
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
                    
                    for pline in parcours_lines:
                        pline_clean = pline.strip()
                        
                        if not pline_clean or any(pattern in pline for pattern in skip_patterns):
                            continue
                        
                        if re.search(r'\d{5}$', pline_clean):
                            continue
                        
                        if any(prefix in pline_clean for prefix in ['Via -', 'Gauche -', 'Droite -']):
                            directions.append(pline_clean)
                    
                    # Ajouter le parcours
                    parcours_dict = {
                        "id": parcours_id,
                        "name": parcours_name,
                        "start": start_station,
                        "start_code": start_code,
                        "end": end_station,
                        "end_code": end_code,
                        "direction": directions
                    }
                    
                    current_route_data["parcours"].append(parcours_dict)
                    continue
                
                i += 1
        else:
            i += 1
    
    return routes_data


# Utilisation
# Lire depuis un fichier texte
with open('route.txt', 'r', encoding='utf-8') as f:
    texte = f.read()

# Convertir
routes_data = parse_route_text(texte)

# Créer un fichier JSON pour chaque ligne/direction
fichiers_crees = []

for ligne in sorted(routes_data.keys()):
    for direction in sorted(routes_data[ligne].keys()):
        # Créer le nom du fichier avec "_" au lieu de "-"
        filename = f"gd{ligne}_{direction}.json"
        
        # Récupérer les données pour cette ligne/direction
        data = routes_data[ligne][direction]
        
        # Sauvegarder le fichier JSON
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        fichiers_crees.append(filename)
        print(f"✓ Fichier créé : {filename}")
        print(f"  - Parcours trouvés : {len(data['routes'][0]['parcours'])}")

print(f"\n✓ Total : {len(fichiers_crees)} fichier(s) créé(s) avec succès!")
