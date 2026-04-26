"""최초 실행 시 API 키를 입력받아 .env 파일을 생성하는 설정 마법사."""
from __future__ import annotations

import os
import tkinter as tk
from pathlib import Path
from tkinter import messagebox


_ENV_PATH = Path.home() / ".narajangteo-pro" / ".env"


def _load_existing_key() -> str:
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            if line.startswith("NARA_API_KEY="):
                return line.split("=", 1)[1].strip()
    return ""


def _save_env(api_key: str) -> None:
    _ENV_PATH.parent.mkdir(parents=True, exist_ok=True)

    lines: list[str] = []
    if _ENV_PATH.exists():
        for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
            if not line.startswith("NARA_API_KEY="):
                lines.append(line)

    lines.insert(0, f"NARA_API_KEY={api_key}")
    _ENV_PATH.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_wizard() -> None:
    root = tk.Tk()
    root.title("나라장터 MCP — 초기 설정")
    root.resizable(False, False)

    # 창을 화면 중앙에 배치
    root.update_idletasks()
    w, h = 520, 300
    x = (root.winfo_screenwidth() - w) // 2
    y = (root.winfo_screenheight() - h) // 2
    root.geometry(f"{w}x{h}+{x}+{y}")

    frame = tk.Frame(root, padx=24, pady=20)
    frame.pack(fill="both", expand=True)

    tk.Label(
        frame,
        text="나라장터 MCP 서버 설정",
        font=("맑은 고딕", 14, "bold"),
    ).pack(anchor="w")

    tk.Label(
        frame,
        text=(
            "공공데이터포털(data.go.kr)에서 발급받은\n"
            "서비스키(Decoding 값)를 입력하세요."
        ),
        justify="left",
        fg="#555",
    ).pack(anchor="w", pady=(6, 14))

    tk.Label(frame, text="NARA_API_KEY", font=("맑은 고딕", 9, "bold")).pack(anchor="w")

    key_var = tk.StringVar(value=_load_existing_key())
    entry = tk.Entry(frame, textvariable=key_var, width=58, show="")
    entry.pack(fill="x", pady=(4, 4))
    entry.focus()

    hint = tk.Label(
        frame,
        text=f"저장 위치: {_ENV_PATH}",
        fg="#888",
        font=("맑은 고딕", 8),
    )
    hint.pack(anchor="w", pady=(0, 16))

    def on_save():
        key = key_var.get().strip()
        if not key:
            messagebox.showwarning("입력 필요", "서비스키를 입력해주세요.", parent=root)
            return
        _save_env(key)
        os.environ["NARA_API_KEY"] = key
        messagebox.showinfo("저장 완료", f"서비스키가 저장되었습니다.\n{_ENV_PATH}", parent=root)
        root.destroy()

    btn_frame = tk.Frame(frame)
    btn_frame.pack(fill="x")

    tk.Button(btn_frame, text="취소", width=10, command=root.destroy).pack(side="right", padx=(6, 0))
    tk.Button(
        btn_frame,
        text="저장",
        width=10,
        bg="#0066cc",
        fg="white",
        activebackground="#0052a3",
        activeforeground="white",
        command=on_save,
    ).pack(side="right")

    root.bind("<Return>", lambda _: on_save())
    root.mainloop()


def ensure_api_key() -> bool:
    """API 키가 없으면 설정 마법사를 실행한다. 키가 있으면 True를 반환."""
    # 이미 환경변수에 있으면 통과
    if os.getenv("NARA_API_KEY", "").strip():
        return True

    # ~/.narajangteo-pro/.env 에서 로드 시도
    if _ENV_PATH.exists():
        from dotenv import load_dotenv
        load_dotenv(_ENV_PATH)
        if os.getenv("NARA_API_KEY", "").strip():
            return True

    # 없으면 마법사 실행
    run_wizard()
    return bool(os.getenv("NARA_API_KEY", "").strip())


def main() -> None:
    run_wizard()


if __name__ == "__main__":
    main()
