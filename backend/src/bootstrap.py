"""시스템 컨텍스트 초기화 및 부트스트랩."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from src.core.board.board_watcher import BoardWatcher
from src.core.config import AppConfig
from src.core.db.session import close_engine, create_engine, get_session_factory
from src.core.git_service.git_service import GitService
from src.core.hooks.builtin_hooks import register_builtin_hooks
from src.core.hooks.hook_registry import HookRegistry
from src.core.logging.logger import get_logger
from src.core.messaging.message_bus import MessageBus
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
    llm_client: Any = None


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

    # 3. LLM Client
    llm_client = _create_llm_client(config)

    # 4. GitService
    git_service = GitService(config)
    await git_service.validate_connection()

    # 5. BoardWatcher
    board_watcher = BoardWatcher(git_service, state_store, message_bus)

    # 6. HookRegistry + 내장 훅 등록
    hook_registry = HookRegistry(state_store)
    await register_builtin_hooks(hook_registry, state_store)

    # 7. OrphanCleaner
    orphan_cleaner = OrphanCleaner(state_store, git_service)

    # 8. RAG — 코드베이스 인덱싱 + 메모리
    code_search, memory_store = await _init_rag(config)

    # 9. 에이전트 생성
    agents = _create_agents(
        config, message_bus, state_store, git_service, llm_client, code_search, memory_store,
    )

    # 9.5. Director 플랜 복원 (서버 재시작 시 이전 세션 이어가기)
    from src.agents.director.director_agent import DirectorAgent
    for agent in agents:
        if isinstance(agent, DirectorAgent):
            await agent.restore_plan_from_db()
            break

    # 10. 에이전트 DB 등록 (병렬, 개별 실패 허용)
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
        llm_client=llm_client,
    )
    _system_context = ctx
    log.info("Bootstrap complete", agent_count=len(agents))
    return ctx


def _create_llm_client(config: AppConfig) -> Any:
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

        # fastembed 임베딩 함수
        from fastembed import TextEmbedding
        embed_model = TextEmbedding(model_name="BAAI/bge-small-en-v1.5")
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
    llm_client: Any,
    code_search: Any = None,
    memory_store: Any = None,
) -> list[Any]:
    from src.agents.backend_agent.backend_agent import BackendAgent
    from src.agents.director.director_agent import DirectorAgent
    from src.agents.docs.docs_agent import DocsAgent
    from src.agents.frontend.frontend_agent import FrontendAgent
    from src.agents.git.git_agent import GitAgent
    from src.core.types import AgentConfig, AgentLevel

    work_dir = config.git_work_dir

    def make_config(agent_id: str, domain: str, level: AgentLevel, **kwargs) -> AgentConfig:
        return AgentConfig(id=agent_id, domain=domain, level=level, **kwargs)

    director = DirectorAgent(
        config=make_config("director", "director", AgentLevel.DIRECTOR),
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=llm_client,
        memory_store=memory_store,
    )

    git_agent = GitAgent(
        config=make_config("agent-git", "git", AgentLevel.WORKER),
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=llm_client,
        work_dir=work_dir,
        code_search=code_search,
    )
    backend = BackendAgent(
        config=make_config("agent-backend", "backend", AgentLevel.WORKER, temperature=0.2),
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=llm_client,
        work_dir=work_dir,
        code_search=code_search,
    )
    frontend = FrontendAgent(
        config=make_config("agent-frontend", "frontend", AgentLevel.WORKER, temperature=0.2),
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=llm_client,
        work_dir=work_dir,
        code_search=code_search,
    )
    docs = DocsAgent(
        config=make_config("agent-docs", "docs", AgentLevel.WORKER, temperature=0.3),
        message_bus=message_bus,
        state_store=state_store,
        git_service=git_service,
        llm_client=llm_client,
        work_dir=work_dir,
        code_search=code_search,
    )
    return [director, git_agent, backend, frontend, docs]


_shutting_down = False


async def shutdown(ctx: SystemContext) -> None:
    """Graceful shutdown — 에이전트 drain → watcher → DB."""
    global _shutting_down, _system_context
    if _shutting_down:
        return
    _shutting_down = True
    log.info("Shutting down...")

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
    if hasattr(ctx.llm_client, "close"):
        try:
            await ctx.llm_client.close()
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
