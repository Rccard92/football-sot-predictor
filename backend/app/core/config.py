from functools import lru_cache

from dotenv import load_dotenv
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str
    api_football_key: str = ""
    api_football_base_url: str = "https://v3.football.api-sports.io"
    cors_origins: str = (
        "https://frontend-production-9b20.up.railway.app,"
        "http://localhost:5173,"
        "http://localhost:3000"
    )
    frontend_origins: str = ""
    app_env: str = "development"
    default_league_id: int = 135
    default_season: int = 2025
    default_competition_key: str = "serie_a_italy_2025"
    # Fallback numerico quando non c'è media lega (<3 partite o nessuna partita precedente in lega)
    sot_feature_fallback_baseline: float | None = 3.0

    # SportAPI RapidAPI (secondaria: mapping/lineups debug only — non usata nel modello se false)
    sportapi_enabled: bool = False
    sportapi_rapidapi_key: str = ""
    sportapi_rapidapi_host: str = "sportapi7.p.rapidapi.com"
    sportapi_base_url: str = "https://sportapi7.p.rapidapi.com"
    use_sportapi_lineups_in_model: bool = False
    use_sportapi_lineup_impact_in_model: bool = False

    # OpenAI (diagnostico laboratorio predittivo — opzionale)
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"

    # Job pre-match (cron Railway + pulsante Admin)
    cron_secret: str = Field(
        default="",
        validation_alias=AliasChoices("CRON_SECRET", "ADMIN_CRON_SECRET"),
    )
    prematch_refresh_minutes_before: int = 30
    prematch_refresh_window_minutes: int = 10
    prematch_refresh_skip_recent_minutes: int = 8

    @property
    def admin_cron_secret(self) -> str:
        """Retrocompatibilità: stesso valore di cron_secret."""
        return self.cron_secret

    @property
    def cors_origins_list(self) -> list[str]:
        raw = self.cors_origins
        if self.frontend_origins.strip():
            raw = f"{raw},{self.frontend_origins}" if raw else self.frontend_origins
        seen: set[str] = set()
        out: list[str] = []
        for part in raw.split(","):
            o = part.strip()
            if o and o not in seen:
                seen.add(o)
                out.append(o)
        return out


@lru_cache
def get_settings() -> Settings:
    return Settings()


def sportapi_configured() -> bool:
    """True se SportAPI è abilitata e la chiave RapidAPI è presente."""
    s = get_settings()
    return bool(s.sportapi_enabled) and bool((s.sportapi_rapidapi_key or "").strip())
