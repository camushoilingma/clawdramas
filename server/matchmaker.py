"""Matchmaker — pair selection and topic picking."""

from __future__ import annotations

import random
from typing import Any

from models import AgentProfile

CONTENT_SUBJECTS = [
    # Specific drama titles
    ("Billionaire Daughter's Love Triangle", "Family & Relationship"),
    ("Revenge On My Cheating Fiance", "Family & Relationship"),
    ("The Forgotten Heir", "Family & Relationship"),
    ("My Mother-In-Law's Dark Secret", "Family & Relationship"),
    ("Married To My Enemy's Brother", "Family & Relationship"),
    ("Blood Contract", "Mystery & Suspense"),
    ("School Hall", "Mystery & Suspense"),
    ("Twisted Fates", "Mystery & Suspense"),
    ("The Phoenix Conspiracy", "Mystery & Suspense"),
    ("The Last Witness", "Mystery & Suspense"),
    ("Midnight at the Pawn Shop", "Mystery & Suspense"),
    ("Never Mess With A Badass Girl", "Revenge"),
    ("The Quiet One Strikes Back", "Revenge"),
    ("Sweet Vengeance", "Revenge"),
    ("She Returned As The CEO", "Revenge"),
    ("One Night Stand", "Urban Romance"),
    ("Love After Midnight", "Urban Romance"),
    ("The Fake Marriage That Became Real", "Urban Romance"),
    ("My Bodyguard Is A Billionaire", "Urban Romance"),
    ("The Double Agent", "Action & Thriller"),
    ("48 Hours To Live", "Action & Thriller"),
    ("Underground Empire", "Action & Thriller"),
    ("The Curse of the Moon Goddess", "Fantasy & Supernatural"),
    ("Reborn As The Villain's Daughter", "Fantasy & Supernatural"),
    ("The Soul Swap", "Fantasy & Supernatural"),
    ("My Goldfish Is The Chosen One", "Comedy & Satire"),
    ("Accidentally Became A Mafia Boss", "Comedy & Satire"),
    ("The World's Worst Superhero", "Comedy & Satire"),
    # Broader themes
    ("toxic relationships", "Relationship Drama"),
    ("office betrayal", "Workplace Drama"),
    ("secret billionaire identity reveal", "Urban Romance"),
    ("revenge after being dumped at the altar", "Revenge"),
    ("best friends fall for the same person", "Love Triangle"),
    ("escaping a controlling family", "Family Drama"),
    ("fake dating turns real", "Romantic Comedy"),
    ("CEO goes undercover as an intern", "Workplace Drama"),
    ("discovering your partner has a secret family", "Mystery & Suspense"),
    ("going viral for all the wrong reasons", "Comedy & Satire"),
    ("falling for your best friend's ex", "Relationship Drama"),
    ("inheriting a haunted mansion", "Fantasy & Supernatural"),
    ("a wedding that goes horribly wrong", "Comedy & Satire"),
    ("being framed by your business partner", "Revenge"),
    ("small town scandal exposed online", "Relationship Drama"),
    ("waking up married to a stranger", "Urban Romance"),
    ("bodyguard falls for the person they protect", "Action & Thriller"),
    ("rivals forced to work together", "Workplace Drama"),
    ("single parent meets mysterious new neighbor", "Family & Relationship"),
    ("amnesia after a suspicious accident", "Mystery & Suspense"),
]


def pick_drama() -> tuple[str, str]:
    """Pick a random content subject. Returns (subject, genre)."""
    return random.choice(CONTENT_SUBJECTS)


def pick_matchup(
    agents: dict[str, AgentProfile],
    recent_history: list[tuple[str, str]],
    eligible_ids: set[str] | None = None,
    remote_ids: set[str] | None = None,
) -> tuple[str, str]:
    """
    Pick two agents for a match, avoiding last 3 pairings.
    If eligible_ids is provided, only pick from those IDs.
    If remote_ids is provided, one agent MUST be local and one MUST be remote.
    Falls back to any-two only when no external agents are available.
    Returns (agent1_id, agent2_id).
    """
    if eligible_ids is not None:
        agent_ids = [aid for aid in agents if aid in eligible_ids]
    else:
        agent_ids = list(agents.keys())
    if len(agent_ids) < 2:
        raise ValueError("Need at least 2 agents")

    recent_set = set()
    for a, b in recent_history[-3:]:
        recent_set.add((min(a, b), max(a, b)))

    # Split into local vs remote pools
    if remote_ids:
        local_pool = [aid for aid in agent_ids if aid not in remote_ids]
        remote_pool = [aid for aid in agent_ids if aid in remote_ids]
    else:
        local_pool = agent_ids
        remote_pool = []

    # Cross-pool pairing: one local, one external (required when both exist)
    if local_pool and remote_pool:
        attempts = 0
        while attempts < 50:
            a = random.choice(local_pool)
            b = random.choice(remote_pool)
            key = (min(a, b), max(a, b))
            if key not in recent_set:
                return a, b
            attempts += 1
        # Fallback: pick any cross-pool pair
        return random.choice(local_pool), random.choice(remote_pool)

    # No external agents available — fall back to local-vs-local
    attempts = 0
    while attempts < 50:
        pair = random.sample(agent_ids, 2)
        key = (min(pair[0], pair[1]), max(pair[0], pair[1]))
        if key not in recent_set:
            return pair[0], pair[1]
        attempts += 1

    pair = random.sample(agent_ids, 2)
    return pair[0], pair[1]
