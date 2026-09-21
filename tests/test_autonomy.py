from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from app.baseline import congestion_for
from app.traffic_fusion import city_summary, compact_axis, fuse_axis
from app.veille import classify_text, load_sample, SOURCE_TAG

KIN = ZoneInfo("Africa/Kinshasa")


def test_weekday_peak_sature_on_majors():
    assert congestion_for("Boulevard du 30 Juin", 0, 8) == "sature"
    assert congestion_for("Route des Poids Lourds", 2, 18) == "sature"
    assert congestion_for("Avenue Kasa-Vubu", 4, 7) == "sature"


def test_offpeak_and_sunday_fluide():
    assert congestion_for("Boulevard du 30 Juin", 0, 2) == "fluide"
    assert congestion_for("Avenue de l’Université", 6, 8) == "fluide"


def test_user_report_overrides_baseline():
    now = datetime(2026, 9, 21, 8, 0, tzinfo=KIN)
    fused = fuse_axis(
        axis_id=1,
        axis_name="Boulevard du 30 Juin",
        reports=[
            {
                "type_code": "accident",
                "source": "community",
                "trust": 0.6,
                "pos": 2,
                "neg": 0,
                "expires_at": now + timedelta(minutes=40),
            }
        ],
        baseline="fluide",
        now=now,
    )
    assert fused["c"] == "sature"
    assert fused["s"] == "user"
    assert fused["verified"] is True


def test_expiry_falls_back_to_baseline():
    now = datetime(2026, 9, 21, 11, 0, tzinfo=KIN)
    fused = fuse_axis(
        axis_id=1,
        axis_name="Boulevard du 30 Juin",
        reports=[],
        baseline="dense",
        now=now,
    )
    assert fused["c"] == "dense"
    assert fused["s"] == "base"
    compact = compact_axis(fused)
    assert compact["c"] == "dense"
    city = city_summary([fused] * 5 + [dict(fused, c="fluide", s="base")] * 13)
    assert city["n"]["d"] == 5


def test_veille_not_classified_as_user():
    now = datetime(2026, 9, 21, 11, 0, tzinfo=KIN)
    fused = fuse_axis(
        axis_id=2,
        axis_name="Avenue Kasa-Vubu",
        reports=[{"type_code": "flood", "source": "veille", "trust": 0.28, "pos": 0, "neg": 0, "expires_at": now + timedelta(hours=1)}],
        baseline="fluide",
        now=now,
    )
    assert fused["s"] == "veille"
    assert fused["verified"] is False
    assert fused["c"] == "sature"


def test_keywords_and_sample_cache():
    assert classify_text("Gros embouteillage à Limete") == "congestion"
    assert classify_text("Accident boulevard du 30 Juin") == "accident"
    sample = load_sample()
    assert sample
    assert sample[0]["external_key"].startswith("sample:")
    assert SOURCE_TAG.startswith("Source :")
