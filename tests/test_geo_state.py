from app.geo_state import summarize_reports


def test_empty_is_no_data():
    s = summarize_reports([])
    assert s["status_code"] == "pas_de_donnee"
    assert "Pas de donnée" in s["status_label"]


def test_verified_vs_signaled():
    sig = summarize_reports([{"type_code": "congestion", "trust": 0.35, "pos": 0, "neg": 0}])
    assert sig["status_code"] == "signale"
    ver = summarize_reports([{"type_code": "congestion", "trust": 0.7, "pos": 3, "neg": 0}])
    assert ver["status_code"] == "verifie"
    pothole = summarize_reports([{"type_code": "pothole", "trust": 0.52, "pos": 2, "neg": 0}])
    assert pothole["conditions"]
    assert pothole["conditions"][0]["type_code"] == "pothole"
    assert "Pas de donnée sur le trafic" in pothole["traffic_label"]
