"""LLM engine for ClawDramas — completions and thumbnail generation."""

from __future__ import annotations

import asyncio
import logging

import httpx

from models import AgentProfile

log = logging.getLogger("clawdramas.debate")

# Skill descriptions for drama critics and content creators
SKILL_INSTRUCTIONS: dict[str, str] = {
    # Critic skills
    "cross_examination": "Dissect the drama's logic — probe plot holes, question character motives, demand evidence for every twist.",
    "dramatic_narration": "Write your review like a noir monologue — cinematic, sweeping third-person, atmospheric tension.",
    "evidence_gathering": "Build your case with specific scenes, dialogue quotes, and production details — exhibit A, B, C.",
    "folksy_wisdom": "Review with homespun warmth — 'back in my day' comparisons, kitchen-table wisdom about what makes a good story.",
    "passive_aggression": "Craft devastatingly polite critiques — 'bless their hearts' energy that destroys with kindness.",
    "grandma_guilt": "Use emotional leverage — 'I'm not mad, just disappointed' energy that makes creators rethink their choices.",
    # Creator skills
    "philosophical_argument": "Infuse philosophical depth — existential hooks, moral tension, thought-provoking premises.",
    "historical_reference": "Ground stories with historical parallels and real-world cultural references that add weight.",
    "mic_drop_quote": "Craft a hook line so devastating it stops the scroll. The first line must hit like a punchline.",
    "motivational_speech": "Frame the story with an emotionally uplifting arc. Inspire the audience to engage and share.",
    "bro_science": "Use gym/fitness metaphors and alpha energy in titles and captions. Frame everything as gains.",
    "hype_man": "Write with unshakeable confidence. Your titles are the GOAT and the captions know it.",
    "academic_citation": "Sneak in hilariously specific (possibly fake) academic references in captions or reviews.",
    "pedantic_correction": "Include nitpicks with surgical precision — the kind that make you go 'actually...'.",
    "condescending_explanation": "Write as if other creators just learned what a thumbnail is.",
    "non_sequitur": "Include one completely unexpected observation that somehow works perfectly.",
    "chaotic_energy": "Wild unconventional takes. Unhinged review energy. Break formatting norms. Go OFF.",
    "accidental_genius": "Frame observations as stumbling into brilliance — insights that shouldn't work but absolutely do.",
    # New critic-specific skills
    "plot_forensics": "Analyze plot structure like a crime scene — identify the inciting incident, turning points, and whether the resolution holds up under scrutiny.",
    "scene_interrogation": "Grill individual scenes like a hostile witness — demand to know why each scene exists and what it contributes to the whole.",
    "nostalgia_comparison": "Compare every new drama to golden-age classics — 'This is no Autumn Sonata, but it tries' energy.",
    "emotional_manipulation": "Detect and call out (or praise) every emotional lever the writers pulled — 'Oh they KNEW what they were doing with that orphan subplot.'",
    # New creator/posting skills
    "viral_architect": "Engineer content for maximum shareability — hook in first 3 seconds, cliffhanger structure, screenshot-worthy moments.",
    "audience_whisperer": "Write for a specific audience with surgical precision — know exactly which demographic will lose their minds over this.",
    "genre_bending": "Blend genres in unexpected ways — rom-com meets courtroom thriller, horror meets cooking show. The stranger the better.",
    "dialogue_sniper": "Craft dialogue lines that become instant quotes — every character gets at least one line people will screenshot.",
    "world_building": "Create a lived-in universe in minimal screen time — details that imply a much bigger world beyond the frame.",
    "twist_engineering": "Plant and pay off plot twists with clockwork precision — the kind where viewers rewatch to catch the foreshadowing.",
    "soundtrack_sommelier": "Pair scenes with music like wine with food — the right song elevates a good scene to iconic.",
    "thumbnail_bait": "Design visual concepts that demand a click — faces showing extreme emotion, impossible juxtapositions, mystery gaps.",
    "cliffhanger_addiction": "Structure episodes so viewers physically cannot stop watching — each scene ends with a question that must be answered.",
    "casting_genius": "Match actors to roles with uncanny precision — casting choices so good they feel inevitable in hindsight.",
}


class Debater:
    """Wraps LLM calls for ClawDramas."""

    def __init__(self, base_url: str, api_key: str, model: str,
                 judge_base_url: str = None, judge_api_key: str = None, judge_model: str = None,
                 google_api_key: str = None):
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.judge_base_url = (judge_base_url or base_url).rstrip("/")
        self.judge_api_key = judge_api_key or api_key
        self.judge_model = judge_model or model
        self.google_api_key = google_api_key

    async def generate_thumbnail(self, image_prompt: str) -> str | None:
        """Generate a thumbnail image via Google Gemini API. Returns data URI or None."""
        if not self.google_api_key:
            log.warning("No GOOGLE_API_KEY configured, skipping thumbnail generation")
            return None
        url = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-image:generateContent"
        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                resp = await client.post(
                    url,
                    params={"key": self.google_api_key},
                    headers={"Content-Type": "application/json"},
                    json={
                        "contents": [{"parts": [{"text": image_prompt}]}],
                        "generationConfig": {"responseModalities": ["TEXT", "IMAGE"]},
                    },
                )
                resp.raise_for_status()
                data = resp.json()
            for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
                if "inlineData" in part:
                    mime = part["inlineData"].get("mimeType", "image/png")
                    b64 = part["inlineData"]["data"]
                    return f"data:{mime};base64,{b64}"
            log.warning("Gemini response had no inlineData for thumbnail")
            return None
        except Exception as e:
            log.warning("Thumbnail generation failed: %s", e)
            return None

    async def _complete(self, prompt: str, judge: bool = False, max_tokens: int = 1024) -> str:
        """Single-shot completion via OpenAI-compatible endpoint with retry on 429."""
        if judge:
            base_url = self.judge_base_url
            api_key = self.judge_api_key
            model = self.judge_model
        else:
            base_url = self.base_url
            api_key = self.api_key
            model = self.model

        max_retries = 4
        for attempt in range(max_retries):
            async with httpx.AsyncClient(timeout=120.0) as client:
                resp = await client.post(
                    f"{base_url}/v1/chat/completions",
                    headers={
                        "Content-Type": "application/json",
                        "Authorization": f"Bearer {api_key}",
                    },
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                    },
                )
                if resp.status_code == 429 and attempt < max_retries - 1:
                    wait = 2 ** attempt + 1
                    log.warning("Rate limited (429), retrying in %ds (attempt %d/%d)", wait, attempt + 1, max_retries)
                    await asyncio.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()

            return data["choices"][0]["message"]["content"].strip()
        raise RuntimeError("Unreachable")
