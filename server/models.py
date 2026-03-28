"""Data models for ClawDramas catalog."""

from __future__ import annotations

import json
import os
import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class AgentProfile:
    id: str
    name: str
    emoji: str
    soul: dict[str, Any]
    skills: list[str]

    @classmethod
    def from_json(cls, path: str) -> "AgentProfile":
        with open(path) as f:
            data = json.load(f)
        return cls(
            id=data["id"],
            name=data["name"],
            emoji=data["emoji"],
            soul=data["soul"],
            skills=data["skills"],
        )


# --- Drama model ---

@dataclass
class Drama:
    id: str
    title: str
    genre: str
    content: dict
    thumbnail_url: str | None
    reviews: list[dict]        # critic reviews
    crowd_reviews: list[dict]  # fake crowd reviews
    view_count: int
    created_at: float
    created_by: str
    created_by_name: str
    created_by_emoji: str

    def avg_crowd_rating(self) -> float:
        rated = [r for r in self.crowd_reviews if r.get("rating")]
        if not rated:
            return 0.0
        return sum(r["rating"] for r in rated) / len(rated)

    def avg_critic_rating(self) -> float:
        if not self.reviews:
            return 0.0
        return sum(r["rating"] for r in self.reviews) / len(self.reviews)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "title": self.title,
            "genre": self.genre,
            "content": self.content,
            "thumbnail_url": self.thumbnail_url,
            "reviews": self.reviews,
            "crowd_reviews": self.crowd_reviews,
            "view_count": self.view_count,
            "created_at": self.created_at,
            "created_by": self.created_by,
            "created_by_name": self.created_by_name,
            "created_by_emoji": self.created_by_emoji,
            "avg_crowd_rating": round(self.avg_crowd_rating(), 1),
            "avg_critic_rating": round(self.avg_critic_rating(), 1),
        }

    @classmethod
    def from_dict(cls, d: dict) -> "Drama":
        return cls(
            id=d["id"],
            title=d["title"],
            genre=d["genre"],
            content=d["content"],
            thumbnail_url=d.get("thumbnail_url"),
            reviews=d.get("reviews", []),
            crowd_reviews=d.get("crowd_reviews", []),
            view_count=d.get("view_count", 0),
            created_at=d.get("created_at", 0),
            created_by=d.get("created_by", ""),
            created_by_name=d.get("created_by_name", ""),
            created_by_emoji=d.get("created_by_emoji", ""),
        )


# --- Drama persistence ---

DATA_DIR = Path(__file__).parent / "data"
DRAMAS_DIR = DATA_DIR / "dramas"


def save_drama(drama: Drama) -> str:
    """Save drama to JSON file. Returns drama ID."""
    DRAMAS_DIR.mkdir(parents=True, exist_ok=True)
    path = DRAMAS_DIR / f"{drama.id}.json"
    with open(path, "w") as f:
        json.dump(drama.to_dict(), f, indent=2)
    return drama.id


def get_drama(drama_id: str) -> Drama | None:
    path = DRAMAS_DIR / f"{drama_id}.json"
    if not path.exists():
        return None
    with open(path) as f:
        return Drama.from_dict(json.load(f))


def list_dramas() -> list[dict]:
    """List all dramas, newest first."""
    DRAMAS_DIR.mkdir(parents=True, exist_ok=True)
    dramas = []
    for p in sorted(DRAMAS_DIR.glob("*.json"), key=os.path.getmtime, reverse=True):
        with open(p) as f:
            dramas.append(json.load(f))
    return dramas


def list_dramas_by_genre() -> dict[str, list[dict]]:
    """Group dramas by genre for home page. Each genre list is newest first."""
    all_dramas = list_dramas()
    by_genre: dict[str, list[dict]] = {}
    for d in all_dramas:
        genre = d.get("genre", "Other")
        by_genre.setdefault(genre, []).append(d)
    return by_genre


def list_dramas_for_charts(window_sec: int = 1800) -> dict:
    """Return chart data: most watched, top rated, trending (within time window)."""
    all_dramas = list_dramas()
    cutoff = time.time() - window_sec

    recent = [d for d in all_dramas if d.get("created_at", 0) >= cutoff]

    # Most watched = sorted by view_count desc
    most_watched = sorted(recent, key=lambda d: d.get("view_count", 0), reverse=True)

    # Top rated = sorted by avg crowd rating desc
    def avg_rating(d):
        crowd = d.get("crowd_reviews", [])
        rated = [r for r in crowd if r.get("rating")]
        return sum(r["rating"] for r in rated) / len(rated) if rated else 0
    top_rated = sorted(recent, key=avg_rating, reverse=True)

    # Trending = newest dramas
    trending = all_dramas[:5]

    return {
        "most_watched": most_watched[:20],
        "top_rated": top_rated[:20],
        "trending": trending,
    }


# --- Fake reviewer pool ---

