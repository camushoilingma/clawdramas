"""ClawDramas — Netflix-style drama catalog server."""

from __future__ import annotations

import base64
import io
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

from agents import load_agents
from llm import LLMClient
from models import Drama, save_drama, get_drama, list_dramas, list_dramas_by_genre, list_dramas_for_charts
from reviews import generate_all_reviews, generate_crowd_reviews, generate_llm_crowd_reviews

load_dotenv()

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("clawdramas")

# --- Config ---
LLM_BASE_URL = os.getenv("LLM_BASE_URL", "http://localhost:8080")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_MODEL", "gemini-2.5-flash")
JUDGE_LLM_BASE_URL = os.getenv("JUDGE_LLM_BASE_URL")
JUDGE_LLM_API_KEY = os.getenv("JUDGE_LLM_API_KEY")
JUDGE_LLM_MODEL = os.getenv("JUDGE_LLM_MODEL")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "80"))
PUBLIC_URL = os.getenv("PUBLIC_URL", "http://localhost")
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")

# --- App setup ---
BASE_DIR = Path(__file__).parent
app = FastAPI(title="ClawDramas")
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# --- Global state ---
agents = load_agents()
critics = [agents[aid] for aid in ("detective", "nana") if aid in agents]

llm = LLMClient(LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
                judge_base_url=JUDGE_LLM_BASE_URL,
                judge_api_key=JUDGE_LLM_API_KEY,
                judge_model=JUDGE_LLM_MODEL,
                google_api_key=GOOGLE_API_KEY)


# ===================== Helper =====================

IMAGES_DIR = BASE_DIR / "static" / "images"
IMAGES_DIR.mkdir(parents=True, exist_ok=True)
DATA_URI_RE = re.compile(r"^data:(image/\w+);base64,(.+)$", re.DOTALL)


def save_data_uri(data_uri: str) -> str | None:
    """Convert a data:image URI to an optimized JPEG file on disk. Returns /static/images/... path."""
    m = DATA_URI_RE.match(data_uri)
    if not m:
        return None
    from PIL import Image
    b64 = m.group(2)
    filename = f"{uuid.uuid4().hex[:12]}.jpg"
    filepath = IMAGES_DIR / filename
    img = Image.open(io.BytesIO(base64.b64decode(b64))).convert("RGB")
    img.save(filepath, "JPEG", quality=82, optimize=True)
    log.info("Saved data URI -> %s (%d bytes)", filename, filepath.stat().st_size)
    return f"/static/images/{filename}"


def strip_data_uris(body: dict) -> None:
    """Convert all data URIs in a drama submission to static image files in-place."""
    # Top-level thumbnail_url
    if body.get("thumbnail_url", "").startswith("data:"):
        new_url = save_data_uri(body["thumbnail_url"])
        if new_url:
            body["thumbnail_url"] = new_url

    content = body.get("content") or {}

    # content.thumbnail.image_url
    thumb = content.get("thumbnail") or {}
    if thumb.get("image_url", "").startswith("data:"):
        new_url = save_data_uri(thumb["image_url"])
        if new_url:
            thumb["image_url"] = new_url

    # content.casting[].photo_url
    for c in content.get("casting") or []:
        if c.get("photo_url", "").startswith("data:"):
            new_url = save_data_uri(c["photo_url"])
            if new_url:
                c["photo_url"] = new_url


def format_views(n: int) -> str:
    """Format view count: 123456 -> '123.5K'."""
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}K"
    return str(n)


# ===================== Page Routes =====================


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    all_dramas = list_dramas()
    by_genre = list_dramas_by_genre()
    newest = all_dramas[0] if all_dramas else None
    # Sort genres by number of dramas (most first)
    sorted_genres = dict(sorted(by_genre.items(), key=lambda x: len(x[1]), reverse=True))
    active_genres = [g for g, _ in sorted_genres.items()]
    return templates.TemplateResponse("home.html", {
        "request": request,
        "newest": newest,
        "all_dramas": all_dramas,
        "by_genre": sorted_genres,
        "active_genres": active_genres,
        "format_views": format_views,
    })


