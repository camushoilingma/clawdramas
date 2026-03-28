"""Critic reviews + crowd simulation for ClawDramas."""

from __future__ import annotations

import json
import logging
import random
import time
from typing import Any

from models import AgentProfile, FakeReviewer, FAKE_REVIEWERS

log = logging.getLogger("clawdramas.reviews")

# --- Critic review prompts ---

REVIEW_SYSTEM = """\
You are {name} {emoji}, a drama critic for ClawDramas.

YOUR PERSONALITY: {personality}
YOUR STYLE: {style}
YOUR CATCHPHRASE: "{catchphrase}"

Review this drama submission:
TITLE: {title}
GENRE: {genre}

CONTENT:
{content_summary}

Write a short, opinionated review (2-3 sentences) in your unique voice and character. Be entertaining. Rate the drama 1-10.

Respond with ONLY valid JSON, nothing else:
{{"rating": <1-10>, "commentary": "Your 2-3 sentence review"}}"""


async def generate_review(llm_client, critic: AgentProfile, title: str, genre: str, content: dict) -> dict:
    """Generate a single critic review via LLM."""
    # Summarize content for the prompt (truncated)
    content_summary = json.dumps(content, indent=2)[:2000]

    prompt = REVIEW_SYSTEM.format(
        name=critic.name,
        emoji=critic.emoji,
        personality=critic.soul.get("personality", ""),
        style=critic.soul.get("style", ""),
        catchphrase=critic.soul.get("catchphrase", ""),
        title=title,
        genre=genre,
        content_summary=content_summary,
    )

    try:
        text = await llm_client._complete(prompt, max_tokens=512)
        # Strip markdown fencing
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        result = json.loads(cleaned)
        return {
            "agent_id": critic.id,
            "agent_name": critic.name,
            "agent_emoji": critic.emoji,
            "rating": max(1, min(10, int(result.get("rating", 5)))),
            "commentary": result.get("commentary", "No comment."),
        }
    except Exception as e:
        log.warning("Failed to generate review from %s: %s", critic.name, e)
        return {
            "agent_id": critic.id,
            "agent_name": critic.name,
            "agent_emoji": critic.emoji,
            "rating": 5,
            "commentary": f"*{critic.name} was unavailable for comment*",
        }


async def generate_all_reviews(llm_client, critics: list[AgentProfile], title: str, genre: str, content: dict) -> list[dict]:
    """Generate reviews from all critics in parallel."""
    import asyncio
    tasks = [generate_review(llm_client, c, title, genre, content) for c in critics]
    return list(await asyncio.gather(*tasks))


# --- Crowd simulation ---

COMMENT_TEMPLATES = [
    # Positive
    "Absolutely loved the twist!",
    "The casting was perfect",
    "This is why I love {genre} dramas",
    "Binged it in one sitting",
    "The soundtrack alone is worth it",
    "The dialogue is chef's kiss",
    "My favorite this season",
    "The villain arc was incredible",
    "Cried actual tears, no shame",
    "This deserves an award",
    "Finally a {genre} drama that doesn't disappoint",
    "The chemistry between the leads is electric",
    "Already rewatching it",
    "My mom recommended this and she was right",
    "Stayed up until 3am for this, no regrets",
    "Masterpiece. That's it. That's the review.",
    "The twist at the end? Did NOT see that coming",
    "Perfect comfort watch",
    "Watched this on the metro and missed my stop. Twice.",
    "The way they used silence in that last scene... goosebumps",
    "I need a season 2 immediately or I will riot",
    "Recommended this to everyone at work, no one has thanked me yet",
    "This healed something in me I didn't know was broken",
    "Best {genre} I've seen since 2019 easily",
    "The acting alone carries this to a 5",
    "I'm still thinking about the ending three days later",
    "Finally someone understands what {genre} should feel like",
    "Bought the soundtrack after episode 1",
    # Negative
    "Not bad, but the ending felt rushed",
    "Mid. Expected better from {genre}",
    "Overhyped tbh",
    "Who greenlit this?",
    "Predictable but still enjoyable",
    "The plot holes ruined it for me",
    "Lost me at episode 2",
    "Decent. Not great, not terrible.",
    "The trailer was better than the actual drama",
    "I wanted to love this but the writing let me down",
    "Style over substance unfortunately",
    "They had all the right ingredients and still burned it",
    "Fell asleep twice. Not a compliment.",
    "Read the synopsis instead, you'll get the same experience",
    "The lead carried the whole thing on their back alone",
    # Mixed / Neutral
    "Better than I expected, solid 4/5",
    "Wish there were more episodes",
    "The cinematography though...",
    "A bit slow to start but worth the wait",
    "Good enough for a rainy Sunday",
    "Interesting concept, shaky execution",
    "Would have been a 5 if the last 10 minutes didn't exist",
    "My partner loved it, I thought it was fine",
    "Not my usual genre but I was pleasantly surprised",
    "Solid 3. Would recommend with caveats.",
    "The first half is brilliant, then it gets weird",
    "Everyone in the comments is overreacting, it's okay",
    # Extra
    "The villain was more interesting than the hero honestly",
    "This felt like a warm hug on a cold day",
    "Who wrote this dialogue? Shakespeare's ghost?",
    "I'm not crying you're crying",
    "The pacing was immaculate",
    "Told my therapist about this show. She started watching too.",
    "That one scene lives in my head rent free",
    "Peak fiction. I said what I said.",
    "My cat watched this with me and even she was invested",
    "Solid debut from this studio, excited for more",
    "The ending was so good I forgave the slow start",
    "Why is no one talking about this?!",
    "Three episodes in and I've already told six people about it",
    "Gave it a chance because of the cast and was not disappointed",
    "The cinematography alone deserves a standing ovation",
    "I have trust issues now thanks to that plot twist",
    "Underrated gem. Bookmark this review.",
    "Started ironically, ended up genuinely obsessed",
    "Would sell my soul for a sequel",
    "The way they built tension was surgical",
    "Every scene had purpose. Tight writing.",
    "An emotional rollercoaster I did not consent to",
    "Beautifully unhinged. 10/10 would spiral again.",
    "This drama understood the assignment",
    "Watched it dubbed, still cried",
    "My expectations were low and I was still let down",
    "Generic {genre} with a pretty filter on it",
    "Casting was a choice. Not a good one.",
    "Please stop recommending this to me",
    "I've seen better {genre} from student films",
    "If you've seen one of these you've seen them all",
]

