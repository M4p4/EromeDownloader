import argparse
import os
import re
import sys
from urllib.parse import urlparse

import requests
import tldextract
from bs4 import BeautifulSoup
from tqdm import tqdm

session = requests.Session()
session.headers.update({"User-Agent": "Mozilla/5.0"})

incomplete_downloads = []

USER_AGENT = "Mozilla/5.0"
EROME_HOST = "www.erome.com"


def collect_links(album_url: str, should_redownload_incomplete = False) -> int:
    validate_url(album_url)
    soup = fetch_album_page(album_url)
    title = extract_title(soup)
    urls = extract_media_urls(soup)
    download_path = get_final_path(title)
    existing_files = get_files_in_dir(download_path)
    print(f"[*] Beginning download of album {title}")
    for file_url in urls:
        if should_redownload_incomplete:
            download_with_incomplete_check(file_url, download_path, album_url, existing_files)
        else:
            download(file_url, download_path, album_url, existing_files)

    # Retry incomplete downloads
    if incomplete_downloads:
        return collect_links(album_url,should_redownload_incomplete=True)

    return len(urls)

def validate_url(album_url: str) -> None:
    """Validates the album URL."""
    parsed_url = urlparse(album_url)
    if parsed_url.hostname != EROME_HOST:
        raise ValueError(f"Host must be {EROME_HOST}")

def fetch_album_page(album_url: str) -> BeautifulSoup:
    """Fetches the album page and returns a BeautifulSoup object."""
    response = session.get(album_url, headers={"User-Agent": USER_AGENT})
    if response.status_code != 200:
        raise requests.HTTPError(f"HTTP error {response.status_code}")
    return BeautifulSoup(response.content, "html.parser")

def clean_title(title: str, default_title="temp") -> str:
    illegal_chars = r'[\\/:*?"<>|]'
    title = re.sub(illegal_chars, '_', title)
    title = title.strip('. ')
    return title if title else default_title

def extract_title(soup: BeautifulSoup) -> str:
    return clean_title(soup.find("meta", property="og:title")["content"])


def get_final_path(title: str) -> str:
    final_path = os.path.join("downloads", title)
    if not os.path.isdir(final_path):
        os.makedirs(final_path)
    return final_path

def extract_media_urls(soup: BeautifulSoup) -> list:
    videos = [video_source["src"] for video_source in soup.find_all("source")]
    images = [image["data-src"] for image in soup.find_all("img", {"class": "img-back"})]
    return list(set(videos + images))

def get_files_in_dir(directory: str) -> list[str]:
    return [
        f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))
    ]


def download(url: str, download_path: str, album: str, existing_files: list[str]) -> None:
    file_name, file_path, headers = download_setup(url, download_path, album, existing_files)
    if file_name in existing_files:
        print(f'[#] Skipping "{url}" [already downloaded]')
        return
    print(f'[+] Downloading "{url}"')
    with session.get(
            url,
            headers=headers,
            stream=True,
    ) as r:
        if r.ok:
            total_size_in_bytes = int(r.headers.get("content-length", 0))
            progress_bar = tqdm(total=total_size_in_bytes, unit="iB", unit_scale=True)
            with open(file_path, "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    progress_bar.update(len(chunk))
                    f.write(chunk)
            progress_bar.close()
        else:
            print(r)
            print(f'[ERROR] Download of  "{url}" failed')
            return None


def download_with_incomplete_check(url: str, download_path: str, album: str, existing_files: list[str]) -> None:
    file_name, file_path, headers = download_setup(url, download_path, album)
    print(f'[+] Downloading "{url}", and checking for incomplete downloads')
    existing_file_size = 0
    total_size_in_bytes = 0
    if file_name in existing_files:
            existing_file_size = os.path.getsize(file_path)
            headers["Range"] = f"bytes={existing_file_size}-"

    with requests.get(url, headers=headers, stream=True) as r:
        if r.ok:
            total_size_in_bytes = int(r.headers.get("content-length", 0)) + existing_file_size
            if existing_file_size != 0 and total_size_in_bytes == existing_file_size:
                print(f'[\u2713] "{file_name}" already downloaded, skipping')
                return

            progress_bar = tqdm(total=total_size_in_bytes, unit="iB", unit_scale=True, initial=existing_file_size)
            with open(file_path, "ab") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    progress_bar.update(len(chunk))
                    f.write(chunk)
            progress_bar.close()
        else:
            incomplete_downloads.append(file_name)
            return None

    if total_size_in_bytes != 0 and progress_bar.n != total_size_in_bytes:
        incomplete_downloads.append(file_name)
    else:
        if file_name in incomplete_downloads:
            incomplete_downloads.remove(file_name)

def get_file_name_and_path(download_path: str, url:str) -> tuple[str, str]:
    file_name = os.path.basename(urlparse(url).path)
    file_path = os.path.join(download_path, file_name)
    return [ file_name, file_path ]

def download_setup(url: str, download_path: str, album: str) -> tuple[str, str, dict]:
    file_name, file_path = get_file_name_and_path(download_path, url)
    extracted = tldextract.extract(url)
    hostname = "{}.{}".format(extracted.domain, extracted.suffix)
    headers = {
            "Referer": f"https://{hostname}" if album is None else album,
            "Origin": f"https://{hostname}",
            "User-Agent": "Mozila/5.0",
        }
    return [file_name, file_path, headers]

if __name__ == "__main__":
    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="url to download", type=str, required=True)
    parser.add_argument(
        "-r",
        help="redownload incomplete downloads. requests file size instead of skipping existing files, therefore slower and optional",
        action="store_true",
    )
    args = parser.parse_args()
    files = collect_links(args.u, args.r)
    print(f"[\u2713] Album with {files} files downloaded")
