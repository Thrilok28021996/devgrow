import math
import os
import sqlite3
import json
from datetime import date, timedelta
from pathlib import Path
from typing import Optional

_data_dir = Path(os.environ["DEVGROW_DATA"]) if "DEVGROW_DATA" in os.environ else Path.home() / ".devgrow"
DB_PATH = _data_dir / "devgrow.db"

# XP rewards
XP_ADD_CARD = 5
XP_REVIEW_CARD = 10
XP_LOG_SESSION = 20
XP_ADD_DECISION = 15
XP_MARK_OUTCOME = 10
XP_STREAK_BONUS = 50
XP_ADD_GOAL = 5
XP_COMPLETE_GOAL = 25
XP_LOG_LESSON = 10
XP_ADD_READING = 5
XP_DONE_READING = 10
XP_WEEKLY_REVIEW = 30


def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db() -> None:
    with get_conn() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS topics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                color TEXT DEFAULT '#7C3AED',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                duration_minutes INTEGER NOT NULL,
                notes TEXT,
                created_at TEXT DEFAULT CURRENT_DATE
            );

            CREATE TABLE IF NOT EXISTS flashcards (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                front TEXT NOT NULL,
                back TEXT NOT NULL,
                ease_factor REAL DEFAULT 2.5,
                interval INTEGER DEFAULT 1,
                next_review TEXT DEFAULT (date('now')),
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                card_id INTEGER REFERENCES flashcards(id) ON DELETE CASCADE,
                rating INTEGER NOT NULL,
                reviewed_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS decisions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                context TEXT,
                options TEXT,
                choice TEXT NOT NULL,
                reasoning TEXT,
                outcome INTEGER,
                reflection TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                outcome_at TEXT
            );

            CREATE TABLE IF NOT EXISTS xp_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                amount INTEGER NOT NULL,
                reason TEXT NOT NULL,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                activity_date TEXT NOT NULL UNIQUE,
                xp_earned INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS goals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                description TEXT,
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                target_date TEXT,
                status TEXT DEFAULT 'active',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            );

            CREATE TABLE IF NOT EXISTS readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                url TEXT,
                type TEXT DEFAULT 'article',
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                notes TEXT,
                status TEXT DEFAULT 'queue',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                finished_at TEXT
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT NOT NULL,
                what_happened TEXT,
                root_cause TEXT,
                lesson TEXT NOT NULL,
                topic_id INTEGER REFERENCES topics(id) ON DELETE SET NULL,
                severity TEXT DEFAULT 'minor',
                created_at TEXT DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS weekly_reviews (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                week_date TEXT NOT NULL UNIQUE,
                went_well TEXT,
                blocked TEXT,
                key_lesson TEXT,
                next_focus TEXT,
                habit_goal TEXT,
                created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                updated_at TEXT DEFAULT CURRENT_TIMESTAMP
            );
        """)
    # Migrations for pre-existing databases
    _run_migrations(conn)


def _run_migrations(conn: sqlite3.Connection) -> None:
    for stmt in [
        "ALTER TABLE topics ADD COLUMN proficiency INTEGER DEFAULT 1",
    ]:
        try:
            conn.execute(stmt)
        except sqlite3.OperationalError:
            pass  # Column already exists


# ── XP + Activity ─────────────────────────────────────────────────────────────

def _log_xp(conn: sqlite3.Connection, amount: int, reason: str) -> None:
    today = date.today().isoformat()
    conn.execute("INSERT INTO xp_log (amount, reason) VALUES (?, ?)", (amount, reason))
    conn.execute("""
        INSERT INTO activity (activity_date, xp_earned) VALUES (?, ?)
        ON CONFLICT(activity_date) DO UPDATE SET xp_earned = xp_earned + ?
    """, (today, amount, amount))
    # Award streak bonus when crossing a 7-day multiple for the first time today
    streak = _compute_streak(conn)
    if streak > 0 and streak % 7 == 0:
        already = conn.execute(
            "SELECT COUNT(*) FROM xp_log WHERE reason LIKE 'Streak bonus%' AND created_at >= ?",
            (today,),
        ).fetchone()[0]
        if not already:
            bonus = XP_STREAK_BONUS * (streak // 7)
            conn.execute(
                "INSERT INTO xp_log (amount, reason) VALUES (?, ?)",
                (bonus, f"Streak bonus — {streak} day streak!"),
            )
            conn.execute("""
                INSERT INTO activity (activity_date, xp_earned) VALUES (?, ?)
                ON CONFLICT(activity_date) DO UPDATE SET xp_earned = xp_earned + ?
            """, (today, bonus, bonus))


def _compute_streak(conn: sqlite3.Connection) -> int:
    rows = conn.execute(
        "SELECT activity_date FROM activity ORDER BY activity_date DESC"
    ).fetchall()
    if not rows:
        return 0
    dates = [date.fromisoformat(r["activity_date"]) for r in rows]
    today = date.today()
    if dates[0] < today - timedelta(days=1):
        return 0
    streak = 1
    for i in range(1, len(dates)):
        if dates[i - 1] - dates[i] == timedelta(days=1):
            streak += 1
        else:
            break
    return streak


def get_level(xp: int) -> tuple[int, int, int]:
    """Returns (level, xp_in_current_level, xp_needed_for_next_level).

    Threshold for level n (0-indexed completed levels): 25n² + 75n.
    Inverse: n = floor((-75 + sqrt(5625 + 100*xp)) / 50)
    """
    if xp <= 0:
        return 1, 0, 100
    n = int((-75 + math.sqrt(5625 + 100 * xp)) / 50)
    xp_start = 25 * n * n + 75 * n
    xp_next  = 25 * (n + 1) * (n + 1) + 75 * (n + 1)
    return n + 1, xp - xp_start, xp_next - xp_start


def get_streak() -> int:
    with get_conn() as conn:
        return _compute_streak(conn)


def get_activity_last_n_days(n: int = 30) -> list[dict]:
    """Returns list of {date, xp_earned} for last n days (fills gaps with 0)."""
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT activity_date, xp_earned FROM activity WHERE activity_date >= date('now', ?)",
            (f"-{n} days",),
        ).fetchall()
    by_date = {r["activity_date"]: r["xp_earned"] for r in rows}
    result = []
    for i in range(n - 1, -1, -1):
        d = (date.today() - timedelta(days=i)).isoformat()
        result.append({"date": d, "xp_earned": by_date.get(d, 0)})
    return result


# ── Topics ─────────────────────────────────────────────────────────────────────

def get_topics() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT t.*, COUNT(DISTINCT s.id) as session_count, COUNT(DISTINCT f.id) as card_count "
            "FROM topics t "
            "LEFT JOIN sessions s ON s.topic_id = t.id "
            "LEFT JOIN flashcards f ON f.topic_id = t.id "
            "GROUP BY t.id ORDER BY t.name"
        ).fetchall()


def add_topic(name: str) -> int:
    with get_conn() as conn:
        cur = conn.execute("INSERT INTO topics (name) VALUES (?)", (name,))
        return cur.lastrowid


def delete_topic(topic_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM topics WHERE id = ?", (topic_id,))


# ── Sessions ───────────────────────────────────────────────────────────────────

def get_sessions(topic_id: Optional[int] = None) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if topic_id is not None:
            return conn.execute(
                "SELECT s.*, t.name as topic_name FROM sessions s "
                "LEFT JOIN topics t ON t.id = s.topic_id "
                "WHERE s.topic_id = ? ORDER BY s.created_at DESC",
                (topic_id,),
            ).fetchall()
        return conn.execute(
            "SELECT s.*, t.name as topic_name FROM sessions s "
            "LEFT JOIN topics t ON t.id = s.topic_id "
            "ORDER BY s.created_at DESC LIMIT 50"
        ).fetchall()


def add_session(topic_id: int, duration_minutes: int, notes: str = "") -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO sessions (topic_id, duration_minutes, notes) VALUES (?, ?, ?)",
            (topic_id, duration_minutes, notes),
        )
        _log_xp(conn, XP_LOG_SESSION, f"Logged {duration_minutes}m study session")
        return cur.lastrowid


# ── Flashcards ─────────────────────────────────────────────────────────────────

def get_cards_due() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT f.*, t.name as topic_name FROM flashcards f "
            "LEFT JOIN topics t ON t.id = f.topic_id "
            "WHERE f.next_review <= date('now') ORDER BY f.next_review"
        ).fetchall()


def get_cards_by_topic(topic_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM flashcards WHERE topic_id = ? ORDER BY created_at DESC",
            (topic_id,),
        ).fetchall()


def add_card(topic_id: int, front: str, back: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO flashcards (topic_id, front, back) VALUES (?, ?, ?)",
            (topic_id, front, back),
        )
        _log_xp(conn, XP_ADD_CARD, "Added flashcard")
        return cur.lastrowid


def add_review(card_id: int, rating: int, ease_factor: float, interval: int, next_review: date) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE flashcards SET ease_factor=?, interval=?, next_review=? WHERE id=?",
            (ease_factor, interval, next_review.isoformat(), card_id),
        )
        conn.execute(
            "INSERT INTO reviews (card_id, rating) VALUES (?, ?)",
            (card_id, rating),
        )
        _log_xp(conn, XP_REVIEW_CARD, "Reviewed flashcard")


def delete_card(card_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM flashcards WHERE id = ?", (card_id,))


# ── Decisions ──────────────────────────────────────────────────────────────────

def get_decisions(pending_only: bool = False) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if pending_only:
            return conn.execute(
                "SELECT * FROM decisions WHERE outcome IS NULL ORDER BY created_at DESC"
            ).fetchall()
        return conn.execute(
            "SELECT * FROM decisions ORDER BY created_at DESC"
        ).fetchall()


def add_decision(title: str, context: str, options: list[str], choice: str, reasoning: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO decisions (title, context, options, choice, reasoning) VALUES (?, ?, ?, ?, ?)",
            (title, context, json.dumps(options), choice, reasoning),
        )
        _log_xp(conn, XP_ADD_DECISION, f"Logged decision: {title}")
        return cur.lastrowid


def update_decision_outcome(decision_id: int, outcome: int, reflection: str) -> None:
    """outcome: 1=good, 2=neutral, 3=bad"""
    with get_conn() as conn:
        conn.execute(
            "UPDATE decisions SET outcome=?, reflection=?, outcome_at=datetime('now') WHERE id=?",
            (outcome, reflection, decision_id),
        )
        _log_xp(conn, XP_MARK_OUTCOME, "Marked decision outcome")


# ── Stats ──────────────────────────────────────────────────────────────────────

def load_demo_data() -> None:
    """Populate with example data. No-op if any topics already exist."""
    with get_conn() as conn:
        if conn.execute("SELECT COUNT(*) FROM topics").fetchone()[0] > 0:
            return

    t1 = add_topic("System Design")
    t2 = add_topic("LLM / AI")

    add_session(t1, 45,
        "Reviewed CAP theorem. Key: most databases sacrifice consistency for availability in practice.")
    add_session(t2, 60,
        "Worked through Attention Is All You Need. Transformers = self-attention + positional encoding.")

    for front, back in [
        ("What is consistent hashing?",
         "Distributes data across nodes so only K/N keys need remapping when a node changes. Uses a hash ring."),
        ("CAP theorem — what are the three properties?",
         "Consistency, Availability, Partition tolerance. A distributed system can only guarantee two at once."),
        ("Horizontal vs vertical scaling — key difference?",
         "Vertical: bigger machine. Horizontal: more machines. Horizontal scales better but requires the system to handle distribution."),
    ]:
        add_card(t1, front, back)

    for front, back in [
        ("What is RAG?",
         "Retrieval-Augmented Generation — augments an LLM's context window with fetched documents to reduce hallucinations."),
        ("What does an embedding model produce?",
         "A dense vector (e.g., 1536 floats) representing text semantics. Similar meaning → similar vectors → similarity search works."),
    ]:
        add_card(t2, front, back)

    add_decision(
        "Use SQLite over Postgres for a local tool",
        "Building a developer tool that runs on one machine. No multi-user access needed.",
        ["SQLite", "Postgres", "DynamoDB"],
        "SQLite",
        "Zero config, single file, no server process. Perfect for local tools where you control the environment.",
    )
    add_goal(
        "Build a working RAG pipeline from scratch",
        "Implement chunking, embedding, vector store, and retrieval without using a framework.",
        t2,
        (date.today() + timedelta(days=30)).isoformat(),
    )
    add_reading(
        "Attention Is All You Need",
        "https://arxiv.org/abs/1706.03762",
        "paper", t2,
        "The original Transformer paper — foundational reading for understanding LLMs.",
    )


def search(q: str) -> dict:
    """Search across flashcards, decisions, and sessions. Returns grouped results."""
    like = f"%{q}%"
    with get_conn() as conn:
        cards = conn.execute(
            "SELECT f.*, t.name as topic_name FROM flashcards f "
            "LEFT JOIN topics t ON t.id = f.topic_id "
            "WHERE f.front LIKE ? OR f.back LIKE ? ORDER BY f.created_at DESC LIMIT 30",
            (like, like),
        ).fetchall()
        decisions = conn.execute(
            "SELECT * FROM decisions "
            "WHERE title LIKE ? OR context LIKE ? OR choice LIKE ? OR reasoning LIKE ? "
            "ORDER BY created_at DESC LIMIT 30",
            (like, like, like, like),
        ).fetchall()
        sessions = conn.execute(
            "SELECT s.*, t.name as topic_name FROM sessions s "
            "LEFT JOIN topics t ON t.id = s.topic_id "
            "WHERE s.notes LIKE ? AND (s.notes IS NOT NULL AND s.notes != '') "
            "ORDER BY s.created_at DESC LIMIT 30",
            (like,),
        ).fetchall()
    return {"cards": list(cards), "decisions": list(decisions), "sessions": list(sessions)}


def import_data(data: dict) -> dict:
    """Import a JSON export. Returns counts of imported rows.
    Safe to run on a fresh DB; importing into an existing DB may result in duplicate XP.
    """
    counts = {"topics": 0, "sessions": 0, "cards": 0, "decisions": 0}
    with get_conn() as conn:
        # Topics — insert by name; map old IDs to new IDs
        topic_id_map: dict[int, int] = {}
        for t in data.get("topics", []):
            try:
                cur = conn.execute(
                    "INSERT INTO topics (name, color) VALUES (?, ?)",
                    (t["name"], t.get("color", "#7C3AED")),
                )
                new_id = cur.lastrowid
                counts["topics"] += 1
            except sqlite3.IntegrityError:
                row = conn.execute("SELECT id FROM topics WHERE name=?", (t["name"],)).fetchone()
                new_id = row["id"] if row else None
            if new_id:
                topic_id_map[t["id"]] = new_id

        # Sessions
        for s in data.get("sessions", []):
            conn.execute(
                "INSERT INTO sessions (topic_id, duration_minutes, notes, created_at) VALUES (?, ?, ?, ?)",
                (topic_id_map.get(s.get("topic_id")), s["duration_minutes"],
                 s.get("notes", ""), s.get("created_at", "")),
            )
            counts["sessions"] += 1

        # Flashcards
        for f in data.get("flashcards", []):
            conn.execute(
                "INSERT INTO flashcards (topic_id, front, back, ease_factor, interval, next_review, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (topic_id_map.get(f.get("topic_id")), f["front"], f["back"],
                 f.get("ease_factor", 2.5), f.get("interval", 1),
                 f.get("next_review", date.today().isoformat()), f.get("created_at", "")),
            )
            counts["cards"] += 1

        # Decisions
        for d in data.get("decisions", []):
            conn.execute(
                "INSERT INTO decisions (title, context, options, choice, reasoning, "
                "outcome, reflection, created_at, outcome_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (d["title"], d.get("context", ""), d.get("options", "[]"),
                 d["choice"], d.get("reasoning", ""), d.get("outcome"),
                 d.get("reflection", ""), d.get("created_at", ""), d.get("outcome_at")),
            )
            counts["decisions"] += 1

        # XP log — restore as-is (for backup/restore into a fresh DB)
        for x in data.get("xp_log", []):
            conn.execute(
                "INSERT INTO xp_log (amount, reason, created_at) VALUES (?, ?, ?)",
                (x["amount"], x["reason"], x.get("created_at", "")),
            )

        # Activity — merge by date, keeping the higher XP value
        for a in data.get("activity", []):
            conn.execute("""
                INSERT INTO activity (activity_date, xp_earned) VALUES (?, ?)
                ON CONFLICT(activity_date) DO UPDATE SET xp_earned = MAX(xp_earned, excluded.xp_earned)
            """, (a["activity_date"], a["xp_earned"]))

    return counts


def get_stats() -> dict:
    with get_conn() as conn:
        total_cards      = conn.execute("SELECT COUNT(*) FROM flashcards").fetchone()[0]
        mastered         = conn.execute("SELECT COUNT(*) FROM flashcards WHERE interval >= 21").fetchone()[0]
        due_today        = conn.execute("SELECT COUNT(*) FROM flashcards WHERE next_review <= date('now')").fetchone()[0]
        total_sessions   = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        total_minutes    = conn.execute("SELECT COALESCE(SUM(duration_minutes), 0) FROM sessions").fetchone()[0]
        total_decisions  = conn.execute("SELECT COUNT(*) FROM decisions").fetchone()[0]
        pending_outcomes = conn.execute("SELECT COUNT(*) FROM decisions WHERE outcome IS NULL").fetchone()[0]
        total_reviews    = conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0]
        active_goals     = conn.execute("SELECT COUNT(*) FROM goals WHERE status='active'").fetchone()[0]
        overdue_goals    = conn.execute(
            "SELECT COUNT(*) FROM goals WHERE status='active' AND target_date < date('now')"
        ).fetchone()[0]
        current_week = (date.today() - timedelta(days=date.today().weekday())).isoformat()
        review_this_week = conn.execute(
            "SELECT COUNT(*) FROM weekly_reviews WHERE week_date=?", (current_week,)
        ).fetchone()[0]
        xp               = conn.execute("SELECT COALESCE(SUM(amount), 0) FROM xp_log").fetchone()[0]
        streak           = _compute_streak(conn)

    level, xp_in_level, xp_for_next = get_level(xp)
    return {
        "total_xp": xp,
        "level": level,
        "xp_in_level": xp_in_level,
        "xp_for_next": xp_for_next,
        "streak": streak,
        "total_cards": total_cards,
        "mastered_cards": mastered,
        "due_today": due_today,
        "total_sessions": total_sessions,
        "total_minutes": total_minutes,
        "total_decisions": total_decisions,
        "pending_outcomes": pending_outcomes,
        "total_reviews": total_reviews,
        "active_goals": active_goals,
        "overdue_goals": overdue_goals,
        "review_this_week": review_this_week > 0,
    }


# ── Topics: proficiency ────────────────────────────────────────────────────────

def set_topic_proficiency(topic_id: int, level: int) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE topics SET proficiency=? WHERE id=?", (max(1, min(5, level)), topic_id))


# ── Flashcards: edit + history ─────────────────────────────────────────────────

def update_card(card_id: int, front: str, back: str) -> None:
    with get_conn() as conn:
        conn.execute("UPDATE flashcards SET front=?, back=? WHERE id=?", (front, back, card_id))


def get_card_reviews(card_id: int) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT rating, reviewed_at FROM reviews WHERE card_id=? ORDER BY reviewed_at DESC LIMIT 20",
            (card_id,),
        ).fetchall()


# ── Decisions: edit ────────────────────────────────────────────────────────────

def update_decision(decision_id: int, title: str, context: str, options: list[str],
                    choice: str, reasoning: str) -> None:
    with get_conn() as conn:
        conn.execute(
            "UPDATE decisions SET title=?, context=?, options=?, choice=?, reasoning=? WHERE id=?",
            (title, context, json.dumps(options), choice, reasoning, decision_id),
        )


# ── Goals ──────────────────────────────────────────────────────────────────────

def get_goals() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT g.*, t.name as topic_name FROM goals g "
            "LEFT JOIN topics t ON t.id = g.topic_id "
            "ORDER BY CASE g.status WHEN 'active' THEN 0 WHEN 'completed' THEN 1 ELSE 2 END, "
            "g.target_date ASC NULLS LAST, g.created_at DESC"
        ).fetchall()


def add_goal(title: str, description: str, topic_id: Optional[int], target_date: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO goals (title, description, topic_id, target_date) VALUES (?, ?, ?, ?)",
            (title, description, topic_id or None, target_date or None),
        )
        _log_xp(conn, XP_ADD_GOAL, f"Set goal: {title}")
        return cur.lastrowid


def update_goal_status(goal_id: int, status: str) -> None:
    with get_conn() as conn:
        if status == "completed":
            conn.execute(
                "UPDATE goals SET status='completed', completed_at=datetime('now') WHERE id=?",
                (goal_id,),
            )
            _log_xp(conn, XP_COMPLETE_GOAL, "Completed a goal")
        else:
            conn.execute("UPDATE goals SET status=? WHERE id=?", (status, goal_id))


def delete_goal(goal_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM goals WHERE id=?", (goal_id,))


# ── Reading log ────────────────────────────────────────────────────────────────

def get_readings(topic_id: Optional[int] = None) -> list[sqlite3.Row]:
    with get_conn() as conn:
        if topic_id:
            return conn.execute(
                "SELECT r.*, t.name as topic_name FROM readings r "
                "LEFT JOIN topics t ON t.id = r.topic_id "
                "WHERE r.topic_id=? "
                "ORDER BY CASE r.status WHEN 'reading' THEN 0 WHEN 'queue' THEN 1 ELSE 2 END, r.created_at DESC",
                (topic_id,),
            ).fetchall()
        return conn.execute(
            "SELECT r.*, t.name as topic_name FROM readings r "
            "LEFT JOIN topics t ON t.id = r.topic_id "
            "ORDER BY CASE r.status WHEN 'reading' THEN 0 WHEN 'queue' THEN 1 ELSE 2 END, r.created_at DESC"
        ).fetchall()


def add_reading(title: str, url: str, rtype: str, topic_id: Optional[int], notes: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO readings (title, url, type, topic_id, notes) VALUES (?, ?, ?, ?, ?)",
            (title, url, rtype, topic_id or None, notes),
        )
        _log_xp(conn, XP_ADD_READING, f"Added reading: {title}")
        return cur.lastrowid


def update_reading_status(reading_id: int, status: str) -> None:
    with get_conn() as conn:
        if status == "done":
            conn.execute(
                "UPDATE readings SET status='done', finished_at=datetime('now') WHERE id=?",
                (reading_id,),
            )
            _log_xp(conn, XP_DONE_READING, "Finished a reading")
        else:
            conn.execute("UPDATE readings SET status=? WHERE id=?", (status, reading_id))


def delete_reading(reading_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM readings WHERE id=?", (reading_id,))


# ── Lessons log ────────────────────────────────────────────────────────────────

def get_lessons() -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT l.*, t.name as topic_name FROM lessons l "
            "LEFT JOIN topics t ON t.id = l.topic_id "
            "ORDER BY l.created_at DESC"
        ).fetchall()


def add_lesson(title: str, what_happened: str, root_cause: str, lesson: str,
               topic_id: Optional[int], severity: str) -> int:
    with get_conn() as conn:
        cur = conn.execute(
            "INSERT INTO lessons (title, what_happened, root_cause, lesson, topic_id, severity) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (title, what_happened, root_cause, lesson, topic_id or None, severity),
        )
        _log_xp(conn, XP_LOG_LESSON, f"Logged lesson: {title}")
        return cur.lastrowid


def delete_lesson(lesson_id: int) -> None:
    with get_conn() as conn:
        conn.execute("DELETE FROM lessons WHERE id=?", (lesson_id,))


# ── Weekly review ──────────────────────────────────────────────────────────────

def get_current_week_date() -> str:
    """ISO date of the Monday starting the current week."""
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    return monday.isoformat()


def get_weekly_review(week_date: str) -> Optional[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM weekly_reviews WHERE week_date=?", (week_date,)
        ).fetchone()


def get_past_reviews(limit: int = 10) -> list[sqlite3.Row]:
    with get_conn() as conn:
        return conn.execute(
            "SELECT * FROM weekly_reviews ORDER BY week_date DESC LIMIT ?", (limit,)
        ).fetchall()


def upsert_weekly_review(week_date: str, went_well: str, blocked: str,
                          key_lesson: str, next_focus: str, habit_goal: str,
                          is_new: bool) -> None:
    with get_conn() as conn:
        conn.execute("""
            INSERT INTO weekly_reviews (week_date, went_well, blocked, key_lesson, next_focus, habit_goal)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(week_date) DO UPDATE SET
                went_well=excluded.went_well, blocked=excluded.blocked,
                key_lesson=excluded.key_lesson, next_focus=excluded.next_focus,
                habit_goal=excluded.habit_goal, updated_at=datetime('now')
        """, (week_date, went_well, blocked, key_lesson, next_focus, habit_goal))
        if is_new:
            _log_xp(conn, XP_WEEKLY_REVIEW, "Completed weekly review")
