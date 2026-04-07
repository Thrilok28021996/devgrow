"""
SM-2 spaced repetition algorithm.

Rating scale (1–5):
  1 = complete blackout, wrong answer
  2 = wrong, but familiar after seeing answer
  3 = correct with significant difficulty
  4 = correct after a hesitation
  5 = perfect, immediate recall

Intervals:
  - First review: 1 day
  - Second review: 6 days
  - Subsequent: previous_interval * ease_factor

Ease factor starts at 2.5, min 1.3.
"""

from datetime import date, timedelta


def update_sm2(
    ease_factor: float,
    interval: int,
    rating: int,
) -> tuple[float, int, date]:
    """
    Returns (new_ease_factor, new_interval, next_review_date).
    rating must be 1–5.
    """
    # EF always updates regardless of pass/fail
    new_ef = ease_factor + (0.1 - (5 - rating) * (0.08 + (5 - rating) * 0.02))
    new_ef = max(1.3, new_ef)

    if rating < 3:
        # Failed — reset interval but keep updated (lower) EF
        new_interval = 1
    else:
        if interval <= 1:
            new_interval = 6
        else:
            new_interval = round(interval * new_ef)

    next_review = date.today() + timedelta(days=new_interval)
    return new_ef, new_interval, next_review


