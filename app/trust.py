from __future__ import annotations

REPORT_TYPES = {
    "congestion": {
        "label": "Embouteillage bloqué",
        "ttl_min": 120,
        "severity": "basse",
        "major_push": False,
        "color": "#e67e22",
    },
    "breakdown_heavy": {
        "label": "Panne de poids lourd",
        "ttl_min": 180,
        "severity": "moyenne",
        "major_push": False,
        "color": "#8e44ad",
    },
    "flood": {
        "label": "Inondation / Route coupée",
        "ttl_min": 240,
        "severity": "haute",
        "major_push": True,
        "color": "#2980b9",
    },
    "checkpoint": {
        "label": "Contrôle / Barrage",
        "ttl_min": 120,
        "severity": "moyenne",
        "major_push": False,
        "color": "#c0392b",
    },
    "accident": {
        "label": "Accident",
        "ttl_min": 150,
        "severity": "haute",
        "major_push": True,
        "color": "#d35400",
    },
}


def clip(v: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, v))


def report_trust(pos_votes: int, neg_votes: int, voter_weights: list[float]) -> float:
    raw = (pos_votes - neg_votes) / (pos_votes + neg_votes + 3)
    avg_w = sum(voter_weights) / len(voter_weights) if voter_weights else 1.0
    return clip(0.35 + raw * avg_w, 0.0, 1.0)


def trust_label(trust: float, pos: int, neg: int, expired: bool) -> str:
    if expired:
        return "Expiré"
    if neg >= pos and neg >= 2:
        return "Contesté"
    if trust >= 0.55 and pos >= 2:
        return "Confirmé"
    if trust < 0.35 or (pos + neg < 2):
        return "Peu confirmé"
    return "Peu confirmé"


def should_auto_hide(pos: int, neg: int) -> bool:
    return neg >= 5 and neg >= 2 * pos


def device_weight(trust_score: float, device_age_hours: float) -> float:
    w = clip(float(trust_score), 0.2, 1.5)
    if device_age_hours < 24:
        w *= 0.5
    return w
