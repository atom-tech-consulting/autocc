"""Output formatting for taskflow."""
import json

from .models import Task


def format_table(tasks: list[Task]) -> str:
    """Format tasks as an ASCII table."""
    if not tasks:
        return "No tasks found."
    header = f"{'ID':<8} {'Title':<30} {'Priority':<10} {'Status':<12} {'Due':<12}"
    sep = "-" * len(header)
    lines = [header, sep]
    for t in tasks:
        due = t.due_date or "-"
        lines.append(
            f"{t.id:<8} {t.title[:30]:<30} {t.priority.value:<10}"
            f" {t.status.value:<12} {due:<12}"
        )
    return "\n".join(lines)


def format_json(tasks: list[Task]) -> str:
    """Format tasks as a JSON array."""
    return json.dumps([t.to_dict() for t in tasks], indent=2)


def format_csv(tasks: list[Task]) -> str:
    """Format tasks as CSV."""
    # BUG: not implemented
    raise NotImplementedError("CSV export is not yet implemented")
