import json
import socket
import webbrowser
from datetime import date, datetime, timedelta
from pathlib import Path

import click
import uvicorn

from devgrow import db


def _lan_ip() -> str:
    """Best-effort local network IP (not loopback)."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


@click.group(invoke_without_command=True)
@click.pass_context
def main(ctx: click.Context) -> None:
    """DevGrow — level up as a developer."""
    if ctx.invoked_subcommand is None:
        ctx.invoke(desktop)


@main.command()
def desktop() -> None:
    """Launch the DevGrow desktop app (requires PySide6)."""
    try:
        from devgrow.desktop import main as _desktop_main
    except ImportError:
        click.echo("PySide6 is required for the desktop app.")
        click.echo("  pip install 'devgrow[desktop]'  or  pip install PySide6")
        raise SystemExit(1)
    _desktop_main()


@main.command()
@click.option("--host", default="127.0.0.1", show_default=True)
@click.option("--port", default=7331, show_default=True)
@click.option("--reload", is_flag=True, default=False, help="Auto-reload on file changes")
@click.option("--open", "open_browser", is_flag=True, default=False, help="Open browser on start")
@click.option("--lan", is_flag=True, default=False, help="Bind to all interfaces (share on local network)")
def serve(host: str, port: int, reload: bool, open_browser: bool, lan: bool) -> None:
    """Start the DevGrow web server."""
    db.init_db()
    if lan:
        host = "0.0.0.0"
        lan_ip = _lan_ip()
        click.echo(f"DevGrow running at http://127.0.0.1:{port}")
        click.echo(f"  Local network:  http://{lan_ip}:{port}")
    else:
        click.echo(f"DevGrow running at http://{host}:{port}")
    url = f"http://127.0.0.1:{port}"
    if open_browser:
        webbrowser.open(url)
    uvicorn.run("devgrow.web:app", host=host, port=port, reload=reload)


@main.command()
def stats() -> None:
    """Print a quick stats summary."""
    db.init_db()
    s = db.get_stats()
    click.echo(f"Level {s['level']}  |  {s['total_xp']} XP  |  {s['streak']} day streak")
    click.echo(f"Progress: {s['xp_in_level']}/{s['xp_for_next']} XP to Level {s['level'] + 1}")
    click.echo(f"Cards: {s['total_cards']} total, {s['mastered_cards']} mastered, {s['due_today']} due")
    click.echo(f"Sessions: {s['total_sessions']}  |  Time: {s['total_minutes'] // 60}h {s['total_minutes'] % 60}m")
    click.echo(f"Decisions: {s['total_decisions']}  |  Pending outcome: {s['pending_outcomes']}")


@main.command()
@click.option("--output", "-o", default="", help="Output file path (default: devgrow_YYYYMMDD.json)")
def export(output: str) -> None:
    """Export all data to a JSON file for backup."""
    db.init_db()
    out_path = Path(output) if output else Path(f"devgrow_{datetime.now().strftime('%Y%m%d')}.json")

    with db.get_conn() as conn:
        topics    = [dict(r) for r in conn.execute("SELECT * FROM topics ORDER BY name").fetchall()]
        sessions  = [dict(r) for r in conn.execute("SELECT * FROM sessions ORDER BY created_at").fetchall()]
        cards     = [dict(r) for r in conn.execute("SELECT * FROM flashcards ORDER BY created_at").fetchall()]
        reviews   = [dict(r) for r in conn.execute("SELECT * FROM reviews ORDER BY reviewed_at").fetchall()]
        decisions = [dict(r) for r in conn.execute("SELECT * FROM decisions ORDER BY created_at").fetchall()]
        xp_log    = [dict(r) for r in conn.execute("SELECT * FROM xp_log ORDER BY created_at").fetchall()]

    data = {
        "exported_at": datetime.now().isoformat(),
        "stats": db.get_stats(),
        "topics": topics,
        "sessions": sessions,
        "flashcards": cards,
        "reviews": reviews,
        "decisions": decisions,
        "xp_log": xp_log,
    }

    out_path.write_text(json.dumps(data, indent=2, default=str))
    click.echo(f"Exported {len(topics)} topics, {len(cards)} cards, "
               f"{len(decisions)} decisions → {out_path}")


@main.command("import")
@click.argument("file", type=click.Path(exists=True, dir_okay=False, path_type=Path))
def import_data(file: Path) -> None:
    """Import data from a JSON export file."""
    db.init_db()
    try:
        data = json.loads(file.read_text())
    except (json.JSONDecodeError, OSError) as e:
        click.echo(f"Error reading file: {e}", err=True)
        raise SystemExit(1)

    s = db.get_stats()
    if s["total_cards"] > 0 or s["total_sessions"] > 0 or s["total_decisions"] > 0:
        click.echo("Warning: existing data detected. Importing will merge data; XP may be duplicated.")
        click.confirm("Continue?", abort=True)

    counts = db.import_data(data)
    click.echo(
        f"Imported {counts['topics']} topics, {counts['sessions']} sessions, "
        f"{counts['cards']} cards, {counts['decisions']} decisions"
    )


@main.command()
def digest() -> None:
    """Print today's learning summary — add to shell profile or cron."""
    db.init_db()
    s = db.get_stats()

    today = date.today()
    day_name = today.strftime("%A %b %-d")

    # Streak indicator
    streak_icon = "🔥" if s["streak"] > 0 else "  "
    streak_text = f"{s['streak']} day streak" if s["streak"] > 0 else "no streak yet"

    # Review status
    review_status = "✓ written" if s["review_this_week"] else "✗ not written yet"

    click.echo("")
    click.echo(f"  DevGrow — {day_name}")
    click.echo(f"  {'─' * 30}")
    click.echo(f"  {streak_icon} Streak:    {streak_text}")
    click.echo(f"  📇 Due today:  {s['due_today']} card{'s' if s['due_today'] != 1 else ''}")

    # Sessions this week
    with db.get_conn() as conn:
        week_start = (today - timedelta(days=today.weekday())).isoformat()
        week_rows = conn.execute(
            "SELECT COUNT(*) as cnt, COALESCE(SUM(duration_minutes),0) as mins "
            "FROM sessions WHERE created_at >= ?", (week_start,)
        ).fetchone()
    sessions_this_week = week_rows["cnt"]
    mins_this_week = week_rows["mins"]
    click.echo(f"  📚 This week:  {sessions_this_week} session{'s' if sessions_this_week != 1 else ''}"
               f" · {mins_this_week // 60}h {mins_this_week % 60}m")

    click.echo(f"  📝 Review:     {review_status}")
    click.echo(f"  ⭐ Level {s['level']}   {s['xp_in_level']}/{s['xp_for_next']} XP to next level")

    # Nudge
    click.echo("")
    if s["due_today"] > 0:
        click.echo(f"  → {s['due_today']} cards waiting. Run: devgrow serve")
    elif not s["review_this_week"] and today.weekday() >= 3:  # Thu+
        click.echo("  → Week's almost done. Write your weekly review.")
    elif s["pending_outcomes"] > 0:
        click.echo(f"  → {s['pending_outcomes']} decision{'s' if s['pending_outcomes'] != 1 else ''} need an outcome.")
    elif sessions_this_week == 0:
        click.echo("  → No sessions logged this week yet.")
    else:
        click.echo("  → All caught up. Keep the streak going.")
    click.echo("")


