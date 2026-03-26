"""LLM으로 파일을 생성하는 에이전트의 공통 기반 클래스."""
from __future__ import annotations

import asyncio
import hashlib
import os
import uuid
import xml.sax.saxutils as saxutils
from pathlib import Path
from typing import Any

from src.core.agent.base_agent import BaseAgent
from src.core.errors import SandboxEscapeError
from src.core.messaging.message_bus import MessageBus
from src.core.state.state_store import StateStore
from src.core.types import AgentConfig, Task, TaskResult

MAX_TOKENS = 64_000
TOKEN_BUDGET = 100_000_000
_MAX_CONTEXT_CHARS = 40_000  # 워크스페이스 컨텍스트 최대 길이
_MAX_FILE_CHARS = 6_000      # 개별 파일 최대 읽기 길이
_MAX_ARTIFACT_CONTEXT_CHARS = 12_000  # 선행 산출물 컨텍스트 최대 길이

# 에이전트 도메인별 관심 파일 패턴
_DOMAIN_FILE_PATTERNS: dict[str, list[str]] = {
    "backend": [
        "**/*.py", "**/requirements.txt", "**/pyproject.toml",
        "**/alembic.ini", "**/docker-compose.yml",
    ],
    "frontend": [
        "**/*.ts", "**/*.tsx", "**/package.json", "**/tsconfig.json",
        "**/*.css", "**/vite.config.*",
    ],
    "git": [
        "**/docker-compose.yml", "**/Dockerfile", "**/.gitignore",
        "**/Makefile", "**/*.sh", "**/*.yml", "**/*.yaml",
    ],
    "docs": [
        "**/*.md", "**/*.py", "**/*.ts",  # 문서 작성 시 코드 참조
    ],
}

# 모든 에이전트가 참조해야 하는 공유 파일 패턴
_SHARED_PATTERNS = [
    "**/types/**", "**/models/**", "**/schemas/**",
    "**/domain.ts", "**/base.py", "**/config.py",
]

# 통합 핵심 파일 — 반드시 먼저 읽어야 하는 파일 (import 경로, DB 설정, 앱 구조)
_INTEGRATION_FILES = [
    "pyproject.toml", "package.json",
    "**/conftest.py", "**/database.py", "**/db.py",
    "**/app.py", "**/main.py", "**/config.py", "**/settings.py",
    "**/base.py", "**/models.py",
    "**/router.py", "**/routes.py", "**/urls.py",
]


