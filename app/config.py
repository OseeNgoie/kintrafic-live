from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+psycopg://kintrafic:kintrafic@127.0.0.1:5432/kintrafic"
    secret_key: str = "change-me-in-production"
    admin_login: str = "osee"
    admin_password: str = "KinTrafic-Local-2026!"
    admin_totp_required: bool = False
    app_port: int = 43147
    public_origin: str = "http://127.0.0.1:43147"
    tile_upstream: str = "https://basemaps.cartocdn.com/rastertiles/voyager"
    mock_payments: bool = True
    mock_otp: bool = True
    seed_demo: bool = True
    eula_version: str = "2026-09-21.1"
    privacy_version: str = "2026-09-21.1"
    premium_price_cdf: int = 1500
    premium_days: int = 30
    tile_cache_dir: str = "data/tiles"
    session_days: int = 30
    admin_idle_minutes: int = 30

    # Kinshasa urbain dense (WGS84)
    kin_bbox_west: float = 15.20
    kin_bbox_south: float = -4.50
    kin_bbox_east: float = 15.55
    kin_bbox_north: float = -4.20
    default_lat: float = -4.305
    default_lng: float = 15.313  # Gombe / 30 Juin


@lru_cache
def get_settings() -> Settings:
    return Settings()
