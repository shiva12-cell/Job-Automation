"""
Persistent State & Seen Jobs Cache Manager.
Prevents the application bot from restarting from the same jobs again and again.
Tracks:
1. Seen / processed job URLs (Applied, Skipped Low Match, Skipped Company Site, Failed Unconfirmed, Manual).
2. Pagination cursor per keyword so the scraper automatically advances to fresh pages.
3. Round-robin keyword rotation for continuous discovery.
"""

import json
import time
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Any, Optional, List

if sys.stdout and hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def safe_print(msg: str):
    """Safely prints message avoiding Windows charmap UnicodeEncodeError."""
    try:
        print(msg)
    except Exception:
        try:
            print(msg.encode("ascii", "replace").decode("ascii"))
        except Exception:
            pass


STATE_DIR = Path("config/data")
SEEN_JOBS_FILE = STATE_DIR / "seen_jobs.json"


class SeenJobsManager:
    """Manages persistent cache of seen/processed jobs and pagination cursors."""

    def __init__(self, file_path: Path = SEEN_JOBS_FILE):
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self.data: Dict[str, Any] = {
            "seen_jobs": {},
            "pagination_cursors": {},
            "rotation_index": 0,
        }
        self.load()

    def load(self) -> None:
        """Loads state from JSON file if available."""
        if self.file_path.exists():
            try:
                with open(self.file_path, "r", encoding="utf-8") as f:
                    content = json.load(f)
                    if isinstance(content, dict):
                        self.data["seen_jobs"] = content.get("seen_jobs", {})
                        self.data["pagination_cursors"] = content.get("pagination_cursors", {})
                        self.data["rotation_index"] = content.get("rotation_index", 0)
            except Exception as e:
                print(f"[StateManager] Warning loading state: {e}. Starting fresh.")

    def save(self) -> None:
        """Persists state to JSON file."""
        try:
            self.file_path.parent.mkdir(parents=True, exist_ok=True)
            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, indent=2)
        except Exception as e:
            safe_print(f"[StateManager] Warning saving state: {e}")

    def is_seen(self, url: str, cooldown_hours: int = 48) -> bool:
        """
        Returns True if the job has already been processed or is on cooldown:
        - APPLIED / MANUAL_SAVED / SKIPPED_LOW_MATCH / SKIPPED_COMPANY_SITE:
          Persistently ignored for 14 days so bot never restarts from the same jobs.
        - FAILED_UNCONFIRMED: Ignored during cooldown_hours to prevent repetitive failure loops.
        """
        if not url:
            return False

        clean_url = self._normalize_url(url)
        entry = self.data["seen_jobs"].get(clean_url)
        if not entry:
            return False

        status = entry.get("status")
        timestamp_str = entry.get("timestamp")

        if not timestamp_str:
            return True

        try:
            ts = datetime.fromisoformat(timestamp_str)
            age = datetime.now() - ts

            # Permanent statuses: ignore for 14 days
            if status in ["APPLIED", "MANUAL_SAVED", "SKIPPED_LOW_MATCH", "SKIPPED_COMPANY_SITE"]:
                return age < timedelta(days=14)

            # Failed submissions: cooldown for cooldown_hours
            if status == "FAILED_UNCONFIRMED":
                return age < timedelta(hours=cooldown_hours)

        except Exception:
            return True

        return True

    def record_job(
        self,
        url: str,
        company: str,
        title: str,
        status: str,
        match_pct: float = 0.0,
        notes: str = ""
    ) -> None:
        """Records a job into the persistent seen cache and saves to disk."""
        if not url:
            return

        clean_url = self._normalize_url(url)
        prev = self.data["seen_jobs"].get(clean_url, {})
        retry_count = prev.get("retry_count", 0) + (1 if status == "FAILED_UNCONFIRMED" else 0)

        self.data["seen_jobs"][clean_url] = {
            "company": company,
            "title": title,
            "status": status,
            "match_pct": round(match_pct, 1),
            "timestamp": datetime.now().isoformat(),
            "retry_count": retry_count,
            "notes": notes,
        }
        self.save()

    def sync_from_excel(self, excel_manager) -> int:
        """
        Populates seen jobs cache directly from existing entries in the Excel tracker.
        Ensures all past applications in 'All Applications' and 'Manual' tabs are cached.
        """
        def _parse_pct(val) -> float:
            if not val:
                return 0.0
            if isinstance(val, (int, float)):
                return float(val)
            clean_str = str(val).replace("%", "").strip()
            try:
                return float(clean_str)
            except Exception:
                return 0.0

        count = 0
        try:
            # Sync applied jobs
            applied_rows = excel_manager.get_all_rows(sheet_name="All Applications")
            for r in applied_rows:
                u = r.get("Job URL") or ""
                if u and "http" in u:
                    clean_u = self._normalize_url(u)
                    if clean_u not in self.data["seen_jobs"]:
                        self.data["seen_jobs"][clean_u] = {
                            "company": r.get("Company", ""),
                            "title": r.get("Job Title", ""),
                            "status": "APPLIED",
                            "match_pct": _parse_pct(r.get("Match %")),
                            "timestamp": datetime.now().isoformat(),
                            "retry_count": 0,
                            "notes": "Synced from Excel tracker",
                        }
                        count += 1

            # Sync manual jobs
            manual_rows = excel_manager.get_all_rows(sheet_name="Manual")
            for r in manual_rows:
                u = r.get("Job URL") or ""
                if u and "http" in u:
                    clean_u = self._normalize_url(u)
                    if clean_u not in self.data["seen_jobs"]:
                        self.data["seen_jobs"][clean_u] = {
                            "company": r.get("Company", ""),
                            "title": r.get("Job Title", ""),
                            "status": "MANUAL_SAVED",
                            "match_pct": _parse_pct(r.get("Match %")),
                            "timestamp": datetime.now().isoformat(),
                            "retry_count": 0,
                            "notes": "Synced from Excel manual sheet",
                        }
                        count += 1

            if count > 0:
                self.save()
                safe_print(f"[StateManager] ✓ Synced {count} existing jobs from Excel tracker into seen cache.")
        except Exception as e:
            safe_print(f"[StateManager] Note during Excel sync: {e}")
        return count

    def get_cursor(self, keyword: str) -> int:
        """Gets current pagination page for a keyword (defaults to page 1)."""
        clean_kw = keyword.strip().lower()
        return self.data["pagination_cursors"].get(clean_kw, 1)

    def set_cursor(self, keyword: str, page_num: int) -> None:
        """Sets explicit pagination cursor for a keyword."""
        clean_kw = keyword.strip().lower()
        self.data["pagination_cursors"][clean_kw] = max(1, page_num)
        self.save()

    def advance_cursor(self, keyword: str, max_pages: int = 10) -> int:
        """Advances pagination page cursor by 1, wrapping around after max_pages."""
        return self.advance_cursor_by(keyword, pages_count=1, max_pages=max_pages)

    def advance_cursor_by(self, keyword: str, pages_count: int = 1, max_pages: int = 10) -> int:
        """Advances pagination page cursor by the given number of pages, wrapping around."""
        clean_kw = keyword.strip().lower()
        curr = self.data["pagination_cursors"].get(clean_kw, 1)
        next_page = curr + max(1, pages_count)
        if next_page > max_pages:
            next_page = 1
        self.data["pagination_cursors"][clean_kw] = next_page
        self.save()
        return next_page

    def reset_cursor(self, keyword: Optional[str] = None) -> None:
        """Resets cursor for a keyword or all keywords back to page 1."""
        if keyword:
            clean_kw = keyword.strip().lower()
            self.data["pagination_cursors"][clean_kw] = 1
        else:
            self.data["pagination_cursors"] = {}
        self.save()

    def get_next_rotated_keyword(self, keywords: List[str]) -> str:
        """Returns the next keyword in round-robin order."""
        if not keywords:
            return "data analyst"

        idx = self.data.get("rotation_index", 0) % len(keywords)
        kw = keywords[idx]
        self.data["rotation_index"] = (idx + 1) % len(keywords)
        self.save()
        return kw

    def purge_manual_seen_jobs(self) -> int:
        """
        Removes all MANUAL_SAVED entries from seen cache and resets cursors
        so that manual/filtered jobs can be cleanly re-evaluated in fresh testing.
        """
        seen = self.data.get("seen_jobs", {})
        keys_to_remove = [k for k, v in seen.items() if v.get("status") == "MANUAL_SAVED"]
        for k in keys_to_remove:
            del seen[k]
        self.save()
        safe_print(f"[StateManager] 🧹 Purged {len(keys_to_remove)} MANUAL_SAVED records from seen cache.")
        return len(keys_to_remove)

    def clear_seen_cache(self) -> int:
        """Clears all seen cache entries (e.g. for complete fresh reset)."""
        count = len(self.data["seen_jobs"])
        self.data["seen_jobs"] = {}
        self.data["pagination_cursors"] = {}
        self.save()
        return count

    def get_stats(self) -> Dict[str, Any]:
        """Returns structured metrics of seen cache entries and pagination cursors."""
        seen = self.data.get("seen_jobs", {})
        counts = {
            "total_seen": len(seen),
            "applied": 0,
            "manual_saved": 0,
            "skipped_low_match": 0,
            "skipped_company_site": 0,
            "failed_unconfirmed": 0,
            "other": 0,
        }
        for entry in seen.values():
            st = entry.get("status", "")
            if st == "APPLIED":
                counts["applied"] += 1
            elif st == "MANUAL_SAVED":
                counts["manual_saved"] += 1
            elif st == "SKIPPED_LOW_MATCH":
                counts["skipped_low_match"] += 1
            elif st == "SKIPPED_COMPANY_SITE":
                counts["skipped_company_site"] += 1
            elif st == "FAILED_UNCONFIRMED":
                counts["failed_unconfirmed"] += 1
            else:
                counts["other"] += 1

        return {
            "counts": counts,
            "pagination_cursors": self.data.get("pagination_cursors", {}),
            "rotation_index": self.data.get("rotation_index", 0),
        }

    def _normalize_url(self, url: str) -> str:
        """Normalizes job URL to strip query tracking parameters for deduplication."""
        base = url.split("?")[0].strip().rstrip("/")
        return base.lower()


# Global Singleton instance
seen_manager = SeenJobsManager()
