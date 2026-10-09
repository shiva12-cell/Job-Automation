from src.web.server import get_cache_stats, reset_cache, reset_pagination, get_status
from src.autonomous_engine import engine


def test_get_cache_stats():
    data = get_cache_stats()
    assert "counts" in data
    assert "total_seen" in data["counts"]
    assert "pagination_cursors" in data


def test_reset_pagination():
    # Set a cursor first
    engine.seen_mgr.set_cursor("data analyst", 4)
    assert engine.seen_mgr.get_cursor("data analyst") == 4

    data = reset_pagination()
    assert data["status"] == "success"
    # Cursor should now be reset to default 1
    assert engine.seen_mgr.get_cursor("data analyst") == 1


def test_reset_cache():
    data = reset_cache()
    assert data["status"] == "success"
    assert "stats" in data
    assert "total_seen" in data["stats"]["counts"]


def test_get_status_includes_seen_jobs_cached():
    status = get_status()
    assert "stats" in status
    assert "seen_jobs_cached" in status["stats"]
    assert status["stats"]["seen_jobs_cached"] >= 0
    assert "category_counts" in status["stats"]
    assert "tab_counts" in status["stats"]
    assert "data_analyst" in status["stats"]["tab_counts"]
