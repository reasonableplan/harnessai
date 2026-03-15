from src.core.types import TaskStatus

# 허용되는 상태 전환 맵
_VALID_TRANSITIONS: dict[TaskStatus, set[TaskStatus]] = {
    TaskStatus.BACKLOG:      {TaskStatus.READY, TaskStatus.FAILED},
    TaskStatus.READY:        {TaskStatus.IN_PROGRESS, TaskStatus.FAILED, TaskStatus.BACKLOG},
    TaskStatus.IN_PROGRESS:  {TaskStatus.REVIEW, TaskStatus.FAILED, TaskStatus.READY},
    TaskStatus.REVIEW:       {TaskStatus.DONE, TaskStatus.FAILED, TaskStatus.READY, TaskStatus.IN_PROGRESS},
    TaskStatus.FAILED:       {TaskStatus.READY, TaskStatus.BACKLOG},
    TaskStatus.DONE:         set(),
}


def is_valid_transition(from_status: TaskStatus, to_status: TaskStatus) -> bool:
    """상태 전환이 유효한지 검사한다."""
    return to_status in _VALID_TRANSITIONS.get(from_status, set())
