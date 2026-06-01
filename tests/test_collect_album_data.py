from pathlib import Path

from aioresponses import aioresponses

import dump

ALBUM_URL = "https://www.erome.com/a/test"
FIXTURE_HTML = (Path(__file__).resolve().parent / "fixtures" / "album.html").read_text(
    encoding="utf-8"
)

VIDEO1 = "https://cdn.erome.com/video1.mp4"
VIDEO2 = "https://cdn.erome.com/video2.mp4"
IMAGE1 = "https://cdn.erome.com/image1.jpg"
IMAGE2 = "https://cdn.erome.com/image2.jpg"


async def test_parses_title_videos_and_images():
    with aioresponses() as mocked:
        mocked.get(ALBUM_URL, status=200, body=FIXTURE_HTML)
        title, urls = await dump._collect_album_data(
            url=ALBUM_URL, skip_videos=False, skip_images=False
        )
    assert title == "Test Album"
    assert set(urls) == {VIDEO1, VIDEO2, IMAGE1, IMAGE2}


async def test_skip_videos_returns_only_images():
    with aioresponses() as mocked:
        mocked.get(ALBUM_URL, status=200, body=FIXTURE_HTML)
        _, urls = await dump._collect_album_data(
            url=ALBUM_URL, skip_videos=True, skip_images=False
        )
    assert set(urls) == {IMAGE1, IMAGE2, VIDEO1}


async def test_skip_images_returns_only_videos():
    with aioresponses() as mocked:
        mocked.get(ALBUM_URL, status=200, body=FIXTURE_HTML)
        _, urls = await dump._collect_album_data(
            url=ALBUM_URL, skip_videos=False, skip_images=True
        )
    assert set(urls) == {VIDEO1, VIDEO2}


async def test_deduplicates_urls():
    with aioresponses() as mocked:
        mocked.get(ALBUM_URL, status=200, body=FIXTURE_HTML)
        _, urls = await dump._collect_album_data(
            url=ALBUM_URL, skip_videos=False, skip_images=False
        )
    assert len(urls) == len(set(urls))
    assert len(urls) == 4
