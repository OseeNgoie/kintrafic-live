from app.db_url import sqlalchemy_url, with_connect_timeout


def test_railway_postgres_url_becomes_psycopg():
    raw = "postgresql://postgres:secret@postgres.railway.internal:5432/railway"
    assert sqlalchemy_url(raw) == (
        "postgresql+psycopg://postgres:secret@postgres.railway.internal:5432/railway"
    )


def test_postgres_scheme_and_existing_driver():
    assert sqlalchemy_url("postgres://u:p@h:5432/db").startswith("postgresql+psycopg://")
    already = "postgresql+psycopg://u:p@h:5432/db"
    assert sqlalchemy_url(already) == already
    assert sqlalchemy_url("postgresql+psycopg2://u:p@h:5432/db").startswith(
        "postgresql+psycopg://"
    )


def test_connect_timeout_query():
    url = with_connect_timeout("postgresql+psycopg://u:p@h:5432/db")
    assert "connect_timeout=8" in url
