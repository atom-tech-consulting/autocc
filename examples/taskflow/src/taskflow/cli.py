"""Click CLI for taskflow."""
import uuid

import click

from .formatters import format_csv, format_json, format_table
from .models import Priority, Status, Task
from .store import TaskStore
from .validators import validate_due_date, validate_priority, validate_title


@click.group()
@click.option("--db", default="tasks.json", help="Path to task database file")
@click.pass_context
def cli(ctx, db):
    ctx.ensure_object(dict)
    ctx.obj["store"] = TaskStore(db)


@cli.command()
@click.argument("title")
@click.option("--desc", default="", help="Task description")
@click.option("--priority", default="medium", help="Priority: low/medium/high/critical")
@click.option("--due", default=None, help="Due date (YYYY-MM-DD)")
@click.pass_context
def add(ctx, title, desc, priority, due):
    """Add a new task."""
    if not validate_title(title):
        click.echo("Error: title must be 1-200 non-blank characters", err=True)
        raise SystemExit(1)
    if not validate_priority(priority):
        click.echo(f"Error: invalid priority '{priority}'", err=True)
        raise SystemExit(1)
    if due and not validate_due_date(due):
        click.echo(f"Error: invalid or past due date '{due}'", err=True)
        raise SystemExit(1)

    task = Task(
        id=uuid.uuid4().hex[:8],
        title=title,
        description=desc,
        priority=Priority(priority),
        due_date=due,
    )
    ctx.obj["store"].add(task)
    click.echo(f"Added task {task.id}: {task.title}")


@cli.command("list")
@click.option("--status", default=None, help="Filter by status")
@click.option("--priority", default=None, help="Filter by priority")
@click.option("--format", "fmt", default="table", help="Output format: table/json/csv")
@click.pass_context
def list_tasks(ctx, status, priority, fmt):
    """List tasks."""
    tasks = ctx.obj["store"].list(status=status, priority=priority)
    if fmt == "json":
        click.echo(format_json(tasks))
    elif fmt == "csv":
        click.echo(format_csv(tasks))
    else:
        click.echo(format_table(tasks))


@cli.command()
@click.argument("task_id")
@click.pass_context
def complete(ctx, task_id):
    """Mark a task as done."""
    from datetime import datetime

    task = ctx.obj["store"].update(
        task_id, status=Status.DONE,
        completed_at=datetime.now().isoformat(),
    )
    if task:
        click.echo(f"Completed task {task_id}: {task.title}")
    else:
        click.echo(f"Error: task {task_id} not found", err=True)
        raise SystemExit(1)


@cli.command()
@click.argument("task_id")
@click.pass_context
def delete(ctx, task_id):
    """Delete a task."""
    if ctx.obj["store"].delete(task_id):
        click.echo(f"Deleted task {task_id}")
    else:
        click.echo(f"Error: task {task_id} not found", err=True)
        raise SystemExit(1)


@cli.command()
@click.option("--format", "fmt", default="json", help="Export format: json/csv")
@click.pass_context
def export(ctx, fmt):
    """Export all tasks."""
    tasks = ctx.obj["store"].list()
    if fmt == "csv":
        click.echo(format_csv(tasks))
    else:
        click.echo(format_json(tasks))
