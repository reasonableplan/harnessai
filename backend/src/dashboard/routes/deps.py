from __future__ import annotations


def get_state_store():
    from src.bootstrap import get_system_context
    return get_system_context().state_store


def get_director():
    from src.agents.director.director_agent import DirectorAgent
    from src.bootstrap import get_system_context

    ctx = get_system_context()
    for agent in ctx.agents:
        if isinstance(agent, DirectorAgent):
            return agent
    raise RuntimeError("DirectorAgent not found in system context")
