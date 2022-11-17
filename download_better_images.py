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
    # Sleep briefly, in an attempt to minimize the possibility of trigging some auto-cutoff mechanism
    if index > 1:
        print(f'{index}/{count}: Sleeping...', end='\r')
        time.sleep(1.5)
    # Request the URL (in stream mode so that we can conditionally abort depending on the headers)
    print(f'{index}/{count}: Requesting headers for {url}...', end='\r')
    size_before = os.path.getsize(filename)
    try:
        with requests.get(url, stream=True) as res:
            if not res.status_code == 200:
                raise Exception('Download failed')
            size_after = int(res.headers['content-length'])
            if size_after > size_before:
                # Proceed with the full download
                print(f'{index}/{count}: Downloading {url}...            ', end='\r')
                with open(filename,'wb') as f:
                    shutil.copyfileobj(res.raw, f)
                percentage_increase = 100.0 * (size_after - size_before) / size_before
                logging.info(f'{index}/{count}: Success. Overwrote {filename} with downloaded version from {url} that is {percentage_increase:.0f}% larger, {size_after/2**20:.1f}MB downloaded.')
                return True, size_after
            else:
                logging.info(f'{index}/{count}: Skipped. Available version at {url} is same size or smaller than {filename}')
                return False, 0
    except:
        logging.error(f"{index}/{count}: Fail. Media couldn't be retrieved: {url} Filename: {filename}")
        return False, 0

def main():

    media_folder_name = 'media'
    media_sources_path = os.path.join(media_folder_name, 'media_sources.txt')
    log_filename = 'download_log.txt'

    # Read the media sources file produced by parser.py
    try:
        with open(media_sources_path, 'r', encoding='utf8') as sources:
            lines = sources.readlines()
    except:
        print(f'ERROR: failed to open {media_sources_path}. Did you run parser.py first?')
        exit()
    sources = [[entry.strip() for entry in line.split(' ')] for line in lines]
    number_of_files = len(sources)

    # Confirm with the user
    print('\nDownload better images\n----------------------\n')
    print(f'This script will attempt to download {number_of_files} files from twimg.com. If the downloaded version is larger')
    print(f'than the version in {media_folder_name}/ then it will be overwritten. Please be aware that this script may download')
    print('a lot of data, which will cost you money if you are paying for bandwidth. Please be aware that')
    print('the servers might block these requests if they are too frequent. This script may not work if your account is')
    print('protected. You may want to set it to public before starting the download.')
    user_input = input('\nOK to continue? [y/n]')
    if not user_input.lower() in ('y', 'yes'):
        exit()

    # Direct all output to stdout and errors to a log file
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(message)s')
    logfile_handler = logging.FileHandler(filename=log_filename, mode='w')
    logfile_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(logfile_handler)

    # Download new versions
    start_time = time.time()
    success_count = 0
    total_bytes_downloaded = 0
    for index, (local_media_filename, media_url) in enumerate(sources):
        # Try downloading it
        local_media_path = os.path.join(media_folder_name, local_media_filename)
        success, bytes_downloaded = attempt_download_larger_media(media_url, local_media_path, index+1, number_of_files)
        success_count += 1 if success else 0
        total_bytes_downloaded += bytes_downloaded
    end_time = time.time()

    logging.info(f'\nReplaced {success_count} of {number_of_files} media files with larger versions.')
    logging.info(f'Total downloaded: {total_bytes_downloaded/2**20:.1f}MB = {total_bytes_downloaded/2**30:.2f}GB')
    logging.info(f'Time taken: {end_time-start_time:.0f}s')
    print(f'Wrote log to {log_filename}')
    print('In case you set your account to public before initiating the download, do not forget to protect it again.')

if __name__ == "__main__":
    main()
