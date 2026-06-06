import json
import re

def parse_route_text(texte):
    """
    Parse le texte de route et retourne un dictionnaire JSON
    """
    lignes = texte.strip().split('\n')
    
    # Extraction de l'en-tête (ligne et direction)
    first_line = lignes[0]  # "Gauche-Droite / 195 Est"
    
    # Parse la première ligne
    match = re.match(r'(.+?)\s*/\s*(\d+)\s+(Est|Ouest|Nord|Sud)', first_line)
    if match:
        type_route = match.group(1).strip()  # "Gauche-Droite"
        line_number = match.group(2)          # "195"
        direction = match.group(3).lower()    # "est"
    else:
        line_number = "XXX"
        direction = "est"
    
    # Extraction du nom du parcours et de l'ID
    parcours_name = "Parcours principal"
    parcours_id = 1
    for ligne in lignes:
        if "Parcours" in ligne:
            match_id = re.search(r'ID\s*(\d+)', ligne)
            if match_id:
                parcours_id = int(match_id.group(1))
            parcours_name = ligne.split('ID')[0].strip()
            break
    
    # Extraction des stations de départ et arrivée
    start_station = None
    start_code = None
    end_station = None
    end_code = None
    
    for i, ligne in enumerate(lignes):
        # Cherche les codes (5 chiffres)
        match = re.search(r'(\w+(?:\s+\w+)*)\s+(\d{5})', ligne)
        if match:
            station_name = match.group(1).strip()
            station_code = int(match.group(2))
            
            # Le premier est le départ, le dernier est l'arrivée
            if start_station is None:
                start_station = station_name
                start_code = station_code
            else:
                end_station = station_name
                end_code = station_code
    
    # Extraction des directions
    directions = []
    skip_patterns = ['Imprimer', 'Parcours', 'Date de mise à jour', 'ID']
    
    for ligne in lignes:
        ligne_clean = ligne.strip()
        # Ignorer les lignes vides et les lignes à sauter
        if not ligne_clean or any(pattern in ligne for pattern in skip_patterns):
            continue
        # Ignorer les lignes avec des codes (5 chiffres)
        if re.search(r'\d{5}', ligne_clean):
            continue
        # Ajouter les directions (Via -, Gauche -, Droite -)
        if any(prefix in ligne_clean for prefix in ['Via -', 'Gauche -', 'Droite -']):
            directions.append(ligne_clean)
    
    # Construction du JSON
    result = {
        "ligne": line_number,
        "direction": direction,
        "routes": [
            {
                "line_number": line_number,
                "direction": direction,
                "parcours": [
                    {
                        "id": parcours_id,
                        "name": parcours_name,
                        "start": start_station,
                        "start_code": start_code,
                        "end": end_station,
                        "end_code": end_code,
                        "direction": directions
                    }
                ]
            }
        ]
    }
    
    return result

# Utilisation
texte_exemple = """Gauche-Droite / 195 Est
Imprimer
Parcours principalID 4
Date de mise à jour: 2026-06-06 01:00:19

Terminus Dorval 57365
Via - Terminus Dorval
Droite - Montréal-Toronto
Via - vers Fénélon
Via - Fénelon
Droite - Dumont
Droite - Herron
Via - rond point Dorval
Via - vers aut. 20 Est
Via - Montréal-Toronto
Via - Bouchard
Via - Victoria
Gauche - 55e Avenue
Droite - Sherbrooke
Droite - 40e Avenue
Gauche - Provost
Droite - 32e Avenue
Droite - Remembrance
Via - Victoria
Gauche - 34e Avenue
Gauche - Notre-Dame
Droite - 6e Avenue
Gauche - du Musée
Gauche - Saint-Patrick
Via - Clément
Droite - Bergevin
Gauche - Jean-Milot
Gauche - Louis-Fortier
Droite - Clément
Gauche - Laplante
Via - Cordner
Droite - Senkus
Gauche - Newman
Droite - Angrignon
Via - des Trinitaires
Droite - Terminus Angrignon
Station Angrignon 54112"""

# Conversion et affichage
#json_result = parse_route_text(texte_exemple)
#json_output = json.dumps(json_result, ensure_ascii=False, indent=2)
#print(json_output)

# Sauvegarde dans un fichier
#with open('route.json', 'w', encoding='utf-8') as f:
#    f.write(json_output)

# Lire depuis un fichier texte
with open('route.txt', 'r', encoding='utf-8') as f:
    texte = f.read()

# Convertir
result = parse_route_text(texte)

# Sauvegarder en JSON
with open('route.json', 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)