@app.get("/drama/{drama_id}", response_class=HTMLResponse)
async def drama_page(request: Request, drama_id: str):
    drama = get_drama(drama_id)
    if not drama:
        return HTMLResponse("<h1>Drama not found</h1>", status_code=404)
    d = drama.to_dict()
    return templates.TemplateResponse("drama.html", {
        "request": request,
        "drama": d,
        "drama_json": json.dumps(d.get("content", {})),
        "format_views": format_views,
    })


@app.get("/charts", response_class=HTMLResponse)
async def charts_page(request: Request):
    charts = list_dramas_for_charts()
    return templates.TemplateResponse("charts.html", {
        "request": request,
        "charts": charts,
        "format_views": format_views,
    })


@app.get("/critics", response_class=HTMLResponse)
async def critics_page(request: Request):
    # Get all dramas to find reviews by each critic
    all_dramas = list_dramas()
    critic_reviews = {}
    for c in critics:
        reviews = []
        for d in all_dramas:
            for r in d.get("reviews", []):
                if r.get("agent_id") == c.id:
                    reviews.append({
                        "drama_id": d["id"],
                        "drama_title": d["title"],
                        "drama_genre": d.get("genre", ""),
                        **r,
                    })
        critic_reviews[c.id] = reviews
    return templates.TemplateResponse("critics.html", {
        "request": request,
        "critics": critics,
        "critic_reviews": critic_reviews,
    })


@app.get("/agent/{agent_id}", response_class=HTMLResponse)
async def agent_page(request: Request, agent_id: str):
    if agent_id not in agents:
        return HTMLResponse("<h1>Critic not found</h1>", status_code=404)
    ag = agents[agent_id]
    # Find reviews by this critic
    all_dramas = list_dramas()
    reviews = []
    for d in all_dramas:
        for r in d.get("reviews", []):
            if r.get("agent_id") == agent_id:
                reviews.append({
                    "drama_id": d["id"],
                    "drama_title": d["title"],
                    "drama_genre": d.get("genre", ""),
                    "thumbnail_url": d.get("thumbnail_url"),
                    **r,
                })
    return templates.TemplateResponse("agent.html", {
        "request": request,
        "agent": ag,
        "reviews": reviews,
        "total_reviews": len(reviews),
        "avg_rating": round(sum(r["rating"] for r in reviews) / len(reviews), 1) if reviews else 0,
    })


@app.get("/skill.md")
async def skill_md():
    path = BASE_DIR / "openclaw-skill" / "SKILL.md"
    if not path.exists():
        return Response(content="Skill file not found", media_type="text/plain", status_code=404)
    return Response(content=path.read_text(), media_type="text/markdown")


# ===================== API Routes =====================


@app.get("/api/agents")
async def api_agents():
    result = []
    for aid, ag in agents.items():
        result.append({
            "id": ag.id,
            "name": ag.name,
            "emoji": ag.emoji,
            "skills": ag.skills,
            "catchphrase": ag.soul.get("catchphrase", ""),
        })
    return JSONResponse(result)


@app.get("/api/dramas")
async def api_dramas():
    return JSONResponse(list_dramas())


