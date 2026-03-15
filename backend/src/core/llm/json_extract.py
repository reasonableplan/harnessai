"""Claude 응답에서 JSON을 견고하게 추출하는 유틸."""
from __future__ import annotations

import json
import re


def parse_json_response(text: str) -> dict | list:
    """
    Claude 응답 텍스트에서 JSON을 추출한다.
    ```json ... ``` 블록 → raw JSON → 전체 텍스트 순서로 시도.
    """
    # 1. ```json ... ``` 코드 블록
    match = re.search(r"```(?:json)?\s*([\s\S]*?)```", text)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except json.JSONDecodeError:
            pass

    # 2. 첫 번째 { 또는 [ 부터 파싱 시도
    for start_char, end_char in (("{", "}"), ("[", "]")):
        start = text.find(start_char)
        if start == -1:
            continue
        # 마지막 닫는 괄호까지
        end = text.rfind(end_char)
        if end <= start:
            continue
        try:
            return json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            continue

    # 3. 전체 텍스트
    try:
        return json.loads(text.strip())
    except json.JSONDecodeError:
        raise ValueError(f"No valid JSON found in response: {text[:200]!r}")
