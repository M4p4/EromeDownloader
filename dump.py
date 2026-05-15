import argparse
import asyncio
import re
import aiohttp
import aiofiles
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from tqdm.asyncio import tqdm, tqdm_asyncio
from pathlib import Path

USER_AGENT = "Mozilla/5.0"
HOST = "www.erome.com"
CHUNK_SIZE = 1024
RETRY_BACKOFF_BASE = 1  # seconds; actual wait = RETRY_BACKOFF_BASE * (2 ** attempt)


def _clean_album_title(title: str, default_title="temp") -> str:
    """Remove illegal characters from the album title"""
    illegal_chars = r'[\\/:*?"<>|]'
    title = re.sub(illegal_chars, "_", title)
    title = title.strip(". ")
    return title if title else default_title


def _get_final_download_path(album_title: str) -> Path:
    """Create a directory with the title of the album"""
    final_path = Path("downloads") / album_title
    if not final_path.exists():
        final_path.mkdir(parents=True)
    return final_path


async def dump(
    url: str,
    max_connections: int,
    skip_videos: bool,
    skip_images: bool,
    retries: int,
):
    """Collect album data and download the album"""
    if urlparse(url).hostname != HOST:
        raise ValueError(f"Host must be {HOST}")

    title, urls = await _collect_album_data(
        url=url, skip_videos=skip_videos, skip_images=skip_images
    )
    download_path = _get_final_download_path(album_title=title)

    await _download(
        album=url,
        urls=urls,
        max_connections=max_connections,
        download_path=download_path,
        retries=retries,
    )


async def _download(
    album: str,
    urls: list[str],
    max_connections: int,
    download_path: Path,
    retries: int,
):
    """Download the album"""
    semaphore = asyncio.Semaphore(max_connections)
    async with aiohttp.ClientSession(
        headers={"Referer": album, "User-Agent": USER_AGENT},
        timeout=ClientTimeout(total=None),
    ) as session:
        tasks = [
            _download_file(
                session=session,
                url=url,
                semaphore=semaphore,
                download_path=download_path,
                retries=retries,
            )
            for url in urls
        ]
        await tqdm_asyncio.gather(
            *tasks,
            colour="MAGENTA",
            desc="Album Progress",
            unit="file",
            leave=True,
        )


async def _download_file(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    download_path: Path,
    retries: int,
):
    """Download the file with retry-on-failure and exponential backoff."""
    async with semaphore:
        for attempt in range(retries + 1):
            try:
                async with session.get(url) as r:
                    if not r.ok:
                        raise aiohttp.ClientResponseError(
                            r.request_info,
                            r.history,
                            status=r.status,
                            message=r.reason or "",
                            headers=r.headers,
                        )

                    file_name = Path(urlparse(url).path).name
                    total_size_in_bytes = int(r.headers.get("content-length", 0))
                    file_path = Path(download_path, file_name)

                    if file_path.exists():
                        existing_file_size = file_path.stat().st_size
                        if abs(existing_file_size - total_size_in_bytes) <= 50:
                            tqdm.write(f"[#] Skipping {url} [already downloaded]")
                            return

                    progress_bar = tqdm(
                        desc=f"[+] Downloading {url}",
                        total=total_size_in_bytes,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=CHUNK_SIZE,
                        colour="MAGENTA",
                        leave=False,
                    )
                    try:
                        async with aiofiles.open(file_path, "wb") as f:
                            async for chunk in r.content.iter_chunked(CHUNK_SIZE):
                                written_size = await f.write(chunk)
                                progress_bar.update(written_size)
                    finally:
                        progress_bar.close()
                    return
            except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                if attempt < retries:
                    wait = RETRY_BACKOFF_BASE * (2 ** attempt)
                    tqdm.write(
                        f"[!] Retry {attempt + 1}/{retries} for {url} in {wait}s ({e})"
                    )
                    await asyncio.sleep(wait)
                else:
                    tqdm.write(
                        f"[ERROR] Failed to download {url} after {retries} retries: {e}"
                    )


async def _collect_album_data(
    url: str, skip_videos: bool, skip_images: bool
) -> tuple[str, list[str]]:
    """Collect videos and images from the album"""
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            html_content = await response.text()
            soup = BeautifulSoup(html_content, "html.parser")
            album_title = _clean_album_title(
                soup.find("meta", property="og:title")["content"]
            )
            videos = (
                [video_source["src"] for video_source in soup.find_all("source")]
                if not skip_videos
                else []
            )
            images = (
                [image["data-src"] for image in soup.find_all("div", {"class": "img"})]
                if not skip_images
                else []
            )
            album_urls = list({*videos, *images})
            return album_title, album_urls


def _read_urls_from_file(path: str) -> list[str]:
    """Read album URLs from a text file, skipping blanks and '#' comments."""
    urls = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            urls.append(line)
    return urls


async def _run(urls: list[str], args: argparse.Namespace):
    """Download a batch of albums sequentially, continuing past per-album errors."""
    for i, url in enumerate(urls, 1):
        print(f"\n[=] Album {i}/{len(urls)}: {url}")
        try:
            await dump(
                url=url,
                max_connections=args.connections,
                skip_videos=args.skip_videos,
                skip_images=args.skip_images,
                retries=args.retries,
            )
        except Exception as e:
            print(f"[ERROR] Album failed: {url} ({e}); continuing.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "-u", "--url", help="URL of a single album to download", type=str
    )
    source.add_argument(
        "-f",
        "--file",
        help="Path to a text file with one album URL per line (blank lines and lines starting with '#' are ignored)",
        type=str,
    )
    parser.add_argument(
        "-c",
        "--connections",
        help="Maximum number of simultaneous connections",
        type=int,
        default=5,
    )
    parser.add_argument(
        "-sv",
        "--skip-videos",
        action=argparse.BooleanOptionalAction,
        help="Skip downloading videos",
    )
    parser.add_argument(
        "-si",
        "--skip-images",
        action=argparse.BooleanOptionalAction,
        help="Skip downloading images",
    )
    parser.add_argument(
        "-r",
        "--retries",
        help="Number of retry attempts per file on failure",
        type=int,
        default=3,
    )
    args = parser.parse_args()
    urls = [args.url] if args.url else _read_urls_from_file(args.file)
    asyncio.run(_run(urls, args))
