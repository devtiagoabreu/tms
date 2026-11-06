from datetime import date

from tms.services import collection_progress

DAY = date(2026, 10, 27)


def test_progress_lifecycle():
    collection_progress.reset(DAY)
    idle = collection_progress.snapshot(DAY)
    assert idle["status"] == "idle"
    assert idle["percent"] == 0

    collection_progress.start(DAY, 2)
    started = collection_progress.snapshot(DAY)
    assert started["status"] == "running"
    assert started["phase"] == "fetching"
    assert started["percent"] == 0

    collection_progress.fetch_completed(DAY, 1, 2, "00001")
    assert collection_progress.snapshot(DAY)["percent"] == 25

    collection_progress.fetch_completed(DAY, 2, 2, "00002")
    assert collection_progress.snapshot(DAY)["percent"] == 50

    collection_progress.process_completed(DAY, 1, 2, "00001", "success")
    partial = collection_progress.snapshot(DAY)
    assert partial["percent"] == 75
    assert partial["success_count"] == 1

    collection_progress.process_completed(DAY, 2, 2, "00002", "retry")
    almost_done = collection_progress.snapshot(DAY)
    assert almost_done["percent"] == 100
    assert almost_done["failed_count"] == 1

    collection_progress.finish(DAY, "partial", 1, 1, "Coleta finalizada.")
    finished = collection_progress.snapshot(DAY)
    assert finished["status"] == "partial"
    assert finished["phase"] == "done"
    assert finished["percent"] == 100
    assert finished["success_count"] == 1
    assert finished["failed_count"] == 1
    assert finished["finished_at"] is not None

    collection_progress.reset(DAY)
    assert collection_progress.snapshot(DAY)["status"] == "idle"
