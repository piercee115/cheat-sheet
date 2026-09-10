from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application configuration loaded from environment and .env file."""
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

    STEAM_API_KEY: str = ""
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    CACHE_TTL_HOURS: int = 3
    AWACY_DATABASE_URL: str = "https://raw.githubusercontent.com/AreWeAntiCheatYet/AreWeAntiCheatYet/master/games.json"
    DATA_DIR: Path = Path("data")
    APP_NAME: str = "Are We Anti-Cheat Yet? Steam Library Checker"
    DEBUG: bool = False

    @property
    def has_steam_key(self) -> bool:
        """Returns whether a Steam API key is provided and non-empty."""
        return bool(self.STEAM_API_KEY and self.STEAM_API_KEY.strip())


settings = Settings()
