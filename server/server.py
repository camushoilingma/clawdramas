"""ClawDramas — Netflix-style drama catalog server."""

from __future__ import annotations

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
from debate import Debater
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

debater = Debater(LLM_BASE_URL, LLM_API_KEY, LLM_MODEL,
                  judge_base_url=JUDGE_LLM_BASE_URL,
                  judge_api_key=JUDGE_LLM_API_KEY,
                  judge_model=JUDGE_LLM_MODEL,
                  google_api_key=GOOGLE_API_KEY)


# ===================== Helper =====================


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
    return templates.TemplateResponse("home.html", {
        "request": request,
        "newest": newest,
        "by_genre": by_genre,
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

    # --- Thumbnail (passed in by agent, or generated from image_prompt) ---
    thumbnail_url = body.get("thumbnail_url") or (content.get("thumbnail") or {}).get("image_url")
    if not thumbnail_url:
        image_prompt = (content.get("thumbnail") or {}).get("image_prompt")
        if image_prompt:
            log.info("No thumbnail_url provided, generating from image_prompt for '%s'...", title)
            thumbnail_url = await debater.generate_thumbnail(image_prompt)
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
            debater.generate_thumbnail(
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
    critic_reviews = await generate_all_reviews(debater, critics, title, genre, content)
    log.info("Got %d critic reviews for '%s'", len(critic_reviews), title)

    # --- Generate crowd reviews ---
    crowd_reviews, view_count = generate_crowd_reviews(title, genre, content)

    # Enhance a few crowd reviews with LLM one-liners
    try:
        no_comment = [r for r in crowd_reviews if not r.get("comment")][:3]
        if no_comment:
            llm_reviews = await generate_llm_crowd_reviews(
                debater, title, genre,
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


# ===================== Startup =====================


@app.on_event("startup")
async def startup():
    log.info("ClawDramas started on %s:%s with %d critics", HOST, PORT, len(critics))


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
