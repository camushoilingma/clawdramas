"""Agent profile loader for ClawDramas."""

from __future__ import annotations

from pathlib import Path

from models import AgentProfile


def load_agents(agents_dir: str | Path = None) -> dict[str, AgentProfile]:
    """Scan agents/ directory and return dict of AgentProfile keyed by id."""
    if agents_dir is None:
        agents_dir = Path(__file__).parent / "agents"
    agents_dir = Path(agents_dir)
    agents = {}
    for path in sorted(agents_dir.glob("*.json")):
        agent = AgentProfile.from_json(str(path))
        agents[agent.id] = agent
    return agents
