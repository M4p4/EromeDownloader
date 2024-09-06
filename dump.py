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
USER_AGENT = "Mozilla/5.0"
HOST = "www.erome.com"


def collect_links(album_url: str) -> int:
    parsed_url = urlparse(album_url)
    if parsed_url.hostname != HOST:
        raise Exception(f"Host must be {HOST}")

    r = session.get(album_url, headers={"User-Agent": USER_AGENT})
    if r.status_code != 200:
        raise Exception(f"HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, "html.parser")
    title = clean_title(soup.find("meta", property="og:title")["content"])
    videos = [video_source["src"] for video_source in soup.find_all("source")]
    images = [
        image["data-src"] for image in soup.find_all("img", {"class": "img-back"})
    ]
    urls = list({*videos, *images})
    download_path = get_final_path(title)
    existing_files = get_files_in_dir(download_path)
    for file_url in urls:
        download(file_url, download_path, album_url, existing_files)

    return len(urls)


def clean_title(title: str, default_title="temp") -> str:
    illegal_chars = r'[\\/:*?"<>|]'
    title = re.sub(illegal_chars, "_", title)
    title = title.strip(". ")
    return title if title else default_title


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
    url: str,
    download_path: str,
    album: str,
    existing_files: list[str],
    max_retries: int = 3,
):
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path)
    if file_name in existing_files:
        print(f'[#] Skipping "{url}" [already downloaded]')
        return

    print(f'[+] Downloading "{url}"')
    extracted = tldextract.extract(url)
    hostname = "{}.{}".format(extracted.domain, extracted.suffix)
    headers = {
        "Referer": album,
        "Origin": f"https://{hostname}",
        "User-Agent": USER_AGENT,
    }

    progress_bar = None
    for attempt in range(max_retries):
        try:
            with session.get(url, headers=headers, stream=True) as r:
                r.raise_for_status()
                total_size_in_bytes = int(r.headers.get("content-length", 0))
                progress_bar = tqdm(
                    total=total_size_in_bytes, unit="B", unit_scale=True
                )
                file_path = os.path.join(download_path, file_name)
                with open(file_path, "wb") as f:
                    for chunk in r.iter_content(chunk_size=8192):
                        progress_bar.update(len(chunk))
                        f.write(chunk)
                progress_bar.close()

                if os.path.getsize(file_path) != total_size_in_bytes:
                    raise ValueError(
                        "Downloaded file size does not match expected size"
                    )
                return

        except requests.exceptions.RequestException as e:
            print(
                f'[ERROR] HTTP Request failed on attempt {attempt + 1} for "{url}": {str(e)}'
            )
        except ValueError as e:
            print(
                f'[ERROR] File size verification failed on attempt {attempt + 1} for "{url}": {str(e)}'
            )
        except IOError as e:
            print(
                f'[ERROR] File I/O error on attempt {attempt + 1} for "{url}": {str(e)}'
            )
        except Exception as e:
            print(
                f'[ERROR] Unexpected error on attempt {attempt + 1} for "{url}": {str(e)}'
            )
        finally:
            if progress_bar:
                progress_bar.close()
                progress_bar = None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(sys.argv[1:])
    parser.add_argument("-u", help="url to download", type=str, required=True)
    args = parser.parse_args()
    files = collect_links(args.u)
    print(f"[\u2713] Album with {files} files downloaded")
