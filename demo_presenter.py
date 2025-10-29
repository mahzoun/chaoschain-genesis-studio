"""
Shared presentation helpers for ChaosChain demo scripts.

This module provides a larger, more legible wait bar and a small helper
for rendering consistent step panels across demos.
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Dict, Iterable, List, Optional, Sequence, Union

from rich.console import Console, Group, RenderableType
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeElapsedColumn,
)
from rich.table import Table
from rich.text import Text


class WaitBar:
    """Display a pulsing progress bar while long-running work completes."""

    def __init__(self, console: Console, description: str, *, bar_width: int = 46):
        self.console = console
        self.description = description
        self.bar_width = bar_width
        self.elapsed: Optional[float] = None
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._start: Optional[float] = None
        self._progress: Optional[Progress] = None
        self._task_id: Optional[int] = None

    def __enter__(self):
        self._progress = Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold white]{task.description}", justify="left"),
            BarColumn(
                bar_width=self.bar_width,
                complete_style="green",
                finished_style="green",
                pulse_style="cyan",
            ),
            TimeElapsedColumn(),
            console=self.console,
            transient=True,
        )

        def runner():
            with self._progress:
                self._task_id = self._progress.add_task(self.description, total=100)
                progress_value = 0
                while not self._stop_event.is_set():
                    if self._task_id is not None:
                        progress_value = (progress_value + 3) % 100
                        self._progress.update(self._task_id, completed=progress_value)
                    time.sleep(0.08)

        self._thread = threading.Thread(target=runner, daemon=True)
        self._thread.start()
        self._start = time.perf_counter()
        return self

    def __exit__(self, exc_type, exc, tb):
        if self._start is None:
            self.elapsed = 0.0
        else:
            self.elapsed = time.perf_counter() - self._start
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join()

        if exc_type is None:
            self.console.print(
                f"[green]✅ {self.description} completed in {self.elapsed:.2f}s[/green]"
            )
        else:
            self.console.print(
                f"[red]❌ {self.description} failed after {self.elapsed:.2f}s[/red]"
            )
        return False


@dataclass
class SectionContent:
    """Simple structure describing a line item within a section panel."""

    label: str
    value: str


class DemoNarrator:
    """Helper to present sections with consistent styling."""

    def __init__(self, console: Console):
        self.console = console
        self._section_index = 0

    def section(
        self,
        title: str,
        *,
        description: Optional[str] = None,
        bullets: Optional[Sequence[str]] = None,
        highlights: Optional[Sequence[SectionContent]] = None,
        extra: Optional[RenderableType] = None,
    ) -> None:
        self._section_index += 1

        renderables: List[RenderableType] = []

        if description:
            renderables.append(Text(description.strip(), style="white"))

        if bullets:
            bullet_table = Table.grid(padding=(0, 1))
            bullet_table.add_column(width=2, style="cyan", justify="right")
            bullet_table.add_column(style="white")
            for bullet in bullets:
                bullet_table.add_row("•", Text(bullet, style="white"))
            renderables.append(bullet_table)

        if highlights:
            highlight_table = Table.grid(padding=(0, 1))
            highlight_table.add_column(style="cyan", justify="right", ratio=1)
            highlight_table.add_column(style="bold white", ratio=2)
            for item in highlights:
                highlight_table.add_row(item.label, item.value)
            renderables.append(highlight_table)

        if extra:
            renderables.append(extra)

        if not renderables:
            renderables.append(Text("No additional details", style="dim"))

        body: RenderableType
        if len(renderables) == 1:
            body = renderables[0]
        else:
            body = Group(*renderables)

        panel_title = f"[bold magenta]Step {self._section_index}: {title}[/bold magenta]"
        panel = Panel(body, title=panel_title, border_style="magenta", padding=(1, 2))
        self.console.print(panel)

    def note(self, message: str, *, style: str = "cyan") -> None:
        """Render a short, styled note outside of the numbered sections."""
        self.console.print(Text(message, style=style))

