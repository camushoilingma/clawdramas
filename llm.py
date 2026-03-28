"""LLM engine for ClawDramas — completions and thumbnail generation."""

from __future__ import annotations

import asyncio
import base64
import logging
import uuid
from pathlib import Path

import httpx

log = logging.getLogger("clawdramas.llm")

# Directory for saved thumbnail images
IMAGES_DIR = Path(__file__).parent / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)


class LLMClient:
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
        """Generate a thumbnail image via Google Gemini API. Returns /static/images/... URL or None."""
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
                    b64 = part["inlineData"]["data"]
                    filename = f"{uuid.uuid4().hex[:12]}.jpg"
                    filepath = IMAGES_DIR / filename
                    # Decode and re-save as optimized JPEG
                    import io
                    from PIL import Image
                    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
                    img.save(filepath, "JPEG", quality=82, optimize=True)
                    image_url = f"/static/images/{filename}"
                    log.info("Saved thumbnail: %s (%d bytes)", image_url, filepath.stat().st_size)
                    return image_url
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
