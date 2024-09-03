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
RED = "\033[31m"
GREEN = "\033[32m"
YELLOW = "\033[33m"
RESET = "\033[0m"
PURPLE = "\033[34m"
PINK = "\033[35m"


def collect_links(album_url: str) -> int:
    parsed_url = urlparse(album_url)
    if parsed_url.hostname != "www.erome.com":
        raise Exception(f"{RED}Host must be www.erome.com{RESET}")

    r = session.get(album_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        raise Exception(f"{RED}HTTP error {r.status_code}{RESET}")

    soup = BeautifulSoup(r.content, "html.parser")
    title = clean_title(soup.find("meta", property="og:title")["content"])
    videos = [video_source["src"] for video_source in soup.find_all("source")]
    images = [
        image["data-src"] for image in soup.find_all("img", {"class": "img-back"})
    ]
    urls = list(set([*videos, *images]))
    download_path = get_final_path(title)
    existing_files = get_files_in_dir(download_path)
    print(f"{PURPLE}[+] Downloading album '{title}'{RESET}")
    for file_url in urls:
        download(file_url, download_path, album_url, existing_files)

    return len(urls)


def clean_title(title: str) -> str:
    illegal_chars = r'[\\/:*?"<>|]'
    return re.sub(illegal_chars, "_", title)


def get_final_path(title: str) -> str:
    final_path = os.path.join("downloads", title)
    if not os.path.isdir(final_path):
        os.makedirs(final_path)
    return final_path


def get_files_in_dir(directory: str) -> list[str]:
    return [
        f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))
    ]


def download(
    url: str, download_path: str, album: str | None, existing_files: list[str]
) -> None:
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path)
    if file_name in existing_files:
        print(f'{YELLOW}[#] Skipping "{url}" [already downloaded]{RESET}')
        return
    print(f'{PINK}[+] Downloading "{url}"{RESET}')
    extracted = tldextract.extract(url)
    hostname = "{}.{}".format(extracted.domain, extracted.suffix)
    with session.get(
        url,
        headers={
            "Referer": f"https://{hostname}" if album is None else album,
            "Origin": f"https://{hostname}",
            "User-Agent": "Mozila/5.0",
        },
        stream=True,
    ) as r:
        if r.ok:
            total_size_in_bytes = int(r.headers.get("content-length", 0))
            progress_bar = tqdm(total=total_size_in_bytes, unit="iB", unit_scale=True)
            with open(os.path.join(download_path, file_name), "wb") as f:
                for chunk in r.iter_content(chunk_size=1024):
                    progress_bar.update(len(chunk))
                    f.write(chunk)
            progress_bar.close()
        else:
            print(r)
            print(f'{RED}[ERROR] Download of  "{url}" failed{RESET}')
            return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(sys.argv[1:])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", help="url to download", type=str)
    group.add_argument("-f", help="file with urls to download", type=str)
    args = parser.parse_args()
    if args.u:
        files = collect_links(args.u)
        print(f"{GREEN}[\u2713] Album with {files} files downloaded{RESET}")
    elif args.f:
        with open(args.f, "r") as reader:
            for line in reader.readlines():
                if line.startswith("http"):
                    files = collect_links(line.strip())
                    print(f"{GREEN}[\u2713] Album with {files} files downloaded{RESET}")
