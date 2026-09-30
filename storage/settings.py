import json
from dataclasses import asdict, fields
from pathlib import Path
from core.models import Settings


def load_settings(root: Path):
    path = root / "data" / "settings.json"
    if not path.exists():
        return Settings()
    raw = json.loads(path.read_text(encoding="utf-8"))
    allowed = {f.name for f in fields(Settings)}
    result = Settings(**{key: val for key, val in raw.items() if key in allowed})
    result.validate()
    return result


def save_settings(root: Path, settings: Settings):
    settings.validate()
    path = root / "data" / "settings.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(asdict(settings), ensure_ascii=False, indent=2), encoding="utf-8")
    temp.replace(path)
