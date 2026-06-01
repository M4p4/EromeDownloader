import argparse
import asyncio
import re
from pathlib import Path
from urllib.parse import urlparse

import aiofiles
import aiohttp
from aiohttp import ClientTimeout
from bs4 import BeautifulSoup
from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    DownloadColumn,
    Progress,
    SpinnerColumn,
    TextColumn,
    TimeRemainingColumn,
    TransferSpeedColumn,
)
from rich.rule import Rule
from rich.table import Table
from rich.text import Text
from rich.traceback import install as install_rich_traceback

USER_AGENT = "Mozilla/5.0"
HOST = "www.erome.com"
CHUNK_SIZE = 1024
RETRY_BACKOFF_BASE = 1  # seconds; actual wait = RETRY_BACKOFF_BASE * (2 ** attempt)

install_rich_traceback(show_locals=False)
console = Console()


def _clean_album_title(title: str, default_title: str = "temp") -> str:
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


def _truncate(text: str, length: int = 48) -> str:
    if len(text) <= length:
        return text
    return "…" + text[-(length - 1) :]


def _print_banner() -> None:
    title = Text("EROME DOWNLOADER", style="bold magenta", justify="center")
    subtitle = Text(
        "v3 · fast concurrent album downloader", style="dim italic", justify="center"
    )
    console.print(
        Panel(
            Group(title, subtitle),
            border_style="magenta",
            padding=(1, 6),
        )
    )


def _make_progress_views() -> tuple[Progress, Progress]:
    album_progress = Progress(
        TextColumn("[bold magenta]{task.description}"),
        BarColumn(
            bar_width=None, complete_style="magenta", finished_style="bold green"
        ),
        TextColumn("[progress.percentage]{task.percentage:>5.1f}%"),
        TextColumn("[cyan]{task.completed}/{task.total} files"),
        TimeRemainingColumn(),
        expand=True,
    )
    file_progress = Progress(
        SpinnerColumn(style="magenta"),
        TextColumn("[bold blue]{task.description}"),
        BarColumn(bar_width=None, complete_style="cyan", finished_style="green"),
        TextColumn("[progress.percentage]{task.percentage:>5.1f}%"),
        DownloadColumn(),
        TransferSpeedColumn(),
        TimeRemainingColumn(),
        expand=True,
    )
    return album_progress, file_progress


def _summary_panel(stats: dict[str, int], title: str = "Album summary") -> Panel:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="dim", justify="right")
    table.add_column()
    table.add_row("Downloaded", f"[bold green]{stats['downloaded']}[/bold green]")
    table.add_row("Skipped", f"[bold yellow]{stats['skipped']}[/bold yellow]")
    table.add_row("Failed", f"[bold red]{stats['failed']}[/bold red]")
    table.add_row("Total", f"[bold cyan]{stats['total']}[/bold cyan]")
    border = "green" if stats["failed"] == 0 else "red"
    return Panel(table, title=f"[bold]{title}", border_style=border, padding=(1, 2))


async def dump(
    url: str,
    max_connections: int,
    skip_videos: bool,
    skip_images: bool,
    retries: int,
    album_index: int,
    total_albums: int,
) -> dict[str, int]:
    """Collect album data and download the album"""
    if urlparse(url).hostname != HOST:
        raise ValueError(f"Host must be {HOST}")

    with console.status(
        f"[magenta]Fetching album {album_index}/{total_albums}…[/magenta]",
        spinner="dots",
    ):
        title, urls = await _collect_album_data(
            url=url, skip_videos=skip_videos, skip_images=skip_images
        )

    download_path = _get_final_download_path(album_title=title)

    info = Table.grid(padding=(0, 2))
    info.add_column(style="dim", justify="right")
    info.add_column()
    info.add_row("URL", f"[link={url}]{url}[/link]")
    info.add_row("Title", f"[bold]{title}[/bold]")
    info.add_row("Files", f"[cyan]{len(urls)}[/cyan]")
    info.add_row("Saved to", f"[green]{download_path}[/green]")

    console.print(
        Panel(
            info,
            title=f"[bold magenta]Album {album_index}/{total_albums}[/bold magenta]",
            border_style="magenta",
            padding=(1, 2),
        )
    )

    if not urls:
        console.print("[yellow]No files found in album — skipping.[/yellow]\n")
        return {"downloaded": 0, "skipped": 0, "failed": 0, "total": 0}

    stats = await _download(
        album=url,
        urls=urls,
        max_connections=max_connections,
        download_path=download_path,
        retries=retries,
    )
    console.print(_summary_panel(stats))
    console.print()
    return stats


