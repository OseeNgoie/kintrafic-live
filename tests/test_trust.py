from app.trust import REPORT_TYPES, clip, report_trust, should_auto_hide, trust_label, device_weight


def test_four_brief_types_present():
    for code in ("congestion", "breakdown_heavy", "flood", "checkpoint"):
        assert code in REPORT_TYPES
    assert 120 <= REPORT_TYPES["congestion"]["ttl_min"] <= 240
    assert 120 <= REPORT_TYPES["flood"]["ttl_min"] <= 240
    assert "pothole" in REPORT_TYPES
    assert "travaux" in REPORT_TYPES
    assert "nid" in REPORT_TYPES["pothole"]["label"].lower() or "poule" in REPORT_TYPES["pothole"]["label"].lower()


def test_trust_formula_and_labels():
    t = report_trust(3, 0, [1.0, 1.0, 1.0])
    assert 0.5 < t <= 1
    assert trust_label(0.2, 0, 0, False) == "Signalé"
    assert trust_label(0.7, 2, 0, False) == "Vérifié"
    assert trust_label(0.4, 1, 3, False) == "Contesté"
    assert trust_label(0.9, 5, 0, True) == "Expiré"
    assert should_auto_hide(1, 5)
    assert not should_auto_hide(3, 4)
    assert clip(2, 0, 1) == 1
    assert device_weight(0.9, 2) < device_weight(0.9, 48)
