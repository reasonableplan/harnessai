import pytest
from src.core.state.task_state_machine import is_valid_transition
from src.core.types import TaskStatus


def test_backlog_to_ready():
    assert is_valid_transition(TaskStatus.BACKLOG, TaskStatus.READY) is True


def test_ready_to_in_progress():
    assert is_valid_transition(TaskStatus.READY, TaskStatus.IN_PROGRESS) is True


def test_in_progress_to_review():
    assert is_valid_transition(TaskStatus.IN_PROGRESS, TaskStatus.REVIEW) is True


def test_review_to_done():
    assert is_valid_transition(TaskStatus.REVIEW, TaskStatus.DONE) is True


def test_done_is_terminal():
    for status in TaskStatus:
        if status != TaskStatus.DONE:
            assert is_valid_transition(TaskStatus.DONE, status) is False


def test_invalid_backlog_to_done():
    assert is_valid_transition(TaskStatus.BACKLOG, TaskStatus.DONE) is False


def test_failed_to_ready():
    assert is_valid_transition(TaskStatus.FAILED, TaskStatus.READY) is True