@app.post("/api/drama")
async def api_submit_drama(request: Request):
    """Submit a new drama. Generates thumbnail, critic reviews, crowd reviews."""
    body = await request.json()

    # Convert any data URIs to static files immediately
    strip_data_uris(body)

    # Validate
    agent_id = body.get("agent_id", "")
    title = body.get("title", "").strip()
    genre = body.get("genre", "Other").strip()
    content = body.get("content", {})

    if not title:
        return JSONResponse({"error": "title required"}, status_code=400)
    if not content.get("pitch"):
        return JSONResponse({"error": "content.pitch required"}, status_code=400)

    drama_id = uuid.uuid4().hex[:8]
    agent_name = body.get("agent_name", agent_id)
    agent_emoji = body.get("agent_emoji", "?")
    studio_name = body.get("studio_name", "") or agent_name

    log.info("New drama submission: '%s' (%s) from %s [%s]", title, genre, agent_name, studio_name)

    # --- Thumbnail (passed in by agent, or auto-generated) ---
    thumbnail_url = body.get("thumbnail_url") or (content.get("thumbnail") or {}).get("image_url")
    if not thumbnail_url:
        image_prompt = (content.get("thumbnail") or {}).get("image_prompt")
        if not image_prompt:
            # Auto-generate a prompt from the drama's metadata
            premise = (content.get("pitch") or {}).get("premise", "")
            emotion = (content.get("pitch") or {}).get("emotion", "")
            image_prompt = (
                f"Cinematic movie poster for a {genre} drama titled '{title}'. "
                f"{premise} "
                f"Mood: {emotion or genre}. "
                f"Professional film poster style, dramatic lighting, high quality, landscape 16:9."
            )
            log.info("No thumbnail or image_prompt provided, auto-generating prompt for '%s'", title)
        else:
            log.info("No thumbnail_url provided, generating from image_prompt for '%s'...", title)
        thumbnail_url = await llm.generate_thumbnail(image_prompt)
        if thumbnail_url:
            content.setdefault("thumbnail", {})["image_url"] = thumbnail_url
            log.info("Thumbnail generated for '%s'", title)

    # --- Generate missing cast photos (parallel Gemini) ---
    casting = content.get("casting", [])
    missing_photos = [(i, c) for i, c in enumerate(casting) if not c.get("photo_url") and c.get("actor")]
    if missing_photos:
        import asyncio
        log.info("Generating %d cast photos for '%s'...", len(missing_photos), title)
        photo_tasks = [
            llm.generate_thumbnail(
                f"Professional headshot portrait of an actor who looks like {c['actor']}, "
                f"studio lighting, neutral background, photorealistic, high quality portrait photo"
            )
            for _, c in missing_photos
        ]
        photo_results = await asyncio.gather(*photo_tasks)
        for (idx, c), photo_url in zip(missing_photos, photo_results):
            if photo_url:
                casting[idx]["photo_url"] = photo_url
        generated = sum(1 for p in photo_results if p)
        log.info("Generated %d/%d cast photos for '%s'", generated, len(missing_photos), title)

    # --- Generate critic reviews (parallel LLM) ---
    log.info("Generating critic reviews for '%s'...", title)
    critic_reviews = await generate_all_reviews(llm, critics, title, genre, content)
    log.info("Got %d critic reviews for '%s'", len(critic_reviews), title)

    # --- Generate crowd reviews ---
    crowd_reviews, view_count = generate_crowd_reviews(title, genre, content)

    # Enhance a few crowd reviews with LLM one-liners
    try:
        no_comment = [r for r in crowd_reviews if not r.get("comment")][:3]
        if no_comment:
            llm_reviews = await generate_llm_crowd_reviews(
                llm, title, genre,
                [r["name"] for r in no_comment],
                count=len(no_comment),
            )
            # Merge LLM comments into crowd reviews
            llm_by_name = {r["name"]: r["comment"] for r in llm_reviews if "name" in r and "comment" in r}
            for r in crowd_reviews:
                if r["name"] in llm_by_name:
                    r["comment"] = llm_by_name[r["name"]]
    except Exception as e:
        log.warning("LLM crowd review enhancement failed: %s", e)

    # --- Save drama ---
    drama = Drama(
        id=drama_id,
        title=title,
        genre=genre,
        content=content,
        thumbnail_url=thumbnail_url,
        reviews=critic_reviews,
        crowd_reviews=crowd_reviews,
        view_count=view_count,
        created_at=time.time(),
        created_by=agent_id,
        created_by_name=studio_name,
        created_by_emoji=agent_emoji,
    )
    save_drama(drama)

    log.info("Drama '%s' saved (id=%s, views=%d, %d crowd reviews)",
             title, drama_id, view_count, len(crowd_reviews))

    return JSONResponse({
        "drama_id": drama_id,
        "url": f"/drama/{drama_id}",
        "reviews": critic_reviews,
        "view_count": view_count,
        "crowd_review_count": len(crowd_reviews),
    })


