# DevGrow

A local web app for developer self-improvement. Track what you study, retain knowledge with spaced repetition flashcards, log technical decisions, and earn XP as you build habits.

All data is stored locally in `~/.devgrow/devgrow.db`. No account, no cloud, no tracking.

---

## Install

```bash
cd devgrow
pip install -e .
```

---

## Run

```bash
devgrow
```

Opens at **http://127.0.0.1:7331**

```bash
# Custom host/port
devgrow serve --host 0.0.0.0 --port 8080

# Auto-open browser
devgrow serve --open

# Auto-reload on code changes (dev mode)
devgrow serve --reload
```

---

## Pages

### Dashboard `/`

Your daily home base.

- **Level + XP bar** — progress toward the next level
- **Streak** — consecutive days with any activity (study, review, or decision)
- **Cards due** — how many flashcards need review today, with a direct link to Quiz
- **Activity chart** — 30-day XP history as a bar chart
- **Quick actions** — links to Review, Learn, and Decisions

### Learn `/learn`

Manage topics, study sessions, and flashcards.

**Topics sidebar (left)**
- Click a topic to see its sessions and cards
- `+ Topic` to add a new topic
- `✕` to delete a topic (also deletes its sessions and cards)

**Right panel (two tabs)**

| Tab | What it shows |
|-----|--------------|
| Sessions | All study sessions for the selected topic — date, duration, notes |
| Flashcards | All cards for the topic — question, answer, next review date, ease factor |

**Actions**
- `Log Session` — record time spent studying a topic (+20 XP)
- `+ Card` — add a flashcard to the selected topic (+5 XP)
- `✕` on a card row — delete that card

### Quiz `/quiz`

Spaced repetition flashcard review using the **SM-2 algorithm**.

1. A card is shown face-down (question only)
2. Click **Flip Card** or press `Space` to reveal the answer
3. Rate your recall honestly with 1–5:

| Key | Rating | Meaning |
|-----|--------|---------|
| `1` | Blackout | No recall at all |
| `2` | Wrong | Wrong, but familiar after seeing answer |
| `3` | Hard | Correct with significant effort |
| `4` | Good | Correct after a hesitation |
| `5` | Easy | Perfect, immediate recall |

The algorithm schedules each card's next review based on your rating:
- Rating ≥ 3 → interval grows (6 days → then multiplied by ease factor each time)
- Rating < 3 → resets to 1 day, ease factor decreases
- A card is **mastered** once its interval reaches 21+ days

Each reviewed card earns **+10 XP**.

### Decisions `/decisions`

An engineering decision journal. Log what you decided, why, and what happened.

**Adding a decision**
- **Title** — short description (required)
- **Context** — what problem were you solving?
- **Options considered** — one per line
- **Choice made** — what you picked (required)
- **Reasoning** — why this option?

**Marking outcomes** (after time has passed)
- Select a decision and click **Mark Outcome**
- Rate it: Good / Neutral / Bad
- Add a reflection on what you learned

Decisions with no outcome marked show a **Pending** badge and a yellow counter in the nav.

Logging a decision earns **+15 XP**. Marking an outcome earns **+10 XP**.

### Stats `/stats`

Full overview of your growth.

- Level progress and XP breakdown
- Flashcard mastery rate (mastered = interval ≥ 21 days)
- 30-day activity heatmap
- Per-topic session and card counts
- Study time totals

---

## XP System

| Action | XP |
|--------|----|
| Log a study session | +20 |
| Review a flashcard | +10 |
| Add a flashcard | +5 |
| Log a decision | +15 |
| Mark a decision outcome | +10 |
| 7-day streak bonus | +50 × (streak ÷ 7) |

**Levels** follow a triangular progression — each level requires more XP than the last:
- Level 1 → 2: 100 XP
- Level 2 → 3: 150 XP
- Level 3 → 4: 200 XP
- Level n → n+1: `(n + 2) × 50` XP

**Streak bonus** fires automatically when you cross a 7-day multiple (7, 14, 21, …) for the first time on that day.

---

## Nav indicators

| Indicator | Meaning |
|-----------|---------|
| 🔥 Nd | Current streak in days |
| Lv N | Current level |
| NNN XP | Total XP earned |
| Purple badge on Quiz | Cards due for review today |
| Yellow badge on Decisions | Decisions with no outcome yet |

---

## CLI commands

```bash
# Start the server (default)
devgrow
devgrow serve --open --port 7331

# Quick stats in the terminal
devgrow stats

# Export all data to JSON (for backup or migration)
devgrow export
devgrow export -o my_backup.json

# Wipe everything and start fresh (asks for confirmation twice)
devgrow reset
```

---

## Data

All data lives in `~/.devgrow/devgrow.db` — a plain SQLite file.

| Table | What it stores |
|-------|----------------|
| `topics` | Topic names |
| `sessions` | Study sessions with duration and notes |
| `flashcards` | Cards with SM-2 state (ease factor, interval, next review) |
| `reviews` | Every individual card review with rating |
| `decisions` | Technical decisions with context, options, choice, outcome |
| `xp_log` | Every XP event with reason and timestamp |
| `activity` | Daily XP totals (powers streak and chart) |

**Backup:**
```bash
# JSON export
devgrow export

# Or just copy the SQLite file
cp ~/.devgrow/devgrow.db ~/Desktop/devgrow_backup.db
```

**Health check** (useful for scripting):
```bash
curl http://localhost:7331/health
# {"status":"ok","due_today":3,"streak":5}
```

---

## How to use it daily

A simple routine that works:

**Morning (2 min)**
1. Open DevGrow
2. Check the Dashboard — how many cards due?
3. Go to Quiz and clear the review queue

**After studying something**
1. Go to Learn → select or add the topic
2. Click Log Session — enter time and a note on what you covered
3. Add 1–3 flashcards for the key concepts

**After making a technical decision**
1. Go to Decisions → + Decision
2. Fill in context, options, choice, reasoning
3. Come back weeks/months later to mark the outcome and reflect

**Once a week**
1. Check Stats — which topics are you ignoring?
2. Open Decisions — any outcomes to mark?
3. Review your mastered cards count

---

## Project layout

```
devgrow/
├── pyproject.toml
└── devgrow/
    ├── db.py          # SQLite layer — all queries, XP logic, streak
    ├── sm2.py         # SM-2 spaced repetition algorithm (pure function)
    ├── web.py         # FastAPI routes
    ├── cli.py         # Click CLI (serve, stats, export, reset)
    ├── static/
    │   ├── style.css  # Dark theme, all styling
    │   └── app.js     # Toast, modal, card flip, tabs
    └── templates/
        ├── base.html
        ├── dashboard.html
        ├── learn.html
        ├── quiz.html
        ├── decisions.html
        └── stats.html
```

---

## Tech stack

| Layer | Choice | Why |
|-------|--------|-----|
| Backend | FastAPI + Uvicorn | Fast, async, clean |
| Templates | Jinja2 | Server-rendered, no build step |
| Database | SQLite | Zero config, local, portable |
| Frontend | Vanilla CSS + JS | No framework, no bundler, easy to modify |
| Algorithm | SM-2 | Battle-tested spaced repetition |
| CLI | Click | Clean commands, auto-help |
