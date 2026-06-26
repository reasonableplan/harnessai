#!/usr/bin/env python3
"""/ha-map — 독립 스킬 백엔드 (stdlib only).

skeleton.md → architecture.md(Mermaid) 파생 뷰 생성을 돕는 기계적 작업만 담당.
다이어그램 *생성* 자체는 SKILL.md 지시에 따라 Claude 가 skeleton 을 읽고 작성한다.
HarnessAI v2 상태기계에 의존하지 않는다 — 독립 실행.

서브커맨드:
  locate <project_dir>      : skeleton.md 위치 + docs_dir + mmdc 가용 여부 (JSON)
  render <architecture_md>  : ```mermaid 블록 추출 → mmdc 로 PNG 렌더 (JSON)
"""

from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):
    pass

_SKIP = {".git", ".venv", "node_modules", "__pycache__", ".ruff_cache"}


def _find_skeleton(root: Path) -> Path | None:
    direct = root / "docs" / "skeleton.md"
    if direct.is_file():
        return direct
    for p in sorted(root.glob("**/docs/skeleton.md")):
        if not any(part in _SKIP for part in p.parts):
            return p
    return None


def cmd_locate(args: argparse.Namespace) -> int:
    root = Path(args.project_dir).resolve()
    skeleton = _find_skeleton(root)
    out = {
        "found": skeleton is not None,
        "skeleton_path": str(skeleton) if skeleton else None,
        "docs_dir": str(skeleton.parent) if skeleton else str(root / "docs"),
        "mmdc_available": shutil.which("mmdc") is not None,
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out["found"] else 1


def _extract_mermaid_blocks(md_text: str) -> list[str]:
    """```mermaid 코드펜스 본문 추출. 펜스 줄끝은 LF/CRLF(Windows) 둘 다 허용."""
    return re.findall(r"```mermaid\r?\n(.*?)```", md_text, re.DOTALL)


def _render_one(mmdc: str, src: Path, png: Path) -> dict:
    cmd = [mmdc, "-i", str(src), "-o", str(png), "-b", "white", "-s", "2"]
    try:
        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except OSError:
            # Windows: mmdc 가 .cmd/.ps1 shim 이면 list 실행이 OSError → shell 로 재시도
            joined = " ".join(f'"{c}"' for c in cmd)
            r = subprocess.run(joined, shell=True, capture_output=True, text=True, timeout=180)
    except (subprocess.SubprocessError, OSError) as exc:
        # timeout 초과 등 subprocess 실패 — 렌더 루프를 죽이지 말고 실패로 보고
        return {"png": str(png), "ok": False, "error": str(exc)[-300:]}
    ok = r.returncode == 0 and png.is_file()
    return {"png": str(png), "ok": ok, "error": "" if ok else (r.stderr or r.stdout)[-300:]}


def cmd_render(args: argparse.Namespace) -> int:
    md = Path(args.architecture_md).resolve()
    if not md.is_file():
        print(json.dumps({"error": f"file not found: {md}"}, ensure_ascii=False))
        return 1
    mmdc = shutil.which("mmdc")
    if not mmdc:
        print(json.dumps({"mmdc_available": False, "rendered": []}, ensure_ascii=False))
        return 0

    blocks = _extract_mermaid_blocks(md.read_text(encoding="utf-8"))
    docs_dir = md.parent
    rendered = []
    for i, block in enumerate(blocks, 1):
        tmp = docs_dir / f".ha-map-tmp-{i}.mmd"
        png = docs_dir / f"architecture-{i}.png"
        try:
            tmp.write_text(block, encoding="utf-8")
            rendered.append(_render_one(mmdc, tmp, png))
        except OSError as exc:
            # tmp 쓰기 실패가 렌더 루프 전체를 죽이지 않도록 — 해당 블록만 실패로 기록
            rendered.append({"png": str(png), "ok": False, "error": str(exc)[-300:]})
        finally:
            tmp.unlink(missing_ok=True)
    print(json.dumps({"mmdc_available": True, "rendered": rendered}, ensure_ascii=False, indent=2))
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="/ha-map 백엔드")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_loc = sub.add_parser("locate")
    p_loc.add_argument("project_dir")
    p_loc.set_defaults(func=cmd_locate)
    p_ren = sub.add_parser("render")
    p_ren.add_argument("architecture_md")
    p_ren.set_defaults(func=cmd_render)
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
