"""시스템 컨텍스트 초기화 및 부트스트랩."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.core.types import AgentConfig

from src.core.board.board_watcher import BoardWatcher
from src.core.config import AppConfig
from src.core.db.session import close_engine, create_engine, get_session_factory
from src.core.git_service.git_service import GitService
from src.core.hooks.builtin_hooks import register_builtin_hooks
from src.core.hooks.hook_registry import HookRegistry
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
from src.core.git_service.merge_queue import MergeQueue
from src.core.resilience.orphan_cleaner import OrphanCleaner
from src.core.state.state_store import StateStore

log = get_logger("Bootstrap")

_system_context: SystemContext | None = None


@dataclass
class SystemContext:
    config: AppConfig
    state_store: StateStore
    message_bus: MessageBus
    git_service: GitService
    board_watcher: BoardWatcher
    hook_registry: HookRegistry
    orphan_cleaner: OrphanCleaner
    agents: list[Any] = field(default_factory=list)
    llm_clients: list[Any] = field(default_factory=list)
    merge_queue: MergeQueue | None = None


async def bootstrap(config: AppConfig) -> SystemContext:
    """전체 시스템을 초기화하고 SystemContext를 반환한다."""
    global _system_context, _shutting_down
    _shutting_down = False  # 재부트스트랩 허용 (테스트/hot-reload)

    log.info("Bootstrapping system...")

    # 1. DB 연결
    create_engine(config.database_url)
    session_factory = get_session_factory()
    state_store = StateStore(session_factory)

    # 2. MessageBus
    message_bus = MessageBus(state_store)

    # 3. GitService + Workspace 초기화
    git_service = GitService(config)
    await git_service.validate_connection()
    await git_service.init_workspace()

    # 4. BoardWatcher
    board_watcher = BoardWatcher(git_service, state_store, message_bus)

    # 5. HookRegistry + 내장 훅 등록
    hook_registry = HookRegistry(state_store)
    await register_builtin_hooks(hook_registry, state_store)

    # 6. OrphanCleaner
    orphan_cleaner = OrphanCleaner(state_store, git_service)

    # 7. RAG — 코드베이스 인덱싱 + 메모리
    code_search, memory_store = await _init_rag(config)

    # 7.5. 머지 큐 생성 (Director가 사용) — test_runner는 Director 생성 후 설정
    merge_queue_instance: MergeQueue | None = None

    # 7.6. orphan worktree 정리 (이전 세션 잔여물)
    await git_service.cleanup_orphan_worktrees()

    # 8. 에이전트 생성 (에이전트별 LLM 클라이언트 포함)
    agents, agent_llm_clients = _create_agents(
        config, message_bus, state_store, git_service, code_search, memory_store,
    )

    # 8.5. 머지 큐 초기화 (Director를 test_runner로 사용)
    from src.agents.director.director_agent import DirectorAgent
    for agent in agents:
        if isinstance(agent, DirectorAgent):
            merge_queue_instance = MergeQueue(
                git_ops=git_service,
                test_runner=agent,
            )
            merge_queue_instance.start()
            agent._merge_queue = merge_queue_instance
            # 플랜 복원 (서버 재시작 시 이전 세션 이어가기)
            await agent.restore_plan_from_db()
            break

    # 8.6. 서버 재시작 시 자동 복구 — 수동 개입 없이 작업 재개
    await _auto_recover_tasks(state_store)

    # 9. 에이전트 DB 등록 (병렬, 개별 실패 허용)
    results = await asyncio.gather(*(
        state_store.register_agent({
            "id": agent.id,
            "domain": agent.domain,
            "level": agent.config.level.value,
            "status": "idle",
        })
        for agent in agents
    ), return_exceptions=True)
    failures = []
    for agent, result in zip(agents, results):
        if isinstance(result, Exception):
            log.error("Agent registration failed", agent=agent.id, err=str(result))
            failures.append(agent.id)
    if len(failures) == len(agents):
        raise RuntimeError(f"All {len(failures)} agent registrations failed: {failures}")

    ctx = SystemContext(
        config=config,
        state_store=state_store,
        message_bus=message_bus,
        git_service=git_service,
        board_watcher=board_watcher,
        hook_registry=hook_registry,
        orphan_cleaner=orphan_cleaner,
        agents=agents,
        llm_clients=agent_llm_clients,
        merge_queue=merge_queue_instance,
    )
    _system_context = ctx
    log.info("Bootstrap complete", agent_count=len(agents))
    return ctx


def _create_llm_client(config: AppConfig) -> Any:
    """글로벌 LLM 클라이언트 (에이전트별 설정이 없을 때 폴백용)."""
    if config.use_local_model:
        from src.core.llm.local_model_client import LocalModelClient
        return LocalModelClient(
            base_url=config.local_model_base_url,
            model=config.local_model_name,
            api_key=config.local_model_api_key,
        )
    if config.use_cli:
        from src.core.llm.claude_cli_client import ClaudeCliClient
        log.info("LLM backend: claude CLI subprocess")
        return ClaudeCliClient()
    from src.core.llm.claude_client import ClaudeClient
    log.info("LLM backend: Anthropic API")
    return ClaudeClient(api_key=config.anthropic_api_key)


# 에이전트별 기본 모델 매핑 (Director=Opus, B/F=Sonnet, 나머지=Haiku)
_DEFAULT_AGENT_MODELS: dict[str, str] = {
    "director": "claude-opus-4-6",
    "agent-backend": "claude-sonnet-4-6",
    "agent-frontend": "claude-sonnet-4-6",
    "agent-git": "claude-haiku-4-5-20251001",
    "agent-docs": "claude-haiku-4-5-20251001",
}


def _create_agent_llm_client(agent_config: "AgentConfig", app_config: AppConfig) -> Any:
    """에이전트별 LLM 클라이언트를 생성한다.

    agent_config.llm_provider가 설정되면 해당 provider를 사용하고,
    비어있으면 글로벌 설정(AppConfig)에 따라 backend를 선택한다.
    어느 경우든 agent_config.claude_model이 기본 모델로 사용된다.
    """
    provider = agent_config.llm_provider

    # 명시적 provider: openai-compat (GPT, Gemini, Ollama 등)
    if provider == "openai-compat":
        from src.core.llm.local_model_client import LocalModelClient
        log.info("LLM backend: openai-compat", agent=agent_config.id, model=agent_config.claude_model)
        return LocalModelClient(
            base_url=agent_config.llm_base_url,
            model=agent_config.claude_model,
            api_key=agent_config.llm_api_key or None,
        )

    # 명시적 provider: claude-cli
    if provider == "claude-cli":
        from src.core.llm.claude_cli_client import ClaudeCliClient
        log.info("LLM backend: claude CLI", agent=agent_config.id)
        return ClaudeCliClient()

    # 명시적 provider: anthropic API
    if provider == "anthropic":
        from src.core.llm.claude_client import ClaudeClient
        log.info("LLM backend: Anthropic API", agent=agent_config.id, model=agent_config.claude_model)
        return ClaudeClient(api_key=app_config.anthropic_api_key, default_model=agent_config.claude_model)

    # provider 미지정 → 글로벌 설정으로 backend 선택, 모델은 에이전트별
    if app_config.use_local_model:
        from src.core.llm.local_model_client import LocalModelClient
        return LocalModelClient(
            base_url=app_config.local_model_base_url,
            model=agent_config.claude_model,
            api_key=app_config.local_model_api_key,
        )
    if app_config.use_cli:
        from src.core.llm.claude_cli_client import ClaudeCliClient
        return ClaudeCliClient()

    from src.core.llm.claude_client import ClaudeClient
    log.info("LLM backend: Anthropic API", agent=agent_config.id, model=agent_config.claude_model)
    return ClaudeClient(api_key=app_config.anthropic_api_key, default_model=agent_config.claude_model)


async def _init_rag(config: AppConfig) -> tuple[Any, Any]:
    """RAG + 메모리를 초기화한다. 실패해도 시스템은 계속 동작한다."""
    try:
        from pathlib import Path

        from qdrant_client import QdrantClient

        from src.core.memory.memory_store import MemoryStore
        from src.core.rag.indexer import CodebaseIndexer
        from src.core.rag.search import CodeSearchService

        # Qdrant in-memory (프로덕션에서는 외부 Qdrant 서버로 교체)
        qdrant = QdrantClient(":memory:")

        # fastembed 임베딩 함수 (GPU 가능하면 CUDA, 아니면 CPU fallback)
        from fastembed import TextEmbedding
        try:
            embed_model = TextEmbedding(
                model_name="BAAI/bge-small-en-v1.5",
                providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
            )
            log.info("fastembed using GPU (CUDA)")
        except Exception:
            embed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
            log.info("fastembed using CPU")
        embedding_fn = embed_model.embed

        # 코드베이스 인덱싱
        indexer = CodebaseIndexer(qdrant, embedding_fn)
        work_dir = Path(config.git_work_dir).resolve()
        if work_dir.exists():
            count = await indexer.index_workspace(work_dir)
            log.info("RAG codebase indexed", chunks=count, work_dir=str(work_dir))

        # 메모리 스토어 초기화
        memory_store = MemoryStore(qdrant, embedding_fn)
        await memory_store.ensure_collection()
        log.info("Memory store initialized")

        return CodeSearchService(qdrant, embedding_fn), memory_store
    except Exception as e:
        log.warning("RAG initialization failed, proceeding without code search", err=str(e))
        return None, None


def _create_agents(
    config: AppConfig,
    message_bus: MessageBus,
    state_store: StateStore,
    git_service: GitService,
    code_search: Any = None,
    memory_store: Any = None,
    merge_queue: MergeQueue | None = None,
) -> tuple[list[Any], list[Any]]:
    """에이전트와 에이전트별 LLM 클라이언트를 생성한다.

    Returns: (agents, llm_clients) — llm_clients는 shutdown 시 close용.
    """
    from src.agents.backend_agent.backend_agent import BackendAgent
    from src.agents.director.director_agent import DirectorAgent
    from src.agents.docs.docs_agent import DocsAgent
    from src.agents.frontend.frontend_agent import FrontendAgent
    from src.agents.git.git_agent import GitAgent
    from src.core.types import AgentConfig, AgentLevel

    work_dir = config.git_work_dir
    llm_clients: list[Any] = []

    def make_config(agent_id: str, domain: str, level: AgentLevel, **kwargs) -> AgentConfig:
        model = _DEFAULT_AGENT_MODELS.get(agent_id, "claude-sonnet-4-6")
        return AgentConfig(id=agent_id, domain=domain, level=level, claude_model=model, **kwargs)

    def make_llm(agent_cfg: AgentConfig) -> Any:
        client = _create_agent_llm_client(agent_cfg, config)
        llm_clients.append(client)
        return client

    director_cfg = make_config("director", "director", AgentLevel.DIRECTOR)
    director = DirectorAgent(
        config=director_cfg,
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=make_llm(director_cfg),
        memory_store=memory_store,
        merge_queue=merge_queue,
    )

    git_cfg = make_config("agent-git", "git", AgentLevel.WORKER)
    git_agent = GitAgent(
        config=git_cfg,
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=make_llm(git_cfg),
        work_dir=work_dir,
        code_search=code_search,
    )

    backend_cfg = make_config("agent-backend", "backend", AgentLevel.WORKER, temperature=0.2)
    backend = BackendAgent(
        config=backend_cfg,
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=make_llm(backend_cfg),
        work_dir=work_dir,
        code_search=code_search,
    )

    frontend_cfg = make_config("agent-frontend", "frontend", AgentLevel.WORKER, temperature=0.2)
    frontend = FrontendAgent(
        config=frontend_cfg,
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=make_llm(frontend_cfg),
        work_dir=work_dir,
        code_search=code_search,
    )

    docs_cfg = make_config("agent-docs", "docs", AgentLevel.WORKER, temperature=0.3)
    docs = DocsAgent(
        config=docs_cfg,
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=make_llm(docs_cfg),
        work_dir=work_dir,
        code_search=code_search,
    )

    log.info(
        "Agent LLM models configured",
        models={aid: _DEFAULT_AGENT_MODELS.get(aid, "sonnet") for aid in
                ["director", "agent-backend", "agent-frontend", "agent-git", "agent-docs"]},
    )
    return [director, git_agent, backend, frontend, docs], llm_clients


async def _auto_recover_tasks(state_store: StateStore) -> None:
    """서버 재시작 시 고아 태스크 복구 + 의존성 자동 해제.

    1. in-progress/review 태스크 → ready (에이전트가 없으므로 재작업)
    2. done 태스크 기반으로 backlog 의존성 해제 → ready
    """
    try:
        all_tasks = await state_store.get_all_tasks()
        if not all_tasks:
            return

        # Step 1: 고아 태스크 복구 (in-progress/review → ready)
        orphan_count = 0
        for t in all_tasks:
            if t.status in ("in-progress", "review"):
                await state_store.update_task(t.id, {
                    "status": "ready", "board_column": "Ready",
                })
                orphan_count += 1

        # Step 2: 의존성 자동 해제 (backlog → ready)
        done_ids = {t.id for t in all_tasks if t.status == "done"}
        unlock_count = 0
        # 복구 후 최신 상태로 다시 조회
        all_tasks = await state_store.get_all_tasks()
        for t in all_tasks:
            if t.status != "backlog":
                continue
            deps = t.dependencies or []
            if deps and all(d in done_ids for d in deps):
                await state_store.update_task(t.id, {
                    "status": "ready", "board_column": "Ready",
                })
                unlock_count += 1

        if orphan_count or unlock_count:
            log.info("Auto-recovery complete",
                     orphans_reset=orphan_count, deps_unlocked=unlock_count)
    except Exception as e:
        log.warning("Auto-recovery failed, continuing", err=str(e))


_shutting_down = False


async def shutdown(ctx: SystemContext) -> None:
    """Graceful shutdown — 에이전트 drain → watcher → DB."""
    global _shutting_down, _system_context
    if _shutting_down:
        return
    _shutting_down = True
    log.info("Shutting down...")

    # 머지 큐 drain (진행 중 머지 완료 대기)
    if ctx.merge_queue:
        try:
            await ctx.merge_queue.drain()
        except Exception as e:
            log.error("MergeQueue drain error", err=str(e))

    # 에이전트 중지
    for agent in ctx.agents:
        try:
            await agent.drain()
        except Exception as e:
            log.error("Agent drain error", agent=agent.id, err=str(e))

    # OrphanCleaner 중지
    await ctx.orphan_cleaner.stop()

    # BoardWatcher 중지
    await ctx.board_watcher.stop()

    # LLM 클라이언트 / GitService HTTP 연결 종료
    for client in ctx.llm_clients:
        if hasattr(client, "close"):
            try:
                await client.close()
            except Exception as e:
                log.error("LLM client close error", err=str(e))
    try:
        await ctx.git_service.close()
    except Exception as e:
        log.error("GitService close error", err=str(e))

    # DB 연결 종료
    await close_engine()

    _system_context = None
    log.info("Shutdown complete")


def get_system_context() -> SystemContext:
    if _system_context is None:
        raise RuntimeError("System not bootstrapped yet")
    return _system_context
