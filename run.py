import sys
from pathlib import Path

from streamlit.web import cli as stcli

import openai  # noqa: F401  只为让 PyInstaller 把 web.py 用到的 openai 一起打进去

_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
_SCRIPT = str(_BASE / "web.py")

if __name__ == "__main__":
    sys.argv = [
        "streamlit", "run", _SCRIPT,
        "--global.developmentMode=false",   # 不加这个 streamlit 会拒绝 server.port 参数
        "--server.port=8501",
        "--server.headless=false",
        "--browser.gatherUsageStats=false",
        *sys.argv[1:],
    ]
    sys.exit(stcli.main())