@main.command("log")
@click.argument("topic")
@click.argument("minutes", type=int)
@click.argument("notes", default="")
def log_session(topic: str, minutes: int, notes: str) -> None:
    """Quick-log a study session from the terminal.

    \b
    Examples:
      devgrow log "System Design" 45
      devgrow log "System Design" 45 "Reviewed consistent hashing"
      devgrow log python 30 "Finished chapter 4"
    """
    db.init_db()

    # Find topic by name (case-insensitive prefix match)
    topics = db.get_topics()
    matched = [t for t in topics if t["name"].lower().startswith(topic.lower())]

    if not matched:
        # Offer to create it
        click.echo(f'No topic matching "{topic}".')
        existing = [t["name"] for t in topics]
        if existing:
            click.echo("  Existing topics: " + ", ".join(existing))
        if click.confirm(f'  Create new topic "{topic}"?'):
            topic_id = db.add_topic(topic)
            click.echo(f'  Created topic "{topic}".')
        else:
            raise SystemExit(0)
    elif len(matched) > 1:
        click.echo(f'Ambiguous — "{topic}" matches: {", ".join(t["name"] for t in matched)}')
        raise SystemExit(1)
    else:
        topic_id = matched[0]["id"]
        topic = matched[0]["name"]

    if minutes <= 0:
        click.echo("Minutes must be > 0.", err=True)
        raise SystemExit(1)

    db.add_session(topic_id, minutes, notes)
    s = db.get_stats()
    click.echo(f'  ✓ {minutes}m logged under "{topic}" +{db.XP_LOG_SESSION} XP')
    click.echo(f'  Level {s["level"]} · {s["xp_in_level"]}/{s["xp_for_next"]} XP · {s["streak"]} day streak')


@main.command()
def reset() -> None:
    """Delete ALL data and start fresh. Cannot be undone."""
    click.confirm("This will permanently delete all your DevGrow data. Are you sure?", abort=True)
    click.confirm("Really sure? This cannot be undone.", abort=True)
    db_path = db.DB_PATH
    for suffix in ("", "-wal", "-shm"):
        p = db_path.parent / (db_path.name + suffix)
        if p.exists():
            p.unlink()
    click.echo(f"Deleted {db_path}")
    db.init_db()
    click.echo("Fresh database created.")
