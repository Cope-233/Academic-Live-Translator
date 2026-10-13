from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
os.environ.setdefault("ALT_DATA_DIR", str(ROOT / "data"))
os.environ.setdefault("ALT_MODELS_DIR", str(ROOT / "models"))
os.environ.setdefault("ALT_CACHE_DIR", str(ROOT / "cache"))
os.environ.setdefault("ALT_LOGS_DIR", str(ROOT / "logs"))
os.environ.setdefault("HF_HOME", str(ROOT / "cache" / "huggingface"))
os.environ.setdefault("PIP_CACHE_DIR", str(ROOT / "cache" / "pip"))
os.environ.setdefault("TMPDIR", str(ROOT / "cache" / "temp"))
os.environ.setdefault("TEMP", str(ROOT / "cache" / "temp"))
os.environ.setdefault("TMP", str(ROOT / "cache" / "temp"))

import uvicorn
from app.webapp import app

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765, reload=False)
