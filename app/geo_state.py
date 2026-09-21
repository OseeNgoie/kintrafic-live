"""Aggregate community reports into honest axis / point status (no fake live traffic)."""

from __future__ import annotations

from app.trust import REPORT_TYPES, trust_label

TRAFFIC_TYPES = {"congestion", "breakdown_heavy", "accident", "checkpoint"}
CONDITION_TYPES = {"pothole", "travaux", "flood"}


def summarize_reports(rows: list[dict]) -> dict:
    """rows: type_code, trust, pos, neg, expired optional, id optional, label optional."""
    if not rows:
        return {
            "status_code": "pas_de_donnee",
            "status_label": "Pas de donnée",
            "traffic_label": "Pas de donnée communautaire",
            "conditions": [],
            "reports": [],
            "verified": False,
        }

    items = []
    for r in rows:
        expired = bool(r.get("expired"))
        label = trust_label(float(r.get("trust") or 0), int(r.get("pos") or 0), int(r.get("neg") or 0), expired)
        meta = REPORT_TYPES.get(r["type_code"], {})
        items.append(
            {
                "id": r.get("id"),
                "type_code": r["type_code"],
                "label": meta.get("label", r["type_code"]),
                "kind": meta.get("kind", "trafic"),
                "color": meta.get("color", "#888"),
                "trust_label": label,
                "pos": r.get("pos"),
                "neg": r.get("neg"),
            }
        )

    labels = {i["trust_label"] for i in items}
    if "Vérifié" in labels:
        status_code, status_label = "verifie", "Vérifié (votes)"
    elif "Contesté" in labels and "Signalé" not in labels:
        status_code, status_label = "conteste", "Contesté"
    else:
        status_code, status_label = "signale", "Signalé"

    traffic = [i for i in items if i["type_code"] in TRAFFIC_TYPES]
    if not traffic:
        traffic_label = "Pas de donnée sur le trafic"
    else:
        best = sorted(traffic, key=lambda x: (x["trust_label"] != "Vérifié", x["label"]))[0]
        traffic_label = f"{best['label']} · {best['trust_label']}"

    cond_map: dict[str, dict] = {}
    for i in items:
        if i["type_code"] not in CONDITION_TYPES:
            continue
        slot = cond_map.setdefault(
            i["type_code"],
            {"type_code": i["type_code"], "label": i["label"], "trust_label": i["trust_label"], "n": 0},
        )
        slot["n"] += 1
        if i["trust_label"] == "Vérifié":
            slot["trust_label"] = "Vérifié"

    return {
        "status_code": status_code,
        "status_label": status_label,
        "traffic_label": traffic_label,
        "conditions": list(cond_map.values()),
        "reports": items,
        "verified": status_code == "verifie",
    }
