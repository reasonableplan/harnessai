"""토큰 예산 관리 — 태스크/일일 예산 초과 시 실행을 차단한다."""
from __future__ import annotations

from src.core.logging.logger import get_logger
from src.core.state.state_store import StateStore

log = get_logger("TokenBudget")


_MAX_CONSECUTIVE_FAILURES = 5


class TokenBudgetManager:
    def __init__(
        self,
        state_store: StateStore,
        max_tokens_per_task: int = 500_000,
        max_tokens_per_day: int = 10_000_000,
    ) -> None:
        self._state_store = state_store
        self._max_per_task = max_tokens_per_task
        self._max_per_day = max_tokens_per_day
        self._consecutive_failures = 0

    async def check_budget(self, task_id: str) -> tuple[bool, str]:
        """예산 내인지 확인한다. (allowed, reason) 반환."""
        try:
            # 일일 예산 체크
            daily = await self._state_store.get_daily_token_usage()
            daily_total = daily["input"] + daily["output"]
            if daily_total >= self._max_per_day:
                reason = (
                    f"Daily token budget exceeded: {daily_total:,} >= {self._max_per_day:,}"
                )
                log.warning(reason)
                self._consecutive_failures = 0
                return False, reason

            # 태스크별 예산 체크
            logs = await self._state_store.get_task_logs(task_id)
            task_total = sum(
                (getattr(entry, "token_input", 0) or 0) + (getattr(entry, "token_output", 0) or 0)
                for entry in logs
            )
            if task_total >= self._max_per_task:
                reason = (
                    f"Task token budget exceeded: {task_total:,} >= {self._max_per_task:,}"
                )
                log.warning(reason, task_id=task_id)
                self._consecutive_failures = 0
                return False, reason

            self._consecutive_failures = 0
            return True, ""
        except Exception as e:
            self._consecutive_failures += 1
            if self._consecutive_failures > _MAX_CONSECUTIVE_FAILURES:
                reason = (
                    f"Budget check failed {self._consecutive_failures} consecutive times, blocking execution"
                )
                log.error(reason, err=str(e))
                return False, reason
            # 일시적 실패 — 가용성 우선으로 허용
            log.warning("Budget check failed, allowing execution", err=str(e),
                        consecutive_failures=self._consecutive_failures)
            return True, ""

    async def record_usage(
        self, log_id: str, input_tokens: int, output_tokens: int,
    ) -> None:
        """태스크 로그에 토큰 사용량을 기록한다."""
        try:
            await self._state_store.update_task_log(log_id, {
                "token_input": input_tokens,
                "token_output": output_tokens,
            })
        except Exception as e:
            log.warning("Failed to record token usage", err=str(e))

    async def get_daily_usage(self) -> dict[str, int]:
        """오늘의 토큰 사용량 합계를 반환한다."""
        return await self._state_store.get_daily_token_usage()