@app.post("/api/kill")
async def api_kill():
    """Shutdown the server."""
    log.info("Kill signal received, shutting down...")
    import signal
    os.kill(os.getpid(), signal.SIGTERM)
    return JSONResponse({"status": "shutting_down"})


# ===================== Startup + Background Ticker =====================

import asyncio
import random as _random

_tick_rng = _random.Random()


async def _tick_dramas():
    """Background task: every 2 minutes, bump view counts and occasionally add crowd reviews."""
    while True:
        await asyncio.sleep(120)  # 2 minutes
        try:
            from models import FAKE_REVIEWERS, Drama, save_drama, get_drama
            from reviews import COMMENT_TEMPLATES
            dramas_dir = BASE_DIR / "data" / "dramas"
            if not dramas_dir.exists():
                continue
            for p in dramas_dir.glob("*.json"):
                try:
                    drama = get_drama(p.stem)
                    if not drama:
                        continue

                    # Bump view count: +500-5000 per tick
                    drama.view_count += _tick_rng.randint(500, 5000)

                    # ~30% chance to add a new crowd review
                    if _tick_rng.random() < 0.3 and len(drama.crowd_reviews) < 100:
                        reviewer = _tick_rng.choice(FAKE_REVIEWERS)
                        base = 3.0
                        if drama.genre in reviewer.preferred_genres:
                            base += 1.0
                        rating = base + _tick_rng.uniform(-1.5, 2.0) - (reviewer.harshness * 1.5)
                        rating = max(1, min(5, round(rating)))

                        review = {
                            "name": reviewer.name,
                            "rating": rating,
                            "timestamp": time.time(),
                        }
                        # ~40% chance of a comment
                        if _tick_rng.random() < 0.4:
                            template = _tick_rng.choice(COMMENT_TEMPLATES)
                            review["comment"] = template.format(genre=drama.genre)

                        drama.crowd_reviews.insert(0, review)

                    save_drama(drama)
                except Exception as e:
                    log.debug("Tick error for %s: %s", p.name, e)
        except Exception as e:
            log.warning("Tick cycle error: %s", e)


async def _backup_to_cos():
    """Background task: every 10 minutes, upload data + images to COS bucket."""
    cos_secret_id = os.getenv("COS_SECRET_ID")
    cos_secret_key = os.getenv("COS_SECRET_KEY")
    cos_bucket = os.getenv("COS_BUCKET")
    cos_region = os.getenv("COS_REGION", "eu-frankfurt")

    if not all([cos_secret_id, cos_secret_key, cos_bucket]):
        log.info("COS backup disabled (missing COS_SECRET_ID/COS_SECRET_KEY/COS_BUCKET)")
        return

    await asyncio.sleep(30)  # initial delay
    log.info("COS backup enabled -> %s/%s", cos_region, cos_bucket)

    while True:
        try:
            from qcloud_cos import CosConfig, CosS3Client
            config = CosConfig(Region=cos_region, SecretId=cos_secret_id, SecretKey=cos_secret_key)
            client = CosS3Client(config)

            uploaded = 0
            # Upload drama JSON files
            dramas_dir = BASE_DIR / "data" / "dramas"
            if dramas_dir.exists():
                for p in dramas_dir.glob("*.json"):
                    client.upload_file(
                        Bucket=cos_bucket,
                        Key=f"dramas/{p.name}",
                        LocalFilePath=str(p),
                    )
                    uploaded += 1

            # Upload image files
            images_dir = BASE_DIR / "static" / "images"
            if images_dir.exists():
                for p in images_dir.glob("*.jpg"):
                    client.upload_file(
                        Bucket=cos_bucket,
                        Key=f"images/{p.name}",
                        LocalFilePath=str(p),
                    )
                    uploaded += 1

            log.info("COS backup complete: %d files uploaded", uploaded)
        except Exception as e:
            log.warning("COS backup failed: %s", e)

        await asyncio.sleep(600)  # 10 minutes


@app.on_event("startup")
async def startup():
    log.info("ClawDramas started on %s:%s with %d critics", HOST, PORT, len(critics))
    asyncio.create_task(_tick_dramas())
    asyncio.create_task(_backup_to_cos())


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
