"""Load class-style api_key.txt into Colab process environment only."""
import os
from pathlib import Path

ALLOWED_KEYS = {"OPENAI_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "AIVLE_ACCESS_PASSWORD", "GH_TOKEN"}

def load_key_file(filepath):
    p = Path(filepath)
    if not p.is_file():
        raise FileNotFoundError(f"api_key.txt를 찾지 못했습니다: {p}")
    loaded = []
    for number, raw in enumerate(p.read_text(encoding="utf-8-sig").splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"api_key.txt {number}행은 KEY=VALUE 형식이어야 합니다.")
        key, value = line.split("=", 1)
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key not in ALLOWED_KEYS or not value:
            raise ValueError(f"api_key.txt {number}행의 키 또는 값이 올바르지 않습니다.")
        os.environ[key] = value
        loaded.append(key)
    return loaded
