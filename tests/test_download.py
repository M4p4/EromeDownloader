import asyncio

import aiohttp
import pytest
from aioresponses import aioresponses

import dump


async def _run_download_file(url, download_path, retries):
    """Invoke dump._download_file with production-shaped arguments."""
    stats = {"downloaded": 0, "skipped": 0, "failed": 0, "total": 1}
    semaphore = asyncio.Semaphore(1)
    album_progress, file_progress = dump._make_progress_views()
    album_task = album_progress.add_task("Album progress", total=1)
    async with aiohttp.ClientSession() as session:
        await dump._download_file(
            session=session,
            url=url,
            semaphore=semaphore,
            download_path=download_path,
            retries=retries,
            file_progress=file_progress,
            album_progress=album_progress,
            album_task=album_task,
            stats=stats,
        )
    return stats


async def test_dump_rejects_wrong_host():
    with pytest.raises(ValueError, match="Host must be www.erome.com"):
        await dump.dump(
            url="https://example.com/a/whatever",
            max_connections=1,
            skip_videos=False,
            skip_images=False,
            retries=0,
            album_index=1,
            total_albums=1,
        )


async def test_download_file_writes_and_counts_downloaded(tmp_path):
    url = "https://cdn.erome.com/image1.jpg"
    body = b"hello world"
    with aioresponses() as mocked:
        mocked.get(
            url,
            status=200,
            body=body,
            headers={"Content-Length": str(len(body))},
        )
        stats = await _run_download_file(url, tmp_path, retries=0)

    saved = tmp_path / "image1.jpg"
    assert saved.exists()
    assert saved.read_bytes() == body
    assert stats["downloaded"] == 1
    assert stats["skipped"] == 0
    assert stats["failed"] == 0


async def test_download_file_skips_existing_file(tmp_path):
    url = "https://cdn.erome.com/image1.jpg"
    existing = tmp_path / "image1.jpg"
    existing.write_bytes(b"x" * 100)

    with aioresponses() as mocked:
        mocked.get(
            url,
            status=200,
            body=b"x" * 100,
            headers={"Content-Length": "100"},
        )
        stats = await _run_download_file(url, tmp_path, retries=0)

    assert stats["skipped"] == 1
    assert stats["downloaded"] == 0
    assert stats["failed"] == 0


async def test_download_file_retries_then_succeeds(tmp_path, monkeypatch):
    monkeypatch.setattr(dump, "RETRY_BACKOFF_BASE", 0)
    url = "https://cdn.erome.com/image1.jpg"
    body = b"recovered"
    with aioresponses() as mocked:
        mocked.get(url, status=500)
        mocked.get(
            url,
            status=200,
            body=body,
            headers={"Content-Length": str(len(body))},
        )
        stats = await _run_download_file(url, tmp_path, retries=3)

    assert stats["downloaded"] == 1
    assert stats["failed"] == 0
    assert (tmp_path / "image1.jpg").read_bytes() == body


async def test_download_file_fails_after_exhausting_retries(tmp_path, monkeypatch):
    monkeypatch.setattr(dump, "RETRY_BACKOFF_BASE", 0)
    url = "https://cdn.erome.com/image1.jpg"
    with aioresponses() as mocked:
        mocked.get(url, status=500, repeat=True)
        stats = await _run_download_file(url, tmp_path, retries=2)

    assert stats["failed"] == 1
    assert stats["downloaded"] == 0
    assert not (tmp_path / "image1.jpg").exists()
