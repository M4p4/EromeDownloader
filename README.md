# EromeDownloader V3

A compact yet powerful Python script for downloading albums from
erome.com, including videos, images, and gifs.

## Features

- Download a single album or batch-download many albums from a URL list
- Concurrent downloads with a configurable connection limit
- Automatic retries with exponential backoff
- Resumes intelligently by skipping files that are already fully downloaded
- Optional filters to skip videos or images
- Live progress bars per file and per album

## Requirements

- Python 3.10 or newer

## Installation

Clone the repository and move into it:

```bash
git clone https://github.com/<your-fork>/EromeDownloader.git
cd EromeDownloader
```

Create and activate a virtual environment so the dependencies stay isolated from
your system Python.

**macOS / Linux**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

**Windows (PowerShell)**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Then install the dependencies:

```bash
pip install -r requirements.txt
```

When you are done, deactivate the virtual environment with `deactivate`.

## Usage

Download a single album:

```bash
python dump.py -u https://www.erome.com/a/xxxxxxxx
```

Download many albums in one run by passing a text file of URLs:

```bash
python dump.py -f albums.txt
```

The file must contain one album URL per line. Blank lines and lines starting
with `#` are ignored, so you can comment your batch lists:

```text
# Favorites
https://www.erome.com/a/aaaaaaaa
https://www.erome.com/a/bbbbbbbb

# To re-download later
https://www.erome.com/a/cccccccc
```

Albums are downloaded sequentially; the `-c/--connections` option controls
per-album parallelism. If one album fails, the batch continues with the next
URL.

## Arguments

| Flag                   | Description                                                                       | Default |
| ---------------------- | --------------------------------------------------------------------------------- | ------- |
| `-u`, `--url`          | URL of a single album to download. One of `-u` or `-f` is required.               | —       |
| `-f`, `--file`         | Path to a text file with one album URL per line. One of `-u` or `-f` is required. | —       |
| `-c`, `--connections`  | Maximum number of simultaneous connections used while downloading an album.       | `5`     |
| `-sv`, `--skip-videos` | Skip downloading videos.                                                          | off     |
| `-si`, `--skip-images` | Skip downloading images.                                                          | off     |
| `-r`, `--retries`      | Number of retry attempts per file on failure.                                     | `3`     |

### Examples

Download an album using 10 connections:

```bash
python dump.py -u https://www.erome.com/a/xxxxxxxx -c 10
```

Download a batch and skip all videos:

```bash
python dump.py -f albums.txt -sv
```

Increase the retry count for flaky connections:

```bash
python dump.py -u https://www.erome.com/a/xxxxxxxx -r 5
```

## Where are the files saved?

Files are saved under a `downloads/` folder in the project directory. Each
album gets its own subfolder named after the album title, and all files from
that album are stored there.

```
downloads/
└── Album Title/
    ├── video.mp4
    ├── image1.jpg
    └── image2.jpg
```
