# EromeDownloader V2

The EromeDownloader script is a compact yet powerful tool written in Python, designed to download albums from erome.com, including videos, images, and gifs.

### How to use?

First install the necessary requirements.

```
pip3 install -r requirements.txt
```

Next, run the script by using the command:

```
python3 dump.py -u [url]
```

Provide the URL of the album you wish to download as the argument **[url]**.

### Arguments
- **-u, --url** : URL of the album to download. (Required)
- **-c, --connections** : Max connections to use for downloading files. Default is 5.
- **-sv, --skip-videos** : Skip downloading videos.
- **-si, --skip-images** : Skip downloading images.

### Where are the files saved?

The files will be saved in a folder named "downloads" and within that, a folder with the album name will be created and all files from that album will be saved there.
