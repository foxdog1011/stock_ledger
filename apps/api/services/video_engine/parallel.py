"""Parallel slide rendering using ProcessPoolExecutor.

matplotlib is not thread-safe, so we must use processes (not threads)
to parallelise CPU-bound chart rendering.
"""
from __future__ import annotations

import logging
from concurrent.futures import ProcessPoolExecutor, as_completed
from typing import Any, Callable

logger = logging.getLogger(__name__)

# Cap workers to avoid excessive memory usage from matplotlib processes.
_MAX_WORKERS = 4


def _run_task(func: Callable[..., Any], args: tuple) -> Any:
    """Wrapper executed in a child process — calls *func(*args)*."""
    return func(*args)


def render_slides_parallel(
    tasks: list[tuple[Callable[..., Any], tuple]],
) -> list[Any]:
    """Render independent slide functions in parallel processes.

    Parameters
    ----------
    tasks:
        List of ``(function, args)`` tuples.  Each function is a slide
        renderer that returns an ``np.ndarray`` (or bytes for thumbnails).

    Returns
    -------
    list:
        Results in the **same order** as *tasks*.

    Falls back to sequential execution if the process pool raises.
    """
    if not tasks:
        return []

    # Single task — no benefit from spawning a process.
    if len(tasks) == 1:
        func, args = tasks[0]
        return [func(*args)]

    try:
        results: list[Any] = [None] * len(tasks)
        workers = min(_MAX_WORKERS, len(tasks))

        with ProcessPoolExecutor(max_workers=workers) as pool:
            future_to_idx = {
                pool.submit(_run_task, func, args): idx
                for idx, (func, args) in enumerate(tasks)
            }

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                results[idx] = future.result()

        return results

    except Exception:
        logger.exception(
            "Parallel slide rendering failed — falling back to sequential"
        )
        return _render_sequential(tasks)


def _render_sequential(
    tasks: list[tuple[Callable[..., Any], tuple]],
) -> list[Any]:
    """Sequential fallback — same interface as render_slides_parallel."""
    return [func(*args) for func, args in tasks]
