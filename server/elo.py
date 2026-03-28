"""Elo rating system with JSON persistence."""

from __future__ import annotations

import json
from pathlib import Path

from models import AgentStats

ELO_PATH = Path(__file__).parent / "data" / "elo.json"
K = 32


def load_elo() -> dict[str, AgentStats]:
    """Load Elo ratings from JSON file."""
    ELO_PATH.parent.mkdir(exist_ok=True)
    if not ELO_PATH.exists():
        return {}
    with open(ELO_PATH) as f:
        data = json.load(f)
    return {k: AgentStats.from_dict(v) for k, v in data.items()}


def save_elo(stats: dict[str, AgentStats]):
    """Save Elo ratings to JSON file."""
    ELO_PATH.parent.mkdir(exist_ok=True)
    with open(ELO_PATH, "w") as f:
        json.dump({k: v.to_dict() for k, v in stats.items()}, f, indent=2)


def ensure_agent(stats: dict[str, AgentStats], agent_id: str) -> AgentStats:
    """Ensure agent exists in stats, seeding at 1200 if new."""
    if agent_id not in stats:
        stats[agent_id] = AgentStats(agent_id=agent_id)
    return stats[agent_id]


def update_elo(
    stats: dict[str, AgentStats], a1_id: str, a2_id: str, winner_id: str | None
) -> dict:
    """
    Update Elo ratings after a match.
    winner_id=None means draw.
    Returns change info dict.
    """
    s1 = ensure_agent(stats, a1_id)
    s2 = ensure_agent(stats, a2_id)

    old1, old2 = s1.elo, s2.elo

    # Expected scores
    e1 = 1 / (1 + 10 ** ((old2 - old1) / 400))
    e2 = 1 - e1

    # Actual scores
    if winner_id is None:
        a1, a2 = 0.5, 0.5
        s1.draws += 1
        s2.draws += 1
    elif winner_id == a1_id:
        a1, a2 = 1.0, 0.0
        s1.wins += 1
        s2.losses += 1
    else:
        a1, a2 = 0.0, 1.0
        s1.losses += 1
        s2.wins += 1

    s1.elo = round(old1 + K * (a1 - e1))
    s2.elo = round(old2 + K * (a2 - e2))

    save_elo(stats)

    return {
        "agents": [
            {"id": a1_id, "old_elo": old1, "new_elo": s1.elo, "change": s1.elo - old1},
            {"id": a2_id, "old_elo": old2, "new_elo": s2.elo, "change": s2.elo - old2},
        ]
    }
