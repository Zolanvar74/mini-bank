import json
import threading
from pathlib import Path

from server.app.core.config import settings


_log_lock = threading.Lock()


def write_audit_log(entry: dict) -> None:
    log_path = Path(settings.log_path)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    line = json.dumps(
        entry,
        ensure_ascii=False,
        separators=(",", ":"),
    )

    with _log_lock:
        with log_path.open(
            "a",
            encoding="utf-8",
        ) as log_file:
            log_file.write(line + "\n")
            log_file.flush()