"""Horaires minimaux des CA 475 et 443, sans données personnelles.

Les résultats attendus sont transcrits et vérifiés à partir des exemples,
indépendamment de l'algorithme de résumé.
"""


def trajet(type_, depart, arrivee, ligne=None, direction=None):
    return {
        "type": type_, "ligne": ligne, "direction": direction,
        "depart": {"heure": depart}, "arrivee": {"heure": arrivee},
    }


def piece(identifiant, prise, fin, trajets, **champs):
    return {"id": identifiant, "prise": prise, "debut": prise, "fin": fin,
            "trajets": trajets, **champs}


def journee_475():
    return {
        "date": "2026-09-10", "journee_numero": 475, "temps_travaille": "7:30",
        "pieces": [
            piece("185-62", "17:11", "21:01", [
                trajet("service", "17:13", "17:55", "136", "nord"),
                trajet("service", "18:03", "18:40", "136", "sud"),
                trajet("service", "18:54", "19:29", "136", "nord"),
                trajet("haut_le_pied", "19:29", "19:52"),
                trajet("service", "20:03", "20:36", "136", "nord"),
                trajet("haut_le_pied", "20:36", "20:59"),
            ], duree="3:50"),
            piece("136-28", "22:43", "26:23", [
                trajet("service", "23:03", "23:35", "136", "nord"),
                trajet("service", "23:49", "24:15", "136", "sud"),
                trajet("service", "24:19", "24:50", "136", "nord"),
                trajet("service", "24:54", "25:19", "136", "sud"),
                trajet("service", "25:25", "25:52", "136", "nord"),
                trajet("entree", "25:52", "26:23"),
            ], duree="3:40"),
        ],
    }


# Heure, segment, direction, durée, battement, total, maximum.
ATTENDU_475 = [
    ("17:11", "prise", None, None, 2, 2, False),
    ("17:13", "136", "nord", 42, 8, 50, False),
    ("18:03", "136", "sud", 37, 14, 51, True),
    ("18:54", "136", "nord", 35, 0, 35, False),
    ("19:29", "hlp", None, 23, 11, 34, False),
    ("20:03", "136", "nord", 33, 0, 33, False),
    ("20:36", "hlp", None, 23, 2, 25, False),
    ("21:01", "fin", None, None, None, None, False),
    ("21:01", "pause", None, None, 102, 102, False),
    ("22:43", "prise", None, None, 20, 20, False),
    ("23:03", "136", "nord", 32, 14, 46, True),
    ("23:49", "136", "sud", 26, 4, 30, False),
    ("24:19", "136", "nord", 31, 4, 35, False),
    ("24:54", "136", "sud", 25, 6, 31, False),
    ("25:25", "136", "nord", 27, 0, 27, False),
    ("25:52", "entrée", None, 31, 10, 41, False),
    ("26:33", "fin", None, None, None, None, False),
]


def journee_443():
    return {
        "date": "2026-08-23", "journee_numero": 443, "temps_travaille": "7:30",
        "pieces": [
            piece("150-06", "11:18", "15:43", [
                trajet("sortie", "11:28", "11:38"),
                trajet("service", "11:38", "12:03", "150", "ouest"),
                trajet("service", "12:06", "12:36", "150", "est"),
                trajet("service", "12:39", "13:05", "150", "ouest"),
                trajet("service", "13:08", "13:38", "150", "est"),
                trajet("service", "13:41", "14:07", "150", "ouest"),
                trajet("service", "14:10", "14:40", "150", "est"),
                trajet("service", "14:43", "15:10", "150", "ouest"),
                trajet("service", "15:13", "15:43", "150", "est"),
            ], debut="11:28", duree="4:15"),
            piece("10-03", "16:49", "20:04", [
                trajet("service", "16:51", "17:17", "10", "nord"),
                trajet("service", "17:20", "17:52", "10", "sud"),
                trajet("service", "17:57", "18:23", "10", "nord"),
                trajet("service", "18:26", "18:58", "10", "sud"),
                trajet("service", "19:03", "19:27", "10", "nord"),
                trajet("service", "19:32", "20:04", "10", "sud"),
            ], duree="3:15"),
        ],
    }


ATTENDU_443 = [
    ("11:18", "prise", None, None, 10, 10, False),
    ("11:28", "sortie", None, 10, 0, 10, False),
    ("11:38", "150", "ouest", 25, 3, 28, True),
    ("12:06", "150", "est", 30, 3, 33, True),
    ("12:39", "150", "ouest", 26, 3, 29, True),
    ("13:08", "150", "est", 30, 3, 33, True),
    ("13:41", "150", "ouest", 26, 3, 29, True),
    ("14:10", "150", "est", 30, 3, 33, True),
    ("14:43", "150", "ouest", 27, 3, 30, True),
    ("15:13", "150", "est", 30, 0, 30, False),
    ("15:43", "fin", None, None, None, None, False),
    ("15:43", "pause", None, None, 66, 66, False),
    ("16:49", "prise", None, None, 2, 2, False),
    ("16:51", "10", "nord", 26, 3, 29, False),
    ("17:20", "10", "sud", 32, 5, 37, True),
    ("17:57", "10", "nord", 26, 3, 29, False),
    ("18:26", "10", "sud", 32, 5, 37, True),
    ("19:03", "10", "nord", 24, 5, 29, True),
    ("19:32", "10", "sud", 32, 0, 32, False),
    ("20:04", "fin", None, None, None, None, False),
]
