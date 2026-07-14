#!/usr/bin/env python3
"""
test_gtfs_rt.py — Tests unitaires chauffeur.gtfs_rt

Couvre le décodeur protobuf minimal (parse_vehicle_positions) et la recherche
de véhicule (find_vehicle) sur des messages GTFS-RT synthétiques encodés à la
main dans le test (wire-format identique aux flux STM : position au field 2,
ID du bus = FeedEntity.id, label au field 7) — hermétique, aucun blob binaire.

Usage : python3 tests/test_gtfs_rt.py   (code de sortie 0 si tout passe)
"""
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from chauffeur.gtfs_rt import find_vehicle, parse_vehicle_positions  # noqa: E402


# ── Encodeur wire-format minimal (miroir du décodeur) ─────────────────────────

def _varint(n: int) -> bytes:
    out = b""
    while True:
        septet = n & 0x7F
        n >>= 7
        if n:
            out += bytes([septet | 0x80])
        else:
            return out + bytes([septet])


def _ld(field: int, payload: bytes) -> bytes:
    """Champ length-delimited (wire type 2)."""
    return _varint((field << 3) | 2) + _varint(len(payload)) + payload


def _f32(field: int, value: float) -> bytes:
    """Champ float 32 bits (wire type 5)."""
    return _varint((field << 3) | 5) + struct.pack("<f", value)


def _entite(entity_id: bytes, vp: bytes | None) -> bytes:
    payload = _ld(1, entity_id)
    if vp is not None:
        payload += _ld(4, vp)
    return _ld(2, payload)   # FeedEntity = field 2 du FeedMessage


def main() -> int:
    echecs = []

    def check(cond: bool, msg: str) -> None:
        if not cond:
            echecs.append(msg)

    # ── Flux synthétique : 1 véhicule complet + 1 entité sans position ───────
    vp_complet = (
        _ld(1, _ld(5, b"104"))                    # TripDescriptor.route_id
        + _ld(2, _f32(1, 45.5) + _f32(2, -73.6))  # Position (field 2, façon STM)
        + _ld(7, "38-013".encode())               # label interne STM
    )
    vp_sans_position = _ld(1, _ld(5, b"51"))
    feed = (_entite(b"31228", vp_complet)
            + _entite(b"99999", vp_sans_position)
            + _entite(b"88888", None))            # entité sans VehiclePosition

    vehicules = parse_vehicle_positions(feed)
    check(len(vehicules) == 1,
          f"parse: 1 véhicule attendu (positions seulement), obtenu {len(vehicules)}")
    if vehicules:
        v = vehicules[0]
        check(v["v_id"] == "31228", f"parse: v_id attendu 31228, obtenu {v['v_id']}")
        check(v["v_label"] == "38-013", f"parse: label attendu 38-013, obtenu {v['v_label']}")
        check(v["route_id"] == "104", f"parse: route_id attendu 104, obtenu {v['route_id']}")
        check(round(v["lat"], 4) == 45.5 and round(v["lon"], 4) == -73.6,
              f"parse: lat/lon inattendus : {v['lat']}, {v['lon']}")

    # ── Robustesse : octets invalides → liste vide, sans exception ───────────
    try:
        check(parse_vehicle_positions(b"\x00\x01\x02\xff\xff\x9c") == [],
              "parse: octets invalides devraient donner []")
        check(parse_vehicle_positions(b"") == [],
              "parse: flux vide devrait donner []")
    except Exception as e:
        echecs.append(f"parse: exception sur octets invalides : {e}")

    # ── find_vehicle : normalisation xx-xxx, repli sur v_id ──────────────────
    check(find_vehicle("38013", vehicules) is not None,
          "find: '38013' devrait matcher le label '38-013' (normalisation)")
    check(find_vehicle("38-013", vehicules) is not None,
          "find: '38-013' devrait matcher le label tel quel")
    check(find_vehicle("31-228", vehicules) is not None,
          "find: '31-228' devrait matcher l'ID d'entité '31228'")
    check(find_vehicle("12345", vehicules) is None,
          "find: numéro inconnu devrait donner None")

    # ── Résultat ──────────────────────────────────────────────────────────────
    if echecs:
        print("✗ test_gtfs_rt")
        for e in echecs:
            print(f"    {e}")
        print("\n0/1 cas réussis")
        return 1

    print("✓ parse_vehicle_positions (entités, position field 2, robustesse) + find_vehicle")
    print("\n1/1 cas réussis")
    return 0


if __name__ == "__main__":
    sys.exit(main())
