# EromeDownloader V2

The EromeDownloader script is a compact yet powerful tool written in Python, designed to download albums from erome.com, including videos, images, and gifs.

### How to use?

First install the necessary requirements.

```
pip3 install -r requirements.txt
```

Next, run the script by using one of the commands below.

Download a single album:

```
python3 dump.py -u [url]
```

Download many albums in one run by passing a text file of URLs:

```
python3 dump.py -f albums.txt
```

The file must contain one album URL per line. Blank lines and lines starting
with `#` are ignored, so you can comment your batch lists, for example:

```
# Favorites
https://www.erome.com/a/aaaaaaaa
https://www.erome.com/a/bbbbbbbb

# To re-download later
https://www.erome.com/a/cccccccc
```

Albums are downloaded sequentially; the `-c/--connections` option still
controls per-album parallelism. If one album fails the batch continues with
the next URL.

### Arguments
- **-u, --url** : URL of a single album to download. (One of `-u` or `-f` is required.)
- **-f, --file** : Path to a text file with one album URL per line. (One of `-u` or `-f` is required.)
- **-c, --connections** : Max connections to use for downloading files. Default is 5.
- **-sv, --skip-videos** : Skip downloading videos.
- **-si, --skip-images** : Skip downloading images.
- **-r, --retries** : Number of retry attempts per file on failure. Default is 3.

### Where are the files saved?

The files will be saved in a folder named "downloads" and within that, a folder with the album 
name will be created and all files from that album will be saved there.
