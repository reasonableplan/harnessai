"""Docs Agent (Level 2) — README, 시스템 구성도, 기능 설명서 등 문서 작성 전담."""
from __future__ import annotations

import xml.sax.saxutils as saxutils
from typing import Any

from src.core.agent.base_code_generator import BaseCodeGeneratorAgent
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import AgentConfig

log = get_logger("DocsAgent")

# artifact 수집 시 허용할 문서 파일 확장자 (소스코드 수집 방지)
_DOC_EXTENSIONS = {".md", ".yaml", ".yml", ".txt", ".rst", ".json"}


class DocsAgent(BaseCodeGeneratorAgent):
    """문서 전담 에이전트.

    README, 시스템 구성도, 기능 설명서, API 문서 등 문서 파일 작성.
    소스코드(.py, .ts, .js 등) 생성/수정은 담당하지 않는다.
    """

    _role_description = (
        "You are a technical documentation specialist. "
        "Your ONLY job is to create and update documentation files: "
        "README.md, system architecture docs, feature guides, API docs, CONVENTIONS.md, etc. "
        "You do NOT write source code. You do NOT create .py, .ts, .tsx, .js, .jsx files. "
        "Documentation only. Follow existing project conventions and use Mermaid diagrams where appropriate."
    )

    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,
        llm_client: Any,
        work_dir: str = "./workspace",
        code_search: Any = None,
        memory_store: Any = None,
    ) -> None:
        super().__init__(
            config, message_bus, state_store, git_service, llm_client, work_dir,
            temperature=0.3, code_search=code_search, memory_store=memory_store,
        )

    def _build_workspace_instructions(self, task: Any, work_dir: str) -> str:
        """Docs 에이전트 전용 지시문 — 문서 파일 작성만 허용."""
        agent_id = self.id
        agent_md = f"docs/agents/{agent_id}.md"

        review_section = ""
        review_note = getattr(task, "review_note", None)
        retry_count = getattr(task, "retry_count", 0)
        if review_note and retry_count and retry_count > 0:
            review_section = (
                f"## ⚠️ 이전 리뷰 피드백 — 최우선 반영 필수\n"
                f"이 태스크는 **{retry_count}회 reject** 되었습니다.\n"
                f"아래 피드백의 **각 항목**을 하나씩 확인하고 수정하세요.\n\n"
                f"<review_feedback>\n{saxutils.escape(review_note)}\n</review_feedback>\n\n"
            )

        return (
            f"{self._role_description}\n\n"
            f"{review_section}"
            f"## 태스크\n"
            f"제목: {task.title}\n"
            f"설명: {task.description}\n\n"
            f"## 작업 순서\n\n"
            f"### Step 1: 기존 문서 읽기\n"
            f"다음 파일을 먼저 읽어 현재 상태를 파악하세요:\n"
            f"- docs/ARCHITECTURE.md — 현재 아키텍처\n"
            f"- docs/CONVENTIONS.md — 코딩 규칙\n"
            f"- docs/api-spec.md — API 계약\n"
            f"- docs/agents/SHARED_LESSONS.md — 과거 실수\n"
            f"- {agent_md} — 에이전트 전용 규칙\n\n"
            f"### Step 2: 코드 구조 파악 (읽기 전용 — 문서 내용 정확도를 위해)\n"
            f"- backend/app/main.py — 등록된 라우터 목록\n"
            f"- backend/app/models/ — 데이터 모델\n"
            f"- frontend/src/ — 프론트엔드 구조\n"
            f"- docker-compose.yml — 서비스 구성\n\n"
            f"### Step 3: 문서 파일 작성\n"
            f"태스크에서 요구하는 문서 파일만 작성하세요.\n"
            f"- 허용 파일 형식: .md, .yaml, .yml, .txt\n"
            f"- 태스크 설명에 명시된 경로에 정확히 작성\n\n"
            f"### Step 4: 검증\n"
            f"1. 요구한 파일이 모두 생성되었는지 확인\n"
            f"2. 파일 내용이 태스크 요구사항을 충족하는지 확인\n"
            f"3. Markdown 문법 오류 없는지 확인\n\n"
            f"## 절대 금지\n"
            f"- 소스 코드 파일(.py, .ts, .tsx, .js, .jsx, .css) 생성/수정\n"
            f"- 태스크에서 명시하지 않은 파일 생성\n"
            f"- workspace 밖 파일 수정\n"
            f"- .git/ 디렉토리 조작\n"
        )

    async def _collect_changed_files(
        self, work_dir: str, task_id: str, base_ref: str | None = None,
    ) -> list[str]:
        """문서 파일(.md, .yaml 등)만 수집한다. 소스코드는 무시."""
        all_files = await super()._collect_changed_files(work_dir, task_id, base_ref)
        doc_files = [
            f for f in all_files
            if any(f.lower().endswith(ext) for ext in _DOC_EXTENSIONS)
        ]
        skipped = len(all_files) - len(doc_files)
        if skipped > 0:
            log.warning(
                "Non-doc files skipped from artifacts",
                task_id=task_id, skipped=skipped,
                skipped_files=[f for f in all_files if f not in doc_files][:5],
            )
        return doc_files
