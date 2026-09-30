from dataclasses import dataclass
from enum import Enum
from datetime import datetime, timezone


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Status(str, Enum):
    INDEXED = "INDEXED"
    DISCOVERED_NOT_INDEXED = "DISCOVERED_NOT_INDEXED"
    CRAWLED_NOT_INDEXED = "CRAWLED_NOT_INDEXED"
    REQUESTED_RECENTLY = "REQUESTED_RECENTLY"
    ALTERNATE_CANONICAL = "ALTERNATE_CANONICAL"
    REDIRECT = "REDIRECT"
    NOINDEX = "NOINDEX"
    ROBOTS_BLOCKED = "ROBOTS_BLOCKED"
    NOT_FOUND = "NOT_FOUND"
    SERVER_ERROR = "SERVER_ERROR"
    TEMP_ERROR = "TEMP_ERROR"
    LOGIN_REQUIRED = "LOGIN_REQUIRED"
    TIMEOUT = "TIMEOUT"
    UNKNOWN = "UNKNOWN"


@dataclass
class Inspection:
    status: Status
    raw: str = ""
    canonical_url: str | None = None
    error: str | None = None


@dataclass
class Settings:
    property_url: str = ""
    chrome_profile_path: str = ""
    max_urls: int = 30
    request_cooldown_days: int = 7
    daily_request_limit: int = 10
    auto_request: bool = False
    retries: int = 2
    timeout_seconds: int = 45

    def validate(self):
        limits = [("max_urls", 1, 10000), ("request_cooldown_days", 1, 3650),
                  ("daily_request_limit", 0, 1000), ("retries", 0, 5),
                  ("timeout_seconds", 10, 300)]
        for key, low, high in limits:
            value = getattr(self, key)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"{key} must be an integer from {low} to {high}.")
        for key in ("auto_request",):
            if type(getattr(self, key)) is not bool:
                raise ValueError(f"{key} must be a boolean.")
        if not isinstance(self.property_url, str):
            raise ValueError("property_url must be a string.")
        if not isinstance(self.chrome_profile_path, str):
            raise ValueError("chrome_profile_path must be a string.")
