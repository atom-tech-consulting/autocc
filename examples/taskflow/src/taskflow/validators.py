"""Input validation for taskflow."""
from datetime import date, datetime

from .models import Priority


def validate_title(title: str) -> bool:
    """Title must be 1-200 chars and not blank."""
    if not title or not title.strip():
        return False
    return 1 <= len(title.strip()) <= 200


def validate_due_date(date_str: str) -> bool:
    """Due date must be YYYY-MM-DD format and today or future. None means no due date."""
    # BUG: does not handle None — crashes with AttributeError
    try:
        parsed = datetime.strptime(date_str.strip(), "%Y-%m-%d").date()
        return parsed >= date.today()
    except ValueError:
        return False


def validate_priority(value: str) -> bool:
    """Must be a valid Priority value."""
    try:
        Priority(value)
        return True
    except ValueError:
        return False
