"""chauffeur.avis — textes d'avis, d'attribution et de limitation de responsabilité.

Source unique des mentions affichées par l'application et imprimées dans les
rapports (voir NOTICE.md pour la version complète).
"""
URL_DONNEES_OUVERTES = "https://www.stm.info/a-propos/documents-donnees/donnees-ouvertes"

# Attribution exigée par la licence CC BY 4.0 des données ouvertes.
ATTRIBUTION = (
    "Contient des données de la Société de transport de Montréal (STM), offertes sous "
    f"licence CC BY 4.0 ({URL_DONNEES_OUVERTES}). "
    "Projet indépendant, non officiel et non cautionné par la STM."
)

AVIS_INFORMATION = (
    "Information non officielle, fournie sans garantie d'exactitude, d'exhaustivité ni de "
    "disponibilité ; elle ne remplace pas les consignes officielles."
)

AVIS_PORTAIL = (
    "Vous êtes seul responsable de votre connexion à employe.stm.info (identifiants, session, "
    "cookies) et du respect des règles et politiques de votre organisation."
)

# Mention courte imprimée au bas des rapports.
AVIS_RAPPORT = f"{AVIS_INFORMATION} {ATTRIBUTION}"
