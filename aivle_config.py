"""AIVLE API credentials. Compatible with the class api_key.txt (KEY=VALUE) format.

Never print secrets or commit api_key.txt. Session uploads are kept in Streamlit session state.
"""
import os
from pathlib import Path

ALLOWED_KEYS = (
    "OPENAI_API_KEY", "GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "AIVLE_ACCESS_PASSWORD", "GH_TOKEN"
)


def parse_key_text(content):
    """Read course-style KEY=VALUE lines; reject unknown keys and malformed lines."""
    if isinstance(content, bytes):
        content = content.decode("utf-8-sig")
    result = {}
    for number, raw in enumerate(content.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise ValueError(f"api_key.txt {number}번째 줄은 KEY=VALUE 형식이어야 합니다.")
        key, value = line.split("=", 1)
        key = key.strip()
        if key not in ALLOWED_KEYS:
            raise ValueError(f"api_key.txt {number}번째 줄에 허용하지 않은 키 이름이 있습니다: {key}")
        value = value.strip().strip('"').strip("'")
        if not value:
            raise ValueError(f"api_key.txt {number}번째 줄의 값이 비어 있습니다: {key}")
        result[key] = value
    return result


def read_local_key_file(project_dir=None):
    """For Colab/local dev. The Cloud deployment must not commit this file."""
    root = Path(project_dir) if project_dir else Path(__file__).resolve().parent
    file = root / "api_key.txt"
    return parse_key_text(file.read_text(encoding="utf-8-sig")) if file.is_file() else {}


def get_settings(session_values=None, cloud_values=None, project_dir=None):
    """Priority: per-session upload > process env > Cloud secrets > local key file.

    The local file is for class-style development only; it is not part of deployment.
    """
    local = read_local_key_file(project_dir)
    cloud = cloud_values or {}
    session = session_values or {}
    return {name: str(session.get(name) or os.getenv(name) or cloud.get(name) or local.get(name) or "")
            for name in ALLOWED_KEYS}
