from app.services.metrics import ALERT_TEXT


def test_alert_copy_is_recommendation_only():
    assert "Ceci n’active rien" in ALERT_TEXT or "Ceci n'active rien" in ALERT_TEXT.replace("’", "'")
    assert "recommandée" in ALERT_TEXT
