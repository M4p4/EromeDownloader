import argparse
import asyncio
import re
import aiohttp
import aiofiles
from bs4 import BeautifulSoup
from urllib.parse import urlparse
from tqdm import tqdm
from pathlib import Path

USER_AGENT = "Mozilla/5.0"
HOST = "www.erome.com"
CHUNK_SIZE = 1024


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


async def dump(url: str, max_connections: int):
    """Collect album data and download the album"""
    if urlparse(url).hostname != HOST:
        raise ValueError(f"Host must be {HOST}")

    title, urls = await _collect_album_data(url=url)
    download_path = _get_final_download_path(album_title=title)

    await _download(
        album=url,
        urls=urls,
        max_connections=max_connections,
        download_path=download_path,
    )


async def _download(
    album: str,
    urls: list[str],
    max_connections: int,
    download_path: Path,
):
    """Download the album"""
    semaphore = asyncio.Semaphore(max_connections)
    async with aiohttp.ClientSession(
        headers={"Referer": album, "User-Agent": USER_AGENT}
    ) as session:
        tasks = [
            _download_file(
                session=session,
                url=url,
                semaphore=semaphore,
                download_path=download_path,
            )
            for url in urls
        ]
        await asyncio.gather(*tasks)


async def _download_file(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    download_path: Path,
):
    """Download the file"""
    async with semaphore, session.get(url) as r:
        if r.ok:
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
            )
            async with aiofiles.open(file_path, "wb") as f:
                async for chunk in r.content.iter_chunked(CHUNK_SIZE):
                    written_size = await f.write(chunk)
                    progress_bar.update(written_size)
        else:
            tqdm.write(f"[ERROR] Failed to download {url}")


async def _collect_album_data(url: str) -> tuple[str, list[str]]:
    """Collect videos and images from the album"""
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            html_content = await response.text()
            soup = BeautifulSoup(html_content, "html.parser")
            album_title = _clean_album_title(
                soup.find("meta", property="og:title")["content"]
            )
            videos = [video_source["src"] for video_source in soup.find_all("source")]
            images = [
                image["data-src"]
                for image in soup.find_all("img", {"class": "img-back"})
            ]
            album_urls = list({*videos, *images})
            return album_title, album_urls


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("-u", "--url", help="URL to download", type=str, required=True)
    parser.add_argument(
        "-c",
        "--connections",
        help="Maximum number of simultaneous connections",
        type=int,
        default=5,
    )
    args = parser.parse_args()
    asyncio.run(dump(url=args.url, max_connections=args.connections))
