"""pytest 공통 설정."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "src"))

# server.py가 import 시 Settings.load()를 호출하므로 플레이스홀더를 주입한다.
# 실제 API 호출 테스트는 환경변수에 진짜 NARA_API_KEY가 있어야 실행된다.
os.environ.setdefault("NARA_API_KEY", "placeholder-replace-with-real-key")
