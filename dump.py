import argparse
import asyncio
import re
import aiohttp
import aiofiles
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin
from tqdm.asyncio import tqdm, tqdm_asyncio
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


def _get_final_download_path(channel_name: str, album_title: str) -> Path:
    """Create a directory with the channel and album names"""
    final_path = Path("downloads") / channel_name / album_title
    if not final_path.exists():
        final_path.mkdir(parents=True)
    return final_path


async def dump(url: str, max_connections: int, skip_videos: bool, skip_images: bool):
    """Determine if the URL is an album or a channel and process accordingly"""
    parsed_url = urlparse(url)
    if parsed_url.hostname != HOST:
        raise ValueError(f"Host must be {HOST}")

    path_parts = parsed_url.path.strip('/').split('/')
    if '/a/' in parsed_url.path:
        # It's an album
        channel_name = "_default"
        if len(path_parts) > 2 and path_parts[-2] == 'a':
            channel_name = path_parts[0]
        
        title, urls = await _collect_album_data(
            url=url, skip_videos=skip_videos, skip_images=skip_images
        )
        download_path = _get_final_download_path(channel_name=channel_name, album_title=title)

        await _download(
            album=url,
            urls=urls,
            max_connections=max_connections,
            download_path=download_path,
        )
    else:
        # It's a channel
        channel_name = path_parts[0] if len(path_parts) > 0 else "_default"
        download_base_path = Path("downloads") / channel_name
        if not download_base_path.exists():
            download_base_path.mkdir(parents=True)

        album_urls = await _collect_all_channel_albums(channel_url=url)
        if not album_urls:
            print(f"No albums found in channel: {url}")
            return

        for album_url in album_urls:
            title, urls = await _collect_album_data(
                url=album_url, skip_videos=skip_videos, skip_images=skip_images
            )
            download_path = _get_final_download_path(channel_name=channel_name, album_title=title)

            await _download(
                album=album_url,
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
        headers={"Referer": album, "User-Agent": USER_AGENT},
        timeout=ClientTimeout(total=None),
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
        await tqdm_asyncio.gather(
            *tasks,
            colour="MAGENTA",
            desc=f"Downloading Album: {download_path.name}",
            unit="file",
            leave=True,
        )


async def _download_file(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    download_path: Path,
):
    """Download the file"""
    async with semaphore:
        async with session.get(url) as r:
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
                    desc=f"[+] Downloading {file_name}",
                    total=total_size_in_bytes,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=CHUNK_SIZE,
                    colour="MAGENTA",
                    leave=False,
                )
                async with aiofiles.open(file_path, "wb") as f:
                    async for chunk in r.content.iter_chunked(CHUNK_SIZE):
                        written_size = await f.write(chunk)
                        progress_bar.update(written_size)
                progress_bar.close()
            else:
                tqdm.write(f"[ERROR] Failed to download {url}")


async def _collect_album_data(
    url: str, skip_videos: bool, skip_images: bool
) -> tuple[str, list[str]]:
    """Collect videos and images from the album"""
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Failed to access {url} with status {response.status}")
            html_content = await response.text()
            soup = BeautifulSoup(html_content, "html.parser")
            title_tag = soup.find("meta", property="og:title")
            if not title_tag or not title_tag.get("content"):
                raise ValueError("Could not find album title.")
            album_title = _clean_album_title(title_tag["content"])
            videos = (
                [video_source["src"] for video_source in soup.find_all("source") if video_source.get("src")]
                if not skip_videos
                else []
            )
            images = (
                [
                    image["data-src"]
                    for image in soup.find_all("img", {"class": "img-back"})
                    if image.get("data-src")
                ]
                if not skip_images
                else []
            )
            album_urls = list({*videos, *images})
            return album_title, album_urls


async def _collect_channel_albums(url: str) -> list[str]:
    """Extract all album URLs from a single channel page"""
    headers = {"User-Agent": USER_AGENT}
    async with aiohttp.ClientSession(headers=headers) as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise ValueError(f"Failed to access channel {url} with status {response.status}")
            html_content = await response.text()
            soup = BeautifulSoup(html_content, "html.parser")
            album_elements = soup.find_all("a", href=re.compile(r"/a/[A-Za-z0-9]+"))
            album_urls = [
                urljoin(f"https://{HOST}", a_tag["href"]) for a_tag in album_elements if a_tag.get("href")
            ]
            # Remove duplicates
            unique_album_urls = list(set(album_urls))
            return unique_album_urls


async def _collect_all_channel_albums(channel_url: str) -> list[str]:
    """Collect all album URLs from all pages of a channel"""
    page = 1
    all_album_urls = []
    channel_name = urlparse(channel_url).path.strip('/')
    
    while True:
        if page == 1:
            url = channel_url
        else:
            url = f"{channel_url}?page={page}"
            
        album_urls = await _collect_channel_albums(url=url)
        if not album_urls:
            break
            
        print(f"Fetching {len(album_urls)} albums from {channel_name} on Page {page}")
        all_album_urls.extend(album_urls)
        page += 1
        await asyncio.sleep(1)  # Optional: Add delay to be respectful to the server
    
    total_albums = len(all_album_urls)
    print(f"\nFound {total_albums} unique albums in total")
    print("Starting downloads...\n")
    return all_album_urls


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
    args = parser.parse_args()
    asyncio.run(
        dump(
            url=args.url,
            max_connections=args.connections,
            skip_videos=args.skip_videos,
            skip_images=args.skip_images,
        )
    )
