#!/usr/bin/env python3
"""
    twitter-archive-parser - Python code to parse a Twitter archive and output in various ways
    Copyright (C) 2022  Tim Hutton

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import glob
import logging
import os
import shutil
import subprocess
import sys
import time
import urllib.request
try:
    import requests
except:
    print('\nError: This script uses the "requests" module which is not installed.\n')
    user_input = input('OK to install using pip? [y/n]')
    if not user_input.lower() in ('y', 'yes'):
        exit()
    subprocess.run([sys.executable, '-m', 'pip', 'install', 'requests'], check=True)
    import requests


def attempt_download_larger_media(url, filename, index, count):
    """Attempts to download from the specified URL. Overwrites file if larger.
       Returns success flag and number of bytes downloaded.
    """
    print(f'{index}/{count}: Downloading...', end='\r')
    size_before = os.path.getsize(filename)
    try:
        # (Would be nice to ask for the size without downloading, but it seems that twimg.com doesn't support HEAD requests.)
        res = urllib.request.urlopen(url)
        if not res.code == 200:
            raise Exception('Download failed')
        size_after = int(res.headers['content-length'])
        if size_after > size_before:
            with open(filename,'wb') as f:
                shutil.copyfileobj(res, f)
            percentage_increase = 100.0 * (size_after - size_before) / size_before
            logging.info(f'{index}/{count}: Success. Overwrote {filename} with downloaded version that is {percentage_increase:.0f}% larger, {size_after/2**20:.1f}MB downloaded.')
            return True, size_after
        else:
            logging.info(f'{index}/{count}: Skipped. Downloaded version is same size or smaller than {filename}, {size_after/2**20:.1f}MB downloaded.')
            return False, size_after
    except:
        logging.error(f"{index}/{count}: Fail. Media couldn't be retrieved: {url} Filename: {filename}")
        return False, 0

def main():

    media_folder_name = 'media'
    log_filename = 'download_log.txt'

    media_filenames = glob.glob(os.path.join(media_folder_name, '*.*'))
    number_of_files = len(media_filenames)

    # Confirm with the user
    print('\nDownload better images\n----------------------\n')
    print(f'This script will attempt to download {number_of_files} files from twimg.com. If the downloaded version is larger')
    print(f'than the version in {media_folder_name}/ then it will be overwritten. Please be aware that this script may download')
    print('a lot of data, which will cost you money if you are paying for bandwidth. Please be aware that')
    print('the servers might block these requests if they are too frequent.')
    user_input = input('\nOK to continue? [y/n]')
    if not user_input.lower() in ('y', 'yes'):
        exit()

    # Direct all output to stdout and errors to a log file
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(message)s')
    logfile_handler = logging.FileHandler(filename=log_filename, mode='w')
    logfile_handler.setLevel(logging.ERROR)
    logging.getLogger().addHandler(logfile_handler)

    # Download new versions
    start_time = time.time()
    success_count = 0
    total_bytes_downloaded = 0
    for index, filename in enumerate(media_filenames):
        # Construct the URL corresponding to this file:
        # - media in the Twitter archive are: <tweet_id>-<media_id>.<ext>
        # - images online are: https://pbs.twimg.com/media/<media_id>.<ext>:orig
        # - videos online are: https://video.twimg.com/tweet_video/<media_id>.<ext>
        media_filename = filename.split('-', 1)[-1]
        ext = os.path.splitext(media_filename)[1]
        if ext in ['.mp4', '.mpg']:
            url = f'https://video.twimg.com/tweet_video/{media_filename}'
        else:
            url = f'https://pbs.twimg.com/media/{media_filename}:orig'
        # Try downloading it
        success, bytes_downloaded = attempt_download_larger_media(url, filename, index+1, number_of_files)
        success_count += 1 if success else 0
        total_bytes_downloaded += bytes_downloaded
        # Sleep briefly, in an attempt to minimize the possibility of trigging some auto-cutoff mechanism
        time.sleep(1)
    end_time = time.time()
    logging.info(f'\nReplaced {success_count} of {number_of_files} media files with larger versions.')
    logging.info(f'Total downloaded: {total_bytes_downloaded/2**20:.1f}MB = {total_bytes_downloaded/2**30:.2f}GB')
    logging.info(f'Time taken: {end_time-start_time:.0f}s')
    print(f'Wrote log to {log_filename}')

if __name__ == "__main__":
    main()