LLM_CROWD_SYSTEM = """\
Write {count} one-sentence drama reviews from different viewers. Each review should feel like a real social media comment — casual, opinionated, varied tone.

Drama: "{title}" ({genre})

Return ONLY a JSON array of objects:
[{{"name": "viewer name", "comment": "their one-liner"}}]

Use these viewer names: {names}"""


def generate_crowd_reviews(title: str, genre: str, content: dict, count: int = 30) -> tuple[list[dict], int]:
    """Generate fake crowd reviews + view count. Synchronous (no LLM).

    Returns (crowd_reviews, view_count).
    """
    rng = random.Random()

    # Pick random reviewers from pool
    reviewers = rng.sample(FAKE_REVIEWERS, min(count, len(FAKE_REVIEWERS)))

    # Time mapping: 30 real minutes = 30 agent days
    # Spread fake timestamps across "the past 30 agent days" within the real 30 min window
    now = time.time()
    window = 1800  # 30 minutes in seconds

    crowd_reviews = []
    comment_count = 0

    for reviewer in reviewers:
        # Rating: influenced by harshness + whether they like this genre
        base = 3.0
        if genre in reviewer.preferred_genres:
            base += 1.0
        # Harshness shifts the rating down
        rating = base + rng.uniform(-1.5, 2.0) - (reviewer.harshness * 1.5)
        rating = max(1, min(5, round(rating)))

        # Fake timestamp spread across the window
        fake_ts = now - rng.uniform(0, window)

        review: dict[str, Any] = {
            "name": reviewer.name,
            "rating": rating,
            "timestamp": fake_ts,
        }

        # ~5-8 get a template comment
        if comment_count < 8 and rng.random() < 0.25:
            template = rng.choice(COMMENT_TEMPLATES)
            review["comment"] = template.format(genre=genre)
            comment_count += 1

        crowd_reviews.append(review)

    # Sort by timestamp (newest first)
    crowd_reviews.sort(key=lambda r: r["timestamp"], reverse=True)

    # View count: random 50k-500k
    view_count = rng.randint(50000, 500000)

    return crowd_reviews, view_count


async def generate_llm_crowd_reviews(llm_client, title: str, genre: str, reviewer_names: list[str], count: int = 3) -> list[dict]:
    """Generate a few LLM-powered one-liner reviews from fake reviewers."""
    names_str = ", ".join(reviewer_names[:count])
    prompt = LLM_CROWD_SYSTEM.format(
        count=count,
        title=title,
        genre=genre,
        names=names_str,
    )

    try:
        text = await llm_client._complete(prompt, max_tokens=512)
        cleaned = text.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[1] if "\n" in cleaned else cleaned[3:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3].strip()
        results = json.loads(cleaned)
        return results if isinstance(results, list) else []
    except Exception as e:
        log.warning("LLM crowd reviews failed: %s", e)
        return []
