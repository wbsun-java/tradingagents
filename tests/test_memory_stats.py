import pytest

from scripts.memory_stats import compute_stats
from tradingagents.agents.utils.memory import TradingMemoryLog


def _make_log(tmp_path):
    return TradingMemoryLog({"memory_log_path": str(tmp_path / "trading_memory.md")})


def test_compute_stats_resolved_entries(tmp_path):
    log = _make_log(tmp_path)
    log.store_decision("NVDA", "2026-01-05", "Rating: Buy\nGo long.")
    log.update_with_outcome(
        "NVDA",
        "2026-01-05",
        raw_return=0.05,
        alpha_return=0.02,
        holding_days=5,
        reflection="Worked out.",
    )
    log.store_decision("TSLA", "2026-01-06", "Rating: Sell\nExit position.")
    log.update_with_outcome(
        "TSLA",
        "2026-01-06",
        raw_return=-0.03,
        alpha_return=-0.01,
        holding_days=8,
        reflection="Missed the bounce.",
    )

    stats = compute_stats(log.load_entries())

    assert stats["count"] == 2
    assert stats["win_rate"] == pytest.approx(0.5)
    assert stats["avg_alpha"] == pytest.approx(0.5, abs=0.01)
    assert stats["avg_holding"] == pytest.approx(6.5, abs=0.01)


def test_compute_stats_pending_only(tmp_path):
    log = _make_log(tmp_path)
    log.store_decision("NVDA", "2026-01-05", "Rating: Buy\nGo long.")

    stats = compute_stats(log.load_entries())

    assert stats is None


def test_compute_stats_empty_list():
    assert compute_stats([]) is None
