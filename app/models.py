from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class AntiCheatStatus(str, Enum):
    SUPPORTED = "Supported"
    RUNNING = "Running"
    BROKEN = "Broken"
    DENIED = "Denied"
    PLANNED = "Planned"
    UNLISTED = "Unlisted"


class AWACYGame(BaseModel):
    """Raw game representation from AreWeAntiCheatYet games.json."""
    name: str
    status: str = "Unlisted"
    anticheats: List[str] = Field(default_factory=list)
    notes: List[Any] = Field(default_factory=list)
    updates: List[Dict[str, Any]] = Field(default_factory=list)
    native: bool = False
    reference: str = ""
    storeIds: Dict[str, Any] = Field(default_factory=dict)
    slug: Optional[str] = None
    url: Optional[str] = None
    dateChanged: Optional[str] = None

    @property
    def steam_appid(self) -> Optional[str]:
        """Extract steam store id if available."""
        if isinstance(self.storeIds, dict) and "steam" in self.storeIds:
            val = self.storeIds["steam"]
            if val is not None:
                return str(val).strip()
        return None


class SteamGame(BaseModel):
    """Game representation returned by Steam GetOwnedGames API."""
    appid: int
    name: str = ""
    playtime_forever: int = 0
    img_icon_url: Optional[str] = None
    playtime_2weeks: Optional[int] = None


class EnrichedGame(BaseModel):
    """Unified game model combining Steam owned game and AWACY anti-cheat status."""
    appid: int
    name: str
    playtime_forever: int
    playtime_hours: float
    icon_url: Optional[str] = None
    header_url: str
    status: AntiCheatStatus
    anticheats: List[str] = Field(default_factory=list)
    native: bool = False
    notes: List[Any] = Field(default_factory=list)
    reference: Optional[str] = None
    updates: List[Dict[str, Any]] = Field(default_factory=list)
    slug: Optional[str] = None
    url: Optional[str] = None
    date_changed: Optional[str] = None
    store_ids: Dict[str, Any] = Field(default_factory=dict)
    notes_count: int = 0
    updates_count: int = 0
    is_tracked: bool = False
    protondb_tier: Optional[str] = "pending"
    protondb_confidence: Optional[str] = None
    protondb_score: Optional[float] = None


class ScanResponse(BaseModel):
    """Full scan response returned to the frontend."""
    steamid: str
    personaname: str = "Steam User"
    avatar: Optional[str] = None
    profileurl: Optional[str] = None
    total_games: int = 0
    tracked_games: int = 0
    status_counts: Dict[str, int] = Field(default_factory=dict)
    protondb_counts: Dict[str, int] = Field(default_factory=dict)
    playable_percentage: float = 0.0
    games: List[EnrichedGame] = Field(default_factory=list)
    is_private: bool = False
    is_demo: bool = False
    message: Optional[str] = None