class BaseCodeGeneratorAgent(BaseAgent):
    """LLM으로 파일을 생성하는 에이전트의 공통 로직.

    서브클래스는 _role_description만 설정하면 된다.
    """

    def __init__(
        self,
        config: AgentConfig,
        message_bus: MessageBus,
        state_store: StateStore,
        git_service: Any,
        llm_client: Any,
        work_dir: str = "./workspace",
        temperature: float = 0.2,
        code_search: Any = None,
        memory_store: Any = None,
    ) -> None:
        super().__init__(config, message_bus, state_store, git_service)
        self._llm = llm_client
        self._work_dir = Path(work_dir).resolve()
        self._temperature = temperature
        self._code_search = code_search
        self._memory_store = memory_store

    # 서브클래스에서 오버라이드할 role description
    _role_description: str = "You are a code generation assistant."

    def _build_prompt(
        self, task: Task, context: str = "", artifact_context: str = "",
    ) -> str:
        """공통 프롬프트 템플릿. 서브클래스는 _role_description만 설정하면 된다."""
        ctx_section = ""
        if context:
            ctx_section = (
                "\n## Existing codebase (follow these patterns and conventions)\n"
                "<existing_code>\n"
                f"{saxutils.escape(context)}\n"
                "</existing_code>\n\n"
                "CRITICAL RULES for integration:\n"
                "- Use EXACTLY the same import paths as existing files. Do NOT guess import paths.\n"
                "- Check the file tree to know what files exist before importing.\n"
                "- Match existing patterns: if conftest.py uses sync, use sync. If async, use async.\n"
                "- New files MUST be importable by existing tests and code without modification.\n"
                "- Follow the existing file structure and naming conventions exactly.\n\n"
            )

        # 선행 태스크 산출물 컨텍스트
        artifact_section = ""
        if artifact_context:
            artifact_section = (
                "\n## Previously Completed Tasks (MUST use these files — do NOT recreate them)\n"
                "<completed_artifacts>\n"
                f"{saxutils.escape(artifact_context)}\n"
                "</completed_artifacts>\n\n"
                "CRITICAL: These files ALREADY exist in the codebase. "
                "Import and use them directly. Do NOT redefine or duplicate their contents.\n\n"
            )

        # 공유 API 스펙 (백엔드/프론트 계약)
        api_spec_section = ""
        api_spec_path = os.path.join(self._git_service.work_dir, "docs", "api-spec.md")
        if os.path.isfile(api_spec_path):
            try:
                with open(api_spec_path, encoding="utf-8") as f:
                    api_spec = f.read()
                api_spec_section = (
                    "\n## API Specification (MUST follow this contract exactly)\n"
                    "<api_spec>\n"
                    f"{saxutils.escape(api_spec)}\n"
                    "</api_spec>\n\n"
                    "CRITICAL: All API endpoints, request/response formats, and type definitions "
                    "MUST match this specification exactly. Do NOT invent new endpoints or change field names.\n\n"
                )
            except OSError:
                pass

        # Director의 이전 리뷰 피드백 (reject 사유)
        feedback_section = ""
        review_note = getattr(task, "review_note", None)
        retry_count = getattr(task, "retry_count", 0)
        if review_note and retry_count and retry_count > 0:
            feedback_section = (
                f"\n## Previous Review Feedback (MUST address these issues)\n"
                f"This task was REJECTED {retry_count} time(s). Director's feedback:\n"
                f"<review_feedback>\n{saxutils.escape(review_note)}\n</review_feedback>\n"
                f"Fix ALL issues mentioned above before resubmitting.\n\n"
            )

        return (
            f"{self._role_description}\n\n"
            "## Rules (STRICT)\n"
            "1. **TDD**: Write tests FIRST, then implementation. Every file must have a corresponding test.\n"
            "2. **Architecture consistency**: Follow the existing codebase patterns exactly.\n"
            "3. **No magic values**: Use constants, config, or environment variables.\n"
            "4. **Type safety**: Full type annotations (Python: type hints, TypeScript: strict mode).\n"
            "5. **Error handling**: Never empty catch. Log errors, provide meaningful messages.\n"
            "6. **File naming**: Follow the existing naming conventions in the codebase.\n"
            "7. **BE CONCISE**: Keep code short and minimal. No docstrings, no comments unless complex logic. "
            "No boilerplate, no verbose error messages. Minimal imports. "
            "Generate FEWER files with LESS code. Quality over quantity. "
            "Empty marker files (py.typed, __init__.py, .gitkeep) MUST be included with empty content.\n\n"
            f"{feedback_section}"
            f"{api_spec_section}"
            f"{artifact_section}"
            'Respond with JSON: {"files": [{"path": str, "content": str, "action": str}], "summary": str}\n'
            "Include test files BEFORE implementation files in the array.\n"
            "CRITICAL: Every file MUST be COMPLETE. Never truncate code mid-function or mid-file. "
            "If output would be too long, generate FEWER files but ensure each one is 100% complete and runnable.\n\n"
            f"{ctx_section}"
            f"<task>\nTitle: {saxutils.escape(task.title)}\n"
            f"Description: {saxutils.escape(task.description)}\n</task>"
        )

    @property
    def _effective_work_dir(self) -> Path:
        """현재 활성 작업 디렉토리 — worktree가 있으면 worktree, 없으면 공유 workspace."""
        if self._active_worktree:
            return Path(self._active_worktree).resolve()
        return self._work_dir

    def _build_workspace_instructions(self, task: Task, work_dir: str) -> str:
        """Worker에게 전달할 자율 작업 지시문을 구성한다."""
        agent_id = self.id
        agent_md = f"docs/agents/{agent_id}.md"

        review_section = ""
        review_note = getattr(task, "review_note", None)
        retry_count = getattr(task, "retry_count", 0)
        if review_note and retry_count and retry_count > 0:
            review_section = (
                f"## ⚠️ 이전 리뷰 피드백 — 최우선 반영 필수\n"
                f"이 태스크는 **{retry_count}회 reject** 되었습니다.\n"
                f"아래 피드백의 **각 항목**을 하나씩 확인하고 수정하세요.\n"
                f"수정 전/후를 비교해서 확인하세요.\n\n"
                f"<review_feedback>\n{saxutils.escape(review_note)}\n</review_feedback>\n\n"
            )

        return (
            f"{self._role_description}\n\n"
            f"{review_section}"
            f"## 태스크\n"
            f"제목: {task.title}\n"
            f"설명: {task.description}\n\n"
            f"## 작업 순서 (반드시 따를 것)\n\n"
            f"### Step 1: 프로젝트 문서 읽기\n"
            f"다음 파일을 **반드시 첫 번째로** 읽고 규칙을 따르세요:\n"
            f"- docs/ARCHITECTURE.md — 파일 구조, import 경로, 현재 상태\n"
            f"- docs/CONVENTIONS.md — 코딩 규칙, 패턴\n"
            f"- docs/api-spec.md — API 계약 (엔드포인트, 타입)\n"
            f"- docs/agents/SHARED_LESSONS.md — 과거 실수, 금지사항\n"
            f"- {agent_md} — 에이전트 전용 규칙\n\n"
            f"### Step 2: 기존 코드 읽기\n"
            f"작업과 관련된 기존 파일을 읽어서 패턴을 파악하세요:\n"
            f"- backend/app/main.py — 현재 등록된 라우터\n"
            f"- backend/app/models/__init__.py — 사용 가능한 모델\n"
            f"- backend/app/database.py — DB 세션 패턴\n"
            f"- 기존 라우터/서비스/스키마가 있으면 패턴 참고\n\n"
            f"### Step 3: 코드 작성\n"
            f"- ARCHITECTURE.md와 CONVENTIONS.md 규칙을 따라 구현\n"
            f"- api-spec.md의 엔드포인트/타입과 정확히 일치\n"
            f"- 새 디렉토리 만들면 __init__.py 반드시 생성\n"
            f"- 새 라우터 만들면 main.py에 include_router() 추가\n\n"
            f"### Step 4: 자체 검증\n"
            f"코드 작성 후 반드시 실행해서 확인:\n"
            f"1. python -c \"from app.main import app\" — ImportError 없는지\n"
            f"2. ruff check backend/ --fix --config ruff.toml — lint 통과\n"
            f"3. 테스트 파일 작성 후 pytest 실행 — 통과 확인\n"
            f"4. 태스크 설명에 수락 기준이 있으면 각 기준을 하나씩 검증\n\n"
            f"### Step 5: 실패하면 직접 수정\n"
            f"위 검증에서 에러가 나면 스스로 원인을 찾아 수정하세요.\n"
            f"모든 검증을 통과할 때까지 반복하세요.\n\n"
            f"## 금지사항\n"
            f"- workspace 밖의 파일 수정 금지\n"
            f"- docs/ 파일 수정 금지 (읽기만)\n"
            f"- .git/ 디렉토리 직접 조작 금지\n"
        )

    async def execute_task(self, task: Task) -> TaskResult:
        """Claude Code CLI를 자율 개발자로 실행한다.

        JSON 생성 대신 workspace에서 직접 파일 읽기/쓰기/테스트/수정.
        """
        try:
            effective_dir = self._effective_work_dir
            instructions = self._build_workspace_instructions(task, str(effective_dir))

            # RAG: 관련 교훈 검색 → instructions 상단에 주입
            lessons_section = await self._get_relevant_lessons(task)
            if lessons_section:
                instructions = lessons_section + "\n\n" + instructions

            # Claude CLI 자율 실행 모드 시도
            from src.core.llm.claude_cli_client import ClaudeCliClient
            if isinstance(self._llm, ClaudeCliClient):
                result = await self._execute_autonomous(task, str(effective_dir), instructions)
                if not result.success:
                    self._log.warning(
                        "CLI mode failed, falling back to JSON mode",
                        task_id=task.id,
                    )
                    # CLI가 남긴 불완전한 파일 정리 후 fallback
                    await self._reset_working_tree(str(effective_dir))
                    return await self._execute_json_mode(task, effective_dir)
                return result

            # fallback: API 클라이언트 → 기존 JSON 생성 방식
            return await self._execute_json_mode(task, effective_dir)

        except SandboxEscapeError as e:
            self._log.error(
                "SECURITY: sandbox escape attempted",
                task_id=task.id, path=e.path, sandbox=e.sandbox,
            )
            return TaskResult(
                success=False,
                error={"message": "Security violation: path outside workspace"},
                artifacts=[],
            )
        except Exception as e:
            self._log.error("Task execution failed", task_id=task.id, err=str(e))
            return TaskResult(
                success=False,
                error={"message": f"Task execution failed: {type(e).__name__}: {e}"},
                artifacts=[],
            )

    async def _execute_autonomous(
        self, task: Task, work_dir: str, instructions: str,
    ) -> TaskResult:
        """Claude Code CLI를 자율 개발자로 실행 — 파일 읽기/쓰기/테스트/수정."""
        from src.core.llm.claude_cli_client import ClaudeCliClient
        cli: ClaudeCliClient = self._llm

        # CLI timeout = agent timeout - 60s (파일 수집/후처리 여유)
        agent_timeout_s = (self.config.task_timeout_ms or 360_000) / 1000
        cli_timeout = max(agent_timeout_s - 60, 60)

        # CLI 실행 전 HEAD SHA 저장 (CLI가 자동 커밋해도 diff 가능)
        saved_head = await self._get_current_head(work_dir)

        await self._publish_progress(task.id, "reading_docs", "문서 읽기 및 코드 작성 시작")

        success, output = await cli.execute_in_workspace(
            work_dir, instructions, timeout=cli_timeout,
        )

        # CLI 출력을 task_log에 저장 (실패/성공 모두 — 관측성 확보)
        try:
            await self._state_store.update_task_log_text(task.id, output[-5000:])
        except Exception:
            pass  # 로그 저장 실패는 메인 플로우 차단 금지

        if not success:
            self._log.warning("Autonomous execution failed", task_id=task.id, output=output[:500])
            return TaskResult(
                success=False,
                error={"message": output[:500]},
                artifacts=[],
            )

        await self._publish_progress(task.id, "collecting", "변경 파일 수집 중")

        # 성공: 변경된 파일 수집 (saved_head 기준 diff로 감지)
        artifact_paths = await self._collect_changed_files(
            work_dir, task.id, base_ref=saved_head,
        )
        self._log.info("Autonomous task complete", task_id=task.id, files=len(artifact_paths))
        await self._publish_progress(task.id, "done", f"완료 — {len(artifact_paths)}개 파일")
        return TaskResult(
            success=True,
            data={"files": artifact_paths, "summary": output[-1000:]},
            artifacts=artifact_paths,
        )

    @staticmethod
    async def _get_current_head(work_dir: str) -> str | None:
        """현재 HEAD의 SHA를 반환한다. 실패 시 None."""
        try:
            proc = await asyncio.create_subprocess_exec(
                "git", "rev-parse", "HEAD",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            if proc.returncode == 0:
                return stdout.decode().strip()
        except Exception:
            pass
        return None

    async def _collect_changed_files(
        self, work_dir: str, task_id: str, base_ref: str | None = None,
    ) -> list[str]:
        """git diff로 변경된 파일을 수집하고 artifact로 등록한다.

        base_ref가 주어지면 해당 커밋 이후 변경사항을 감지한다
        (CLI가 자동 커밋한 경우에도 누락 방지).
        """
        try:
            # 커밋 간 diff + 워킹 트리 diff + untracked 모두 수집
            stdout_parts: list[bytes] = []

            if base_ref:
                # 1. 커밋 간 diff (CLI가 자동 커밋한 파일)
                proc_committed = await asyncio.create_subprocess_exec(
                    "git", "diff", "--name-only", "--diff-filter=ACMR", f"{base_ref}..HEAD",
                    cwd=work_dir,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                out, _ = await proc_committed.communicate()
                stdout_parts.append(out)

            # 2. 워킹 트리 변경 (커밋 안 된 수정사항)
            proc = await asyncio.create_subprocess_exec(
                "git", "diff", "--name-only", "--diff-filter=ACMR", "HEAD",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, _ = await proc.communicate()
            stdout_parts.append(stdout)

            # 3. untracked 파일도 포함
            proc2 = await asyncio.create_subprocess_exec(
                "git", "ls-files", "--others", "--exclude-standard",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout2, _ = await proc2.communicate()
            stdout_parts.append(stdout2)

            changed = set()
            combined = b"".join(stdout_parts).decode()
            for line in combined.strip().split("\n"):
                line = line.strip()
                if line:
                    changed.add(line)

            artifact_paths: list[str] = []
            work_dir_path = Path(work_dir).resolve()
            for rel_path in changed:
                # sandbox escape 검증
                try:
                    resolved = (work_dir_path / rel_path).resolve()
                    if not resolved.is_relative_to(work_dir_path):
                        self._log.warning("Sandbox escape in changed file, skipping", path=rel_path)
                        continue
                except (ValueError, OSError):
                    continue
                abs_path = str(resolved)
                if not os.path.isfile(abs_path):
                    continue
                try:
                    content = Path(abs_path).read_text(encoding="utf-8", errors="replace")
                    await self._state_store.save_artifact({
                        "id": str(uuid.uuid4()),
                        "task_id": task_id,
                        "file_path": abs_path,
                        "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                        "created_by": self.id,
                    })
                    artifact_paths.append(abs_path)
                except Exception as e:
                    self._log.warning("Failed to save artifact", path=rel_path, err=str(e))
                    artifact_paths.append(abs_path)  # 파일은 존재하므로 경로는 반환
            return artifact_paths
        except Exception as e:
            self._log.warning("Failed to collect changed files", err=str(e))
            return []

    @staticmethod
    async def _reset_working_tree(work_dir: str) -> None:
        """CLI fallback 전 불완전한 변경사항을 정리한다."""
        try:
            # 변경된 tracked 파일 복원
            proc = await asyncio.create_subprocess_exec(
                "git", "checkout", ".",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc.communicate()
            # untracked 파일 삭제
            proc2 = await asyncio.create_subprocess_exec(
                "git", "clean", "-fd",
                cwd=work_dir,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            await proc2.communicate()
        except Exception:
            pass  # 정리 실패해도 fallback은 시도

    async def _get_relevant_lessons(self, task: Task) -> str:
        """RAG로 태스크 관련 교훈을 검색하여 프롬프트 섹션으로 반환한다."""
        if not self._memory_store:
            return ""
        try:
            query = f"{task.title} {task.description or ''}"
            lessons = await self._memory_store.search_lessons(query, top_k=5, min_score=0.3)
            if not lessons:
                return ""
            items = "\n".join(f"- {saxutils.escape(lesson)}" for lesson in lessons)
            return (
                "## 관련 과거 교훈 (반드시 참고)\n"
                f"{items}\n"
            )
        except Exception as e:
            self._log.warning("Lessons search failed", err=str(e))
            return ""

    async def _execute_json_mode(self, task: Task, effective_dir: Path) -> TaskResult:
        """기존 JSON 생성 방식 (API 클라이언트 fallback).

        Raises SandboxEscapeError to caller for security violations.
        """
        context = await self._search_codebase(task)
        if not context:
            context = await self._scan_workspace_context(task)
        artifact_context = await self._collect_artifact_context(task)
        prompt = self._build_prompt(task, context=context, artifact_context=artifact_context)

        data, input_tokens, output_tokens = await self._llm.chat_json(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=MAX_TOKENS,
            temperature=self._temperature,
            token_budget=TOKEN_BUDGET,
        )
        await self._publish_token_usage(input_tokens, output_tokens)

        files = data.get("files", []) if isinstance(data, dict) else []
        artifact_paths: list[str] = []

        truncated_files = []
        for f in files:
            content = f.get("content", "")
            if content and self._is_likely_truncated(content, f.get("path", "")):
                truncated_files.append(f.get("path", "unknown"))
        if truncated_files:
            return TaskResult(
                success=False,
                error={"message": f"LLM output truncated: {', '.join(truncated_files)}. Retry with fewer files."},
                artifacts=[],
            )

        for f in files:
            path = f.get("path", "")
            content = f.get("content", "")
            if not path or not content:
                continue
            abs_path = self._safe_resolve(path, effective_dir)
            abs_path.parent.mkdir(parents=True, exist_ok=True)
            await asyncio.to_thread(abs_path.write_text, content, "utf-8")
            await self._state_store.save_artifact({
                "id": str(uuid.uuid4()),
                "task_id": task.id,
                "file_path": str(abs_path),
                "content_hash": hashlib.sha256(content.encode()).hexdigest(),
                "created_by": self.id,
            })
            artifact_paths.append(str(abs_path))

        summary = data.get("summary", "") if isinstance(data, dict) else ""
        return TaskResult(
            success=True,
            data={"files": artifact_paths, "summary": summary},
            artifacts=artifact_paths,
        )

    async def _search_codebase(self, task: Task) -> str:
        """RAG: 태스크와 관련된 기존 코드를 검색한다."""
        if not self._code_search:
            return ""
        try:
            query = f"{task.title} {task.description or ''}"
            return await self._code_search.search_formatted(query, top_k=5, min_score=0.3)
        except Exception as e:
            self._log.warning("Code search failed, falling back to workspace scan", err=str(e))
            return ""

    async def _scan_workspace_context(self, task: Task) -> str:
        """workspace 디렉토리의 기존 파일을 스캔하여 컨텍스트로 반환한다.

        3단계로 컨텍스트를 구성:
        1. 전체 파일 트리 (구조 파악)
        2. 통합 핵심 파일 (import 경로, DB, 앱 구조 — 반드시 포함)
        3. 도메인별 + 공유 패턴 파일 (남은 예산으로)
        """
        scan_dir = self._effective_work_dir
        if not scan_dir.exists():
            return ""

        # ---- Phase 1: 전체 파일 트리 ----
        all_files: list[str] = []
        skip_dirs = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".worktrees"}
        skip_exts = {".pyc", ".pyo", ".png", ".jpg", ".ico", ".woff", ".lock", ".egg-info"}
        for file_path in sorted(scan_dir.rglob("*")):
            if not file_path.is_file():
                continue
            if any(d in file_path.parts for d in skip_dirs):
                continue
            if file_path.suffix in skip_exts:
                continue
            all_files.append(str(file_path.relative_to(scan_dir)))

        tree_section = "## Project File Tree\n```\n" + "\n".join(all_files) + "\n```\n"
        total_chars = len(tree_section)

        # ---- Phase 2: 통합 핵심 파일 (반드시 포함) ----
        collected_files: dict[str, str] = {}

        for pattern in _INTEGRATION_FILES:
            for file_path in sorted(scan_dir.glob(pattern)):
                if not file_path.is_file() or file_path.stat().st_size > 50_000:
                    continue
                rel = str(file_path.relative_to(scan_dir))
                if rel in collected_files:
                    continue
                if any(d in file_path.parts for d in skip_dirs):
                    continue
                try:
                    content = await asyncio.to_thread(file_path.read_text, "utf-8", "replace")
                    truncated = content[:_MAX_FILE_CHARS]
                    collected_files[rel] = truncated
                    total_chars += len(truncated)
                except Exception:
                    continue

        # ---- Phase 3: 도메인별 + 공유 파일 (남은 예산으로) ----
        patterns = list(_SHARED_PATTERNS)
        domain_patterns = _DOMAIN_FILE_PATTERNS.get(self.domain, [])
        patterns.extend(domain_patterns)

        for pattern in patterns:
            if total_chars >= _MAX_CONTEXT_CHARS:
                break
            for file_path in sorted(scan_dir.glob(pattern)):
                if not file_path.is_file():
                    continue
                rel = str(file_path.relative_to(scan_dir))
                if rel in collected_files:
                    continue
                if file_path.suffix in skip_exts:
                    continue
                if any(d in file_path.parts for d in skip_dirs):
                    continue
                if file_path.stat().st_size > 50_000:
                    continue
                try:
                    content = await asyncio.to_thread(file_path.read_text, "utf-8", "replace")
                    truncated = content[:_MAX_FILE_CHARS]
                    if total_chars + len(truncated) > _MAX_CONTEXT_CHARS:
                        break
                    collected_files[rel] = truncated
                    total_chars += len(truncated)
                except Exception:
                    continue

        # ---- 조합 ----
        parts = [tree_section]
        if collected_files:
            parts.append("## Key Files (MUST follow these patterns for imports and structure)")
            for rel_path, content in collected_files.items():
                parts.append(f"### {rel_path}\n```\n{content}\n```")

        self._log.info("Workspace context loaded",
                       files=len(collected_files), chars=total_chars)
        return "\n\n".join(parts)

    @staticmethod
    def _is_likely_truncated(content: str, path: str) -> bool:
        """파일 내용이 잘렸을 가능성이 높은지 휴리스틱으로 판단한다."""
        stripped = content.rstrip()
        if not stripped:
            return False

        # Python 파일: 열린 괄호/중괄호가 닫히지 않은 경우
        if path.endswith(".py"):
            opens = stripped.count("(") + stripped.count("{") + stripped.count("[")
            closes = stripped.count(")") + stripped.count("}") + stripped.count("]")
            if opens - closes >= 3:
                return True

        # TypeScript/JS: 중괄호 불균형
        if path.endswith((".ts", ".tsx", ".js", ".jsx")):
            opens = stripped.count("{") + stripped.count("(")
            closes = stripped.count("}") + stripped.count(")")
            if opens - closes >= 3:
                return True

        # 일반: 코드가 키워드 중간에서 끊긴 경우 (YAML/config 파일은 제외)
        if not path.endswith((".yml", ".yaml", ".toml", ".ini", ".cfg", ".json")):
            last_line = stripped.split("\n")[-1].rstrip()
            if last_line.endswith((",", ":", "->", "=>", "=")):
                return True

        return False

    async def _collect_artifact_context(self, task: Task) -> str:
        """에픽 내 완료된 선행 태스크의 산출물을 읽어 컨텍스트 문자열로 반환한다.

        - 에픽이 없는 독립 태스크는 빈 문자열 반환
        - 파일 내용 직접 포함 (12,000자 제한)
        - 핵심 파일 우선 (models, config, schemas 등)
        """
        epic_id = getattr(task, "epic_id", None)
        if not epic_id:
            return ""

        try:
            artifacts = await self._state_store.get_completed_artifacts_for_epic(epic_id)
        except Exception as e:
            self._log.warning("Failed to load artifact context", err=str(e))
            return ""

        if not artifacts:
            return ""

        # 핵심 파일 우선 정렬 (models, config, schemas, base → 기타)
        priority_keywords = ("model", "schema", "config", "base", "type", "database", "db")

        def sort_key(art: Any) -> tuple[int, str]:
            fpath = art.file_path if hasattr(art, "file_path") else str(art)
            basename = fpath.rsplit("/", 1)[-1].rsplit("\\", 1)[-1].lower()
            is_priority = any(kw in basename for kw in priority_keywords)
            return (0 if is_priority else 1, fpath)

        sorted_artifacts = sorted(artifacts, key=sort_key)

        parts: list[str] = []
        total_chars = 0

        for art in sorted_artifacts:
            if total_chars >= _MAX_ARTIFACT_CONTEXT_CHARS:
                break

            fpath = art.file_path if hasattr(art, "file_path") else str(art)
            try:
                content = await asyncio.to_thread(
                    Path(fpath).read_text, "utf-8", "replace",
                )
            except Exception:
                # 파일 삭제/이동된 경우 graceful 처리
                parts.append(f"### {fpath}\n(파일 읽기 실패 — 삭제/이동됨)")
                continue

            remaining = _MAX_ARTIFACT_CONTEXT_CHARS - total_chars
            truncated = content[:min(len(content), remaining, _MAX_FILE_CHARS)]
            suffix = " (truncated)" if len(truncated) < len(content) else ""
            parts.append(f"### {fpath}{suffix}\n```\n{truncated}\n```")
            total_chars += len(truncated)

        if not parts:
            return ""

        self._log.info("Artifact context collected",
                       epic_id=epic_id, files=len(parts), chars=total_chars)
        return "\n\n".join(parts)

    def _safe_resolve(self, rel_path: str, base_dir: Path | None = None) -> Path:
        """Sandbox escape 방지: work_dir 밖 경로 차단."""
        target = base_dir or self._work_dir
        resolved = (target / rel_path).resolve()
        if not resolved.is_relative_to(target):
            raise SandboxEscapeError(rel_path, str(target))
        return resolved
