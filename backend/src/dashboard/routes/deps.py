from __future__ import annotations


def get_state_store():
    from src.bootstrap import get_system_context
    return get_system_context().state_store
