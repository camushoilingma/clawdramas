"""Tournament mode — round-robin scheduler and state management."""

from __future__ import annotations

import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from itertools import combinations
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).parent / "data"


@dataclass
class TournamentRecord:
    wins: int = 0
    losses: int = 0
    draws: int = 0
    points: int = 0  # 3 win, 1 draw, 0 loss

    def to_dict(self) -> dict:
        return {"wins": self.wins, "losses": self.losses, "draws": self.draws, "points": self.points}

    @classmethod
    def from_dict(cls, d: dict) -> TournamentRecord:
        return cls(**d)


@dataclass
class Tournament:
    id: str
    agent_ids: list[str]
    schedule: list[tuple[str, str]]
    completed: list[str]  # match_ids
    standings: dict[str, TournamentRecord]
    battle_counts: dict[str, int]
    started_at: float
    ended_at: float | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "agent_ids": self.agent_ids,
            "schedule": self.schedule,
            "completed": self.completed,
            "standings": {k: v.to_dict() for k, v in self.standings.items()},
            "battle_counts": self.battle_counts,
            "started_at": self.started_at,
            "ended_at": self.ended_at,
        }

    @classmethod
    def from_dict(cls, d: dict) -> Tournament:
        return cls(
            id=d["id"],
            agent_ids=d["agent_ids"],
            schedule=[tuple(p) for p in d["schedule"]],
            completed=d["completed"],
            standings={k: TournamentRecord.from_dict(v) for k, v in d["standings"].items()},
            battle_counts=d["battle_counts"],
            started_at=d["started_at"],
            ended_at=d.get("ended_at"),
        )


def create_tournament(agent_ids: list[str]) -> Tournament:
    """Create a new round-robin tournament with all pairings shuffled."""
    schedule = list(combinations(agent_ids, 2))
    random.shuffle(schedule)

    standings = {aid: TournamentRecord() for aid in agent_ids}
    battle_counts = {aid: 0 for aid in agent_ids}

    return Tournament(
        id=uuid.uuid4().hex[:8],
        agent_ids=list(agent_ids),
        schedule=schedule,
        completed=[],
        standings=standings,
        battle_counts=battle_counts,
        started_at=time.time(),
    )


def add_agent(tournament: Tournament, new_id: str) -> int:
    """Add a new agent mid-tournament. Returns number of matches added."""
    if new_id in tournament.agent_ids:
        return 0

    # Add matches vs all existing agents
    new_matches = [(new_id, existing) for existing in tournament.agent_ids]
    random.shuffle(new_matches)
    tournament.schedule.extend(new_matches)

    tournament.agent_ids.append(new_id)
    tournament.standings[new_id] = TournamentRecord()
    tournament.battle_counts[new_id] = 0

    save_tournament(tournament)
    return len(new_matches)


def next_match(tournament: Tournament) -> tuple[str, str] | None:
    """Pop the next match, prioritizing agents with fewest battles."""
    if not tournament.schedule:
        return None

    # Sort schedule so pairs involving agents with fewest battles come first
    tournament.schedule.sort(
        key=lambda pair: tournament.battle_counts.get(pair[0], 0) + tournament.battle_counts.get(pair[1], 0)
    )

    return tournament.schedule.pop(0)


def record_result(tournament: Tournament, match_id: str, a1: str, a2: str, winner_id: str | None):
    """Record a match result, update standings and battle counts."""
    tournament.completed.append(match_id)
    tournament.battle_counts[a1] = tournament.battle_counts.get(a1, 0) + 1
    tournament.battle_counts[a2] = tournament.battle_counts.get(a2, 0) + 1

    s1 = tournament.standings.setdefault(a1, TournamentRecord())
    s2 = tournament.standings.setdefault(a2, TournamentRecord())

    if winner_id is None:
        s1.draws += 1
        s2.draws += 1
        s1.points += 1
        s2.points += 1
    elif winner_id == a1:
        s1.wins += 1
        s2.losses += 1
        s1.points += 3
    elif winner_id == a2:
        s2.wins += 1
        s1.losses += 1
        s2.points += 3

    save_tournament(tournament)


def is_complete(tournament: Tournament) -> bool:
    """Check if all scheduled matches have been played."""
    return len(tournament.schedule) == 0


def standings_sorted(tournament: Tournament) -> list[dict]:
    """Return standings sorted by points desc, then wins desc."""
    rows = []
    for aid in tournament.agent_ids:
        rec = tournament.standings.get(aid, TournamentRecord())
        rows.append({
            "agent_id": aid,
            "wins": rec.wins,
            "losses": rec.losses,
            "draws": rec.draws,
            "points": rec.points,
            "battles": tournament.battle_counts.get(aid, 0),
        })
    rows.sort(key=lambda r: (r["points"], r["wins"]), reverse=True)
    return rows


def save_tournament(tournament: Tournament):
    """Persist tournament state to data/tournament.json."""
    DATA_DIR.mkdir(exist_ok=True)
    path = DATA_DIR / "tournament.json"
    with open(path, "w") as f:
        json.dump(tournament.to_dict(), f, indent=2)


def load_active_tournament() -> Tournament | None:
    """Load active tournament from disk, or None if none exists / already ended."""
    path = DATA_DIR / "tournament.json"
    if not path.exists():
        return None
    try:
        with open(path) as f:
            data = json.load(f)
        t = Tournament.from_dict(data)
        if t.ended_at is not None:
            return None
        return t
    except Exception:
        return None


def clear_tournament():
    """Remove persisted tournament file."""
    path = DATA_DIR / "tournament.json"
    if path.exists():
        path.unlink()