async def _download(
    album: str,
    urls: list[str],
    max_connections: int,
    download_path: Path,
    retries: int,
) -> dict[str, int]:
    """Download the album with a live progress dashboard"""
    semaphore = asyncio.Semaphore(max_connections)
    stats = {"downloaded": 0, "skipped": 0, "failed": 0, "total": len(urls)}

    album_progress, file_progress = _make_progress_views()
    dashboard = Panel(
        Group(album_progress, Rule(style="dim magenta"), file_progress),
        title="[bold magenta]Downloading[/bold magenta]",
        border_style="magenta",
        padding=(1, 2),
    )

    async with aiohttp.ClientSession(
        headers={"Referer": album, "User-Agent": USER_AGENT},
        timeout=ClientTimeout(total=None),
    ) as session:
        with Live(dashboard, console=console, refresh_per_second=12):
            album_task = album_progress.add_task("Album progress", total=len(urls))
            tasks = [
                _download_file(
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
                for url in urls
            ]
            await asyncio.gather(*tasks)

    return stats


async def _download_file(
    session: aiohttp.ClientSession,
    url: str,
    semaphore: asyncio.Semaphore,
    download_path: Path,
    retries: int,
    file_progress: Progress,
    album_progress: Progress,
    album_task: int,
    stats: dict[str, int],
) -> None:
    """Download the file with retry-on-failure and exponential backoff."""
    async with semaphore:
        file_name = Path(urlparse(url).path).name
        task_id = file_progress.add_task(_truncate(file_name), total=None, start=False)
        try:
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

                        total_size_in_bytes = int(r.headers.get("content-length", 0))
                        file_path = Path(download_path, file_name)

                        if file_path.exists():
                            existing_file_size = file_path.stat().st_size
                            if abs(existing_file_size - total_size_in_bytes) <= 50:
                                stats["skipped"] += 1
                                return

                        file_progress.update(task_id, total=total_size_in_bytes or None)
                        file_progress.start_task(task_id)

                        async with aiofiles.open(file_path, "wb") as f:
                            async for chunk in r.content.iter_chunked(CHUNK_SIZE):
                                written_size = await f.write(chunk)
                                file_progress.update(task_id, advance=written_size)

                        stats["downloaded"] += 1
                        return
                except (aiohttp.ClientError, asyncio.TimeoutError, OSError) as e:
                    if attempt < retries:
                        wait = RETRY_BACKOFF_BASE * (2**attempt)
                        console.print(
                            f"[yellow]↻[/yellow] [yellow]retry[/yellow] "
                            f"[dim]{attempt + 1}/{retries}[/dim] "
                            f"[cyan]{file_name}[/cyan] in [magenta]{wait}s[/magenta] "
                            f"[red]({e})[/red]"
                        )
                        await asyncio.sleep(wait)
                    else:
                        console.print(
                            f"[red]✗[/red] [bold red]failed[/bold red] "
                            f"[cyan]{file_name}[/cyan] after [magenta]{retries}[/magenta] "
                            f"retries: [red]{e}[/red]"
                        )
                        stats["failed"] += 1
                        return
        finally:
            file_progress.remove_task(task_id)
            album_progress.update(album_task, advance=1)


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
                [
                    image["data-src"]
                    for image in soup.find_all(
                        "div", {"class": "img", "data-src": True}
                    )
                ]
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


async def _run(urls: list[str], args: argparse.Namespace) -> None:
    """Download a batch of albums sequentially, continuing past per-album errors."""
    _print_banner()

    overall = {"downloaded": 0, "skipped": 0, "failed": 0, "total": 0}
    albums_ok = 0
    albums_failed = 0

    for i, url in enumerate(urls, 1):
        try:
            stats = await dump(
                url=url,
                max_connections=args.connections,
                skip_videos=args.skip_videos,
                skip_images=args.skip_images,
                retries=args.retries,
                album_index=i,
                total_albums=len(urls),
            )
            for key in overall:
                overall[key] += stats[key]
            albums_ok += 1
        except Exception as e:
            console.print(
                Panel(
                    f"[red]{e}[/red]\n[dim]{url}[/dim]",
                    title=f"[bold red]Album {i}/{len(urls)} failed[/bold red]",
                    border_style="red",
                    padding=(1, 2),
                )
            )
            console.print()
            albums_failed += 1

    if len(urls) > 1:
        table = Table.grid(padding=(0, 2))
        table.add_column(style="dim", justify="right")
        table.add_column()
        table.add_row("Albums OK", f"[bold green]{albums_ok}[/bold green]")
        table.add_row("Albums failed", f"[bold red]{albums_failed}[/bold red]")
        table.add_row(
            "Files downloaded", f"[bold green]{overall['downloaded']}[/bold green]"
        )
        table.add_row(
            "Files skipped", f"[bold yellow]{overall['skipped']}[/bold yellow]"
        )
        table.add_row("Files failed", f"[bold red]{overall['failed']}[/bold red]")
        table.add_row("Files total", f"[bold cyan]{overall['total']}[/bold cyan]")
        border = "green" if albums_failed == 0 and overall["failed"] == 0 else "red"
        console.print(
            Panel(
                table,
                title="[bold]Batch summary[/bold]",
                border_style=border,
                padding=(1, 2),
            )
        )


def main() -> None:
    """CLI entry point for the ``eromedump`` command."""
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
    try:
        asyncio.run(_run(urls, args))
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user.[/yellow]")


if __name__ == "__main__":
    main()
