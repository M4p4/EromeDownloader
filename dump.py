import argparse
import sys
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse
import os
import tldextract
from tqdm import tqdm
import re

session = requests.Session()
# Chars not valid to windows folder creation
UNVALID_CHARS = [r"\\", r"\/", r"\?", r"\:", r"\*", r"\<", r"\"", r"\>", r"\|"]
PATTERN = "[(" + "".join(UNVALID_CHARS) + ")]"
MAX_ATTEMPTS = 5


def collect_links(album_url):
    parsed_url = urlparse(album_url)
    if parsed_url.hostname != "www.erome.com":
        raise Exception(f"Host must be www.erome.com")

    r = session.get(album_url, headers={"User-Agent": "Mozilla/5.0"})
    if r.status_code != 200:
        raise Exception(f"HTTP error {r.status_code}")

    soup = BeautifulSoup(r.content, "html.parser")
    title = soup.find("meta", property="og:title")["content"]
    videos = [video_source["src"] for video_source in soup.find_all("source")]
    images = [
        image["data-src"] for image in soup.find_all("img", {"class": "img-back"})
    ]
    urls = list(set([*videos, *images]))
    download_path, folder_name = get_final_path(title)
    existing_files = get_files_in_dir(download_path)
    with tqdm(desc=folder_name, total=len(urls), leave=True, position=0) as dbar:
        for file_url in urls:
            download(file_url, download_path, album_url, existing_files)
            dbar.update()


def get_final_path(title):
    folder_name = re.sub(PATTERN, "_", title)
    final_path = os.path.join("downloads", folder_name)
    if not os.path.isdir(final_path):
        os.makedirs(final_path)
    return final_path, folder_name


def get_files_in_dir(directory):
    return [
        f for f in os.listdir(directory) if os.path.isfile(os.path.join(directory, f))
    ]


def download(url, download_path, album=None, existing_files=[]):
    parsed_url = urlparse(url)
    file_name = os.path.basename(parsed_url.path)
    extracted = tldextract.extract(url)
    hostname = "{}.{}".format(extracted.domain, extracted.suffix)

    attempt = 0
    while attempt < MAX_ATTEMPTS:
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
                total_size_in_bytes = int(r.headers.get("Content-Length", 0))
                block_size = 1024

                with open(os.path.join(download_path, file_name), "wb") as f, tqdm(
                    desc=file_name,
                    total=total_size_in_bytes // block_size,
                    unit="Kb",
                    unit_scale=True,
                    leave=False,
                    position=1,
                ) as bar:
                    downloaded_size = 0
                    for chunk in r.iter_content(chunk_size=block_size):
                        if chunk:
                            f.write(chunk)
                            bar.update(len(chunk) // block_size)
                            downloaded_size += len(chunk)

                if downloaded_size == total_size_in_bytes:
                    break
                else:
                    attempt += 1
                    continue
            else:
                print(r)
                print(f'[ERROR] Download of  "{url}" failed')
                return None
    else:
        print(f"[ERROR] Failed to download '{file_name}' after {MAX_ATTEMPTS} retries.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(sys.argv[1:])
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("-u", help="url to download", type=str)
    group.add_argument("-f", help="file with links to download", type=str)
    args = parser.parse_args()
    if args.u:
        collect_links(args.u)
    elif args.f:
        with open(args.f) as reader:
            for line in reader.readlines():
                collect_links(line.strip())
