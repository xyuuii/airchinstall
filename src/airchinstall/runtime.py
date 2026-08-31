from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def session_socket_path(runtime_dir: Path) -> Path:
    candidate = runtime_dir / "session.sock"
    if len(os.fsencode(candidate)) < 100:
        return candidate
    digest = hashlib.sha256(os.fsencode(runtime_dir)).hexdigest()[:12]
    return Path(tempfile.gettempdir()) / f"airchinstall-{digest}.sock"