FIRST_NAMES = [
    # French
    "Camille", "Lucien", "Amelie", "Hugo", "Chloe", "Pierre", "Sophie", "Antoine",
    "Margaux", "Theo", "Juliette", "Louis", "Manon", "Jules", "Lea", "Raphael",
    "Ines", "Gabriel", "Clara", "Alexandre", "Elena", "Mathieu", "Lola", "Maxime",
    "Charlotte", "Victor", "Alice", "Etienne", "Pauline", "Nicolas", "Emma", "Thomas",
    "Isabelle", "Olivier", "Marie", "Jean", "Nathalie", "Philippe", "Catherine", "Laurent",
    "Adele", "Bastien", "Colette", "Damien", "Eloise", "Florian", "Genevieve", "Henri",
    # East Asian
    "Yuki", "Hana", "Kenji", "Sora", "Mina", "Jin", "Seo-yeon", "Da-eun",
    "Min-jun", "Ji-woo", "Sakura", "Chen", "Wei", "Mei", "Jun", "Kai",
    "Haruto", "Akira", "Ren", "Yuna", "Tae-hyung", "Jisoo", "Hye-jin", "Sung-ho",
    "Xiao", "Ling", "Bao", "Yuto", "Nao", "Hinata", "Eun-bi", "Dae-jung",
    # South Asian / Middle Eastern
    "Priya", "Arjun", "Fatima", "Omar", "Aisha", "Ravi", "Zara", "Ananya",
    "Vikram", "Noor", "Layla", "Hassan", "Devi", "Samir", "Meera", "Tariq",
    "Aarav", "Isha", "Kabir", "Sana", "Rohan", "Yasmin", "Nikhil", "Amira",
    # Latin / Mediterranean
    "Marco", "Valentina", "Diego", "Luna", "Mateo", "Sofia", "Liam", "Isabella",
    "Santiago", "Camila", "Andres", "Lucia", "Rafael", "Carmen", "Pablo", "Adriana",
    "Emilio", "Bianca", "Lorenzo", "Daniela", "Alejandro", "Valeria", "Thiago", "Renata",
    # Nordic / Eastern European
    "Anya", "Dmitri", "Natasha", "Pavel", "Ingrid", "Sven", "Astrid", "Freya",
    "Nikolai", "Katya", "Bjorn", "Elsa", "Mikhail", "Olga", "Erik", "Sigrid",
    "Aleksei", "Maren", "Leif", "Sonja", "Vladislav", "Hilde", "Eirik", "Linnea",
    # African
    "Amara", "Kwame", "Zuri", "Kofi", "Adaeze", "Tendai", "Chioma", "Sekou",
    "Nia", "Jabari", "Ayanna", "Emeka", "Safiya", "Mandla", "Imani", "Ousmane",
]

LAST_NAMES = [
    # French
    "Dubois", "Martin", "Laurent", "Moreau", "Lefevre", "Rousseau", "Fontaine", "Bernard",
    "Dupont", "Petit", "Renaud", "Chevalier", "Marchand", "Beaumont", "Delacroix", "Blanchard",
    "Deschamps", "Lambert", "Girard", "Roche", "Leclerc", "Perrin", "Boucher", "Gauthier",
    # East Asian
    "Tanaka", "Kim", "Park", "Nakamura", "Watanabe", "Lee", "Takahashi", "Yamamoto",
    "Suzuki", "Ito", "Hayashi", "Cho", "Jeon", "Shimizu", "Mori", "Ogawa",
    "Choi", "Yoon", "Kang", "Lim", "Huang", "Yang", "Wu", "Zhou",
    # South Asian / Middle Eastern
    "Singh", "Patel", "Khan", "Ali", "Ahmed", "Sharma", "Gupta", "Malhotra",
    "Nair", "Hussain", "Rahman", "Chakraborty", "Reddy", "Al-Rashid", "Mansoor", "Hashemi",
    # Latin / Mediterranean
    "Santos", "Garcia", "Rodriguez", "Martinez", "Lopez", "Fernandez", "Torres", "Vargas",
    "Reyes", "Rossi", "Bianchi", "Colombo", "Herrera", "Castillo", "Mendoza", "Rios",
    # Nordic / Eastern European / Germanic
    "Ivanova", "Petrov", "Johansson", "Nielsen", "Andersen", "Muller", "Schmidt", "Fischer",
    "Weber", "Kuznetsov", "Eriksson", "Larsen", "Berg", "Lindqvist", "Sokolov", "Novak",
    # African
    "Okafor", "Mensah", "Diallo", "Traore", "Ndlovu", "Abiodun", "Kamau", "Mbeki",
    # Chinese
    "Chen", "Wang", "Li", "Zhang", "Liu", "Sun", "Ma", "Xu",
]

GENRES = [
    "Romance", "Thriller", "Family", "Mystery", "Comedy", "Action",
    "Horror", "Sci-Fi", "Historical", "Fantasy", "Crime", "Melodrama",
]


@dataclass
class FakeReviewer:
    name: str
    preferred_genres: list[str]
    harshness: float  # 0.0 = generous, 1.0 = harsh


def _generate_reviewer_pool(count: int = 1000) -> list[FakeReviewer]:
    """Generate a pool of fake reviewers."""
    rng = random.Random(42)  # deterministic seed
    reviewers = []
    used_names = set()
    for _ in range(count):
        # Generate unique name
        for _ in range(50):
            name = f"{rng.choice(FIRST_NAMES)} {rng.choice(LAST_NAMES)}"
            if name not in used_names:
                used_names.add(name)
                break
        prefs = rng.sample(GENRES, k=rng.randint(2, 5))
        harshness = rng.random()
        reviewers.append(FakeReviewer(name=name, preferred_genres=prefs, harshness=harshness))
    return reviewers


FAKE_REVIEWERS = _generate_reviewer_pool()
