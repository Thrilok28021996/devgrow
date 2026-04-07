import json as _json
import random
from contextlib import asynccontextmanager
from datetime import date as _date
from pathlib import Path
from typing import Annotated, Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from devgrow import db
from devgrow.sm2 import update_sm2

BASE_DIR = Path(__file__).parent


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    yield


app = FastAPI(title="DevGrow", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")
templates.env.filters["from_json"] = _json.loads
templates.env.filters["tojson"] = _json.dumps


def _next_action(s: dict) -> dict:
    """Return the single highest-priority action the user should take right now."""
    if s["due_today"] > 0:
        return {"label": f"Review {s['due_today']} card{'s' if s['due_today'] != 1 else ''} due today",
                "url": "/quiz", "cta": "Start Quiz"}
    if not s["review_this_week"] and _date.today().weekday() >= 3:
        return {"label": "Week's almost over — write your weekly review",
                "url": "/review", "cta": "Write Review"}
    if s["pending_outcomes"] > 0:
        return {"label": f"{s['pending_outcomes']} decision{'s' if s['pending_outcomes'] != 1 else ''} need{'s' if s['pending_outcomes'] == 1 else ''} an outcome",
                "url": "/decisions", "cta": "Mark Outcome"}
    if s.get("overdue_goals", 0) > 0:
        return {"label": f"{s['overdue_goals']} goal{'s are' if s['overdue_goals'] != 1 else ' is'} past their target date",
                "url": "/goals", "cta": "View Goals"}
    return {}


def ctx(page: str, nav_stats: Optional[dict] = None, **kwargs) -> dict:
    return {"page": page, "nav_stats": nav_stats or db.get_stats(), **kwargs}


def redirect(url: str, flash: str = "") -> RedirectResponse:
    dest = f"{url}{'&' if '?' in url else '?'}flash={flash}" if flash else url
    return RedirectResponse(dest, status_code=303)


# ── Demo data ──────────────────────────────────────────────────────────────────

@app.post("/demo")
async def load_demo():
    db.load_demo_data()
    return redirect("/", "Demo data loaded — explore away!")


# ── Health ─────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    s = db.get_stats()
    return {"status": "ok", "due_today": s["due_today"], "streak": s["streak"]}


# ── Dashboard ──────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def dashboard(request: Request):
    stats = db.get_stats()
    activity = db.get_activity_last_n_days(30)
    next_action = _next_action(stats)
    return templates.TemplateResponse(request, "dashboard.html",
        ctx("dashboard", nav_stats=stats, stats=stats, activity=activity,
            next_action=next_action, today_weekday=_date.today().weekday()))


# ── Search ─────────────────────────────────────────────────────────────────────

@app.get("/search", response_class=HTMLResponse)
async def search(request: Request, q: str = ""):
    q = q.strip()
    results = db.search(q) if q else {"cards": [], "decisions": [], "sessions": []}
    total = sum(len(v) for v in results.values())
    return templates.TemplateResponse(request, "search.html",
        ctx("search", search_q=q, results=results, total=total, q=q))


# ── Learn ──────────────────────────────────────────────────────────────────────

@app.get("/learn", response_class=HTMLResponse)
async def learn(request: Request, topic: Optional[int] = None, flash: str = ""):
    topics = db.get_topics()
    selected_topic = None
    sessions: list = []
    cards: list = []
    readings: list = []

    if topic:
        selected_topic = next((t for t in topics if t["id"] == topic), None)
    if not selected_topic and topics:
        selected_topic = topics[0]
        topic = selected_topic["id"]

    if selected_topic:
        sessions = db.get_sessions(topic)
        cards = db.get_cards_by_topic(topic)
        readings = db.get_readings(topic)

    return templates.TemplateResponse(request, "learn.html",
        ctx("learn", topics=topics, selected_topic=selected_topic,
            sessions=sessions, cards=cards, readings=readings, flash=flash))


@app.post("/learn/topics")
async def add_topic(name: Annotated[str, Form()]):
    name = name.strip()
    if name:
        db.add_topic(name)
    return redirect("/learn", "Topic added")


@app.post("/learn/topics/{topic_id}/delete")
async def delete_topic(topic_id: int):
    db.delete_topic(topic_id)
    return redirect("/learn", "Topic deleted")


@app.post("/learn/topics/{topic_id}/proficiency")
async def set_proficiency(topic_id: int, level: Annotated[int, Form()]):
    db.set_topic_proficiency(topic_id, level)
    return redirect(f"/learn?topic={topic_id}")


@app.post("/learn/sessions")
async def log_session(
    topic_id: Annotated[int, Form()],
    duration_minutes: Annotated[int, Form()],
    notes: Annotated[str, Form()] = "",
):
    if duration_minutes > 0:
        db.add_session(topic_id, duration_minutes, notes.strip())
    return redirect(f"/learn?topic={topic_id}", "Session logged +20 XP")


@app.post("/learn/cards")
async def add_card(
    topic_id: Annotated[int, Form()],
    front: Annotated[str, Form()],
    back: Annotated[str, Form()],
):
    front, back = front.strip(), back.strip()
    if front and back:
        db.add_card(topic_id, front, back)
    return redirect(f"/learn?topic={topic_id}", "Card added +5 XP")


@app.post("/learn/cards/{card_id}/edit")
async def edit_card(
    card_id: int,
    topic_id: Annotated[int, Form()],
    front: Annotated[str, Form()],
    back: Annotated[str, Form()],
):
    front, back = front.strip(), back.strip()
    if front and back:
        db.update_card(card_id, front, back)
    return redirect(f"/learn?topic={topic_id}", "Card updated")


@app.post("/learn/cards/{card_id}/delete")
async def delete_card(card_id: int, topic_id: Annotated[int, Form()]):
    db.delete_card(card_id)
    return redirect(f"/learn?topic={topic_id}", "Card deleted")


# ── Quiz ───────────────────────────────────────────────────────────────────────

@app.get("/quiz", response_class=HTMLResponse)
async def quiz(request: Request, flash: str = "", limit: int = 0, shuffle: int = 0):
    cards = list(db.get_cards_due())
    if shuffle:
        random.shuffle(cards)
    if limit > 0:
        cards = cards[:limit]
    card = cards[0] if cards else None
    remaining = len(cards)
    return templates.TemplateResponse(request, "quiz.html",
        ctx("quiz", card=card, remaining=remaining, flash=flash, limit=limit, shuffle=shuffle))


@app.post("/quiz/review")
async def submit_review(
    card_id: Annotated[int, Form()],
    rating: Annotated[int, Form()],
    limit: Annotated[int, Form()] = 0,
    shuffle: Annotated[int, Form()] = 0,
):
    cards = db.get_cards_due()
    card = next((c for c in cards if c["id"] == card_id), None)
    if card:
        new_ef, new_interval, next_review = update_sm2(
            card["ease_factor"], card["interval"], rating
        )
        db.add_review(card_id, rating, new_ef, new_interval, next_review)
    params = []
    if limit > 0:
        params.append(f"limit={limit}")
    if shuffle:
        params.append(f"shuffle={shuffle}")
    qs = ("?" + "&".join(params)) if params else ""
    return redirect(f"/quiz{qs}", f"Reviewed +{db.XP_REVIEW_CARD} XP")


# ── Decisions ──────────────────────────────────────────────────────────────────

@app.get("/decisions", response_class=HTMLResponse)
async def decisions(request: Request, selected: Optional[int] = None, flash: str = ""):
    all_decisions = db.get_decisions()
    detail = None
    if selected:
        detail = next((d for d in all_decisions if d["id"] == selected), None)
    elif all_decisions:
        detail = all_decisions[0]
        selected = detail["id"]

    return templates.TemplateResponse(request, "decisions.html",
        ctx("decisions", decisions=all_decisions, detail=detail,
            selected_id=selected, flash=flash))


@app.post("/decisions")
async def add_decision(
    title: Annotated[str, Form()],
    context: Annotated[str, Form()] = "",
    options: Annotated[str, Form()] = "",
    choice: Annotated[str, Form()] = "",
    reasoning: Annotated[str, Form()] = "",
):
    title, choice = title.strip(), choice.strip()
    if title and choice:
        options_list = [o.strip() for o in options.splitlines() if o.strip()]
        did = db.add_decision(title, context.strip(), options_list, choice, reasoning.strip())
        return redirect(f"/decisions?selected={did}", "Decision logged +15 XP")
    return redirect("/decisions")


@app.post("/decisions/{decision_id}/edit")
async def edit_decision(
    decision_id: int,
    title: Annotated[str, Form()],
    context: Annotated[str, Form()] = "",
    options: Annotated[str, Form()] = "",
    choice: Annotated[str, Form()] = "",
    reasoning: Annotated[str, Form()] = "",
):
    title, choice = title.strip(), choice.strip()
    if title and choice:
        options_list = [o.strip() for o in options.splitlines() if o.strip()]
        db.update_decision(decision_id, title, context.strip(), options_list, choice, reasoning.strip())
    return redirect(f"/decisions?selected={decision_id}", "Decision updated")


@app.post("/decisions/{decision_id}/outcome")
async def mark_outcome(
    decision_id: int,
    outcome: Annotated[int, Form()],
    reflection: Annotated[str, Form()] = "",
):
    db.update_decision_outcome(decision_id, outcome, reflection.strip())
    return redirect(f"/decisions?selected={decision_id}", "Outcome recorded +10 XP")


# ── Goals ──────────────────────────────────────────────────────────────────────

@app.get("/goals", response_class=HTMLResponse)
async def goals(request: Request, flash: str = ""):
    all_goals = db.get_goals()
    topics = db.get_topics()
    return templates.TemplateResponse(request, "goals.html",
        ctx("goals", goals=all_goals, topics=topics, today=_date.today().isoformat(), flash=flash))


@app.post("/goals")
async def add_goal(
    title: Annotated[str, Form()],
    description: Annotated[str, Form()] = "",
    topic_id: Annotated[str, Form()] = "",
    target_date: Annotated[str, Form()] = "",
):
    title = title.strip()
    if title:
        tid = int(topic_id) if topic_id.isdigit() else None
        db.add_goal(title, description.strip(), tid, target_date)
    return redirect("/goals", "Goal added +5 XP")


@app.post("/goals/{goal_id}/complete")
async def complete_goal(goal_id: int):
    db.update_goal_status(goal_id, "completed")
    return redirect("/goals", "Goal completed! +25 XP")


@app.post("/goals/{goal_id}/drop")
async def drop_goal(goal_id: int):
    db.update_goal_status(goal_id, "dropped")
    return redirect("/goals", "Goal dropped")


@app.post("/goals/{goal_id}/delete")
async def delete_goal(goal_id: int):
    db.delete_goal(goal_id)
    return redirect("/goals", "Goal deleted")


# ── Review (weekly + lessons) ──────────────────────────────────────────────────

@app.get("/review", response_class=HTMLResponse)
async def review(request: Request, flash: str = ""):
    week_date = db.get_current_week_date()
    current_review = db.get_weekly_review(week_date)
    past_reviews = db.get_past_reviews(8)
    lessons = db.get_lessons()
    topics = db.get_topics()
    return templates.TemplateResponse(request, "review.html",
        ctx("review", week_date=week_date, current_review=current_review,
            past_reviews=past_reviews, lessons=lessons, topics=topics, flash=flash))


@app.post("/review")
async def save_review(
    week_date: Annotated[str, Form()],
    went_well: Annotated[str, Form()] = "",
    blocked: Annotated[str, Form()] = "",
    key_lesson: Annotated[str, Form()] = "",
    next_focus: Annotated[str, Form()] = "",
    habit_goal: Annotated[str, Form()] = "",
):
    existing = db.get_weekly_review(week_date)
    db.upsert_weekly_review(
        week_date, went_well.strip(), blocked.strip(),
        key_lesson.strip(), next_focus.strip(), habit_goal.strip(),
        is_new=(existing is None),
    )
    msg = "Review saved +30 XP" if not existing else "Review updated"
    return redirect("/review", msg)


@app.post("/lessons")
async def add_lesson(
    title: Annotated[str, Form()],
    what_happened: Annotated[str, Form()] = "",
    root_cause: Annotated[str, Form()] = "",
    lesson: Annotated[str, Form()] = "",
    topic_id: Annotated[str, Form()] = "",
    severity: Annotated[str, Form()] = "minor",
):
    title = title.strip()
    lesson = lesson.strip()
    if title and lesson:
        tid = int(topic_id) if topic_id.isdigit() else None
        db.add_lesson(title, what_happened.strip(), root_cause.strip(), lesson, tid, severity)
    return redirect("/review", "Lesson logged +10 XP")


@app.post("/lessons/{lesson_id}/delete")
async def delete_lesson(lesson_id: int):
    db.delete_lesson(lesson_id)
    return redirect("/review", "Lesson deleted")


# ── Readings ───────────────────────────────────────────────────────────────────

@app.post("/learn/readings")
async def add_reading(
    topic_id: Annotated[int, Form()],
    title: Annotated[str, Form()],
    url: Annotated[str, Form()] = "",
    rtype: Annotated[str, Form()] = "article",
    notes: Annotated[str, Form()] = "",
):
    title = title.strip()
    if title:
        db.add_reading(title, url.strip(), rtype, topic_id, notes.strip())
    return redirect(f"/learn?topic={topic_id}", "Reading added +5 XP")


@app.post("/learn/readings/{reading_id}/status")
async def update_reading(
    reading_id: int,
    status: Annotated[str, Form()],
    topic_id: Annotated[int, Form()],
):
    db.update_reading_status(reading_id, status)
    msg = "Marked as done +10 XP" if status == "done" else "Status updated"
    return redirect(f"/learn?topic={topic_id}", msg)


@app.post("/learn/readings/{reading_id}/delete")
async def delete_reading(reading_id: int, topic_id: Annotated[int, Form()]):
    db.delete_reading(reading_id)
    return redirect(f"/learn?topic={topic_id}", "Reading deleted")


# ── Stats ──────────────────────────────────────────────────────────────────────

@app.get("/stats", response_class=HTMLResponse)
async def stats(request: Request):
    s = db.get_stats()
    activity = db.get_activity_last_n_days(30)
    topics = db.get_topics()
    return templates.TemplateResponse(request, "stats.html",
        ctx("stats", nav_stats=s, stats=s, activity=activity, topics=topics))
