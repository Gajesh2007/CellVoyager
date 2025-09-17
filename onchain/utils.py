import os
from typing import Optional


def load_openai_api_key() -> Optional[str]:
    key = os.getenv("OPENAI_API_KEY")
    if key:
        return key
    candidate_paths = []
    env_file = os.getenv("OPENAI_API_KEY_FILE")
    if env_file:
        candidate_paths.append(env_file)
    candidate_paths.extend([
        "/run/secrets/openai_api_key",
        "/run/secrets/OPENAI_API_KEY",
        "/var/run/secrets/openai_api_key",
        "/var/run/secrets/OPENAI_API_KEY",
        "/etc/secrets/openai_api_key",
        "/etc/secrets/OPENAI_API_KEY",
    ])
    for path in candidate_paths:
        try:
            if path and os.path.exists(path):
                with open(path, "r") as f:
                    content = f.read().strip()
                    if content:
                        return content
        except Exception:
            continue
    return None


