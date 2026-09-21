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


def test_swap_railway_dbname_to_postgres():
    from app.db_url import database_name, with_database_name

    raw = "postgresql+psycopg://postgres:secret@10.130.125.7:5432/railway"
    assert database_name(raw) == "railway"
    pg = with_database_name(raw, "postgres")
    assert database_name(pg) == "postgres"
    assert "10.130.125.7" in pg


def test_missing_database_detection():
    from app.db import is_missing_database

    class Fake(Exception):
        sqlstate = "3D000"

    assert is_missing_database(
        Exception('connection failed: FATAL: database "railway" does not exist')
    )
    assert is_missing_database(Fake("catalog"))
    assert not is_missing_database(Exception("password authentication failed"))
