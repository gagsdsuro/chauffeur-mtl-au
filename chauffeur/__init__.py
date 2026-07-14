"""chauffeur — noyau de domaine partagé (carte agent, G-D, évènements).

Package sans dépendance UI/CLI : réutilisé par les scripts (gen_rapport,
gen_rapport_v2, rapport_gd, refresh_events…) et l'app Streamlit (app/ui.py)
pour éviter la duplication de la logique de traitement.
"""
