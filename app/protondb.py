import asyncio
import json
import logging
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

import httpx

from app.config import settings

logger = logging.getLogger("cheatsheet.protondb")


class ProtonDBCache:
    """
    Thread-safe in-memory cache for ProtonDB compatibility reports.
    Provides batch resolution with a bounded semaphore and persistent disk caching.
    """

    def __init__(self, data_dir: Path = settings.DATA_DIR):
        self.data_dir = data_dir
        self.cache_file = data_dir / "protondb_cache.json"
        self._cache: Dict[int, Dict[str, Any]] = {}
        self._lock = threading.RLock()

    def load_cache(self) -> None:
        """Load persistent ProtonDB cache or bundled seed file from disk on startup."""
        seed_file = self.data_dir / "seed_protondb.json"
        target_file = None
        if self.cache_file.exists() and self.cache_file.stat().st_size > 0:
            target_file = self.cache_file
        elif seed_file.exists() and seed_file.stat().st_size > 0:
            target_file = seed_file

        if target_file:
            try:
                with open(target_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                with self._lock:
                    self._cache = {int(k): v for k, v in data.items() if isinstance(v, dict)}
                logger.info("Loaded %d ProtonDB tier summaries from %s.", len(self._cache), target_file.name)
            except Exception as e:
                logger.warning("Failed to load ProtonDB cache from %s: %s", target_file, e)

    def save_cache(self) -> None:
        """Save in-memory cache to disk."""
        try:
            self.data_dir.mkdir(parents=True, exist_ok=True)
            with self._lock:
                data_copy = {str(k): v for k, v in self._cache.items()}
            temp_file = self.cache_file.with_suffix(".tmp")
            with open(temp_file, "w", encoding="utf-8") as f:
                json.dump(data_copy, f)
            temp_file.replace(self.cache_file)
        except Exception as e:
            logger.debug("Failed to write ProtonDB disk cache: %s", e)

    def get(self, appid: int) -> Optional[Dict[str, Any]]:
        """Get cached ProtonDB summary in O(1) time."""
        with self._lock:
            return self._cache.get(appid)

    def set(self, appid: int, summary: Dict[str, Any]) -> None:
        """Cache a ProtonDB summary."""
        with self._lock:
            self._cache[appid] = summary

    async def fetch_summary(self, client: httpx.AsyncClient, appid: int, semaphore: asyncio.Semaphore) -> Optional[Dict[str, Any]]:
        """Fetch a single game's ProtonDB summary via their JSON endpoint."""
        cached = self.get(appid)
        if cached is not None:
            return cached

        url = f"https://www.protondb.com/api/v1/reports/summaries/{appid}.json"
        async with semaphore:
            try:
                resp = await client.get(url, timeout=3.5)
                if resp.status_code == 200:
                    data = resp.json()
                    summary = {
                        "tier": data.get("tier", "pending").lower(),
                        "confidence": data.get("confidence", "none"),
                        "score": data.get("score", 0.0),
                        "total": data.get("total", 0),
                        "bestReportedTier": data.get("bestReportedTier", "pending").lower(),
                    }
                    self.set(appid, summary)
                    return summary
                elif resp.status_code == 404:
                    # Not enough reports on ProtonDB
                    summary = {
                        "tier": "pending",
                        "confidence": "none",
                        "score": 0.0,
                        "total": 0,
                    }
                    self.set(appid, summary)
                    return summary
            except Exception:
                # Network or timeout, fallback to pending without caching error
                pass
        return None

    async def resolve_many(self, client: httpx.AsyncClient, appids: List[int], max_concurrency: int = 15) -> Dict[int, Dict[str, Any]]:
        """
        Concurrently resolve ProtonDB ratings for multiple AppIDs.
        Uses in-memory cache first, then parallel queries for missing entries.
        """
        results: Dict[int, Dict[str, Any]] = {}
        missing_appids: List[int] = []

        for aid in appids:
            cached = self.get(aid)
            if cached is not None:
                results[aid] = cached
            else:
                missing_appids.append(aid)

        if missing_appids:
            # Limit parallel queries to max_concurrency
            sem = asyncio.Semaphore(max_concurrency)
            tasks = [self.fetch_summary(client, aid, sem) for aid in missing_appids]
            resolved = await asyncio.gather(*tasks, return_exceptions=True)

            for aid, res in zip(missing_appids, resolved):
                if isinstance(res, dict):
                    results[aid] = res
                else:
                    results[aid] = {"tier": "pending", "confidence": "none", "score": 0.0, "total": 0}

            # Persist newly resolved entries
            self.save_cache()

        return results


# Global singleton
protondb_cache = ProtonDBCache()
