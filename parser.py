#!/usr/bin/env python3
"""
    twitter-archive-parser - Python code to parse a Twitter archive and output in various ways
    Copyright (C) 2022 Tim Hutton - https://github.com/timhutton/twitter-archive-parser

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

from collections import defaultdict
from typing import Optional
from urllib.parse import urlparse
import datetime
import glob
import importlib
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import time
# hot-loaded if needed, see import_module():
#  imagesize
#  requests


# Print a compile-time error in Python < 3.6. This line does nothing in Python 3.6+ but is reported to the user
# as an error (because it is the first line that fails to compile) in older versions.
f' Error: This script requires Python 3.6 or later. Use `python --version` to check your version.'


class UserData:
    def __init__(self, user_id: str, handle: str):
        if user_id is None:
            raise ValueError('ID "None" is not allowed in UserData.')
        self.user_id = user_id
        if handle is None:
            raise ValueError('handle "None" is not allowed in UserData.')
        self.handle = handle


class PathConfig:
    """
    Helper class containing constants for various directories and files.
    
    The script will only add / change / delete content in its own directories, which start with `parser-`.
    Files within `parser-output` are the end result that the user is probably interested in.
    Files within `parser-cache` are temporary working files, which improve the efficiency if you run
    this script multiple times. They can safely be removed without harming the consistency of  the
    files within `parser-output`.
    """
    def __init__(self, dir_archive):
        self.dir_archive                    = dir_archive
        self.dir_input_data                 = os.path.join(dir_archive,             'data')
        self.file_account_js                = os.path.join(self.dir_input_data,     'account.js')

        # check if user is in correct folder
        if not os.path.isfile(self.file_account_js):
            print(f'Error: Failed to load {self.file_account_js}. ')
            exit()

        self.dir_input_media                = find_dir_input_media(self.dir_input_data)
        self.dir_output                     = os.path.join(self.dir_archive,        'parser-output')
        self.dir_output_media               = os.path.join(self.dir_output,         'media')
        self.dir_output_cache               = os.path.join(self.dir_archive,        'parser-cache')
        self.file_output_following          = os.path.join(self.dir_output,         'following.txt')
        self.file_output_followers          = os.path.join(self.dir_output,         'followers.txt')
        self.file_download_log              = os.path.join(self.dir_output_media,   'download_log.txt')
        self.file_tweet_icon                = os.path.join(self.dir_output_media,   'tweet.ico')
        self.files_input_tweets             = find_files_input_tweets(self.dir_input_data)

        # structured like an actual tweet output file, can be used to compute relative urls to a media file
        self.example_file_output_tweets = self.create_path_for_file_output_tweets(year=2020, month=12)

    def create_path_for_file_output_tweets(self, year, month, format="html", kind="tweets") -> str:
        """Builds the path for a tweet-archive file based on some properties."""
        # Previously the filename was f'{dt.year}-{dt.month:02}-01-Tweet-Archive-{dt.year}-{dt.month:02}'
        return os.path.join(self.dir_output, f"{kind}-{format}", f"{year:04}", f"{year:04}-{month:02}-01-{kind}.{format}")

    def create_path_for_file_output_dms(self, name: str, index: Optional[int]=None, format: str="html", kind: str="DMs") -> str:
        """Builds the path for a dm-archive file based on some properties."""
        index_suffix = ""
        if (index):
            index_suffix = f"-part{index:03}"
        return os.path.join(self.dir_output, kind, f"{kind}-{name}{index_suffix}.{format}")

    def create_path_for_file_output_single(self, format: str, kind: str)->str:
        """Builds the path for a single output file which, i.e. one that is not part of a larger group or sequence."""
        return os.path.join(self.dir_output, f"{kind}.{format}")


def get_consent(prompt: str, default_to_yes: bool = False):
    """Asks the user for consent, using the given prompt. Accepts various versions of yes/no, or 
    an empty answer to accept the default. The default is 'no' unless default_to_yes is passed as 
    True. The default will be indicated automatically. For unacceptable answers, the user will 
    be asked again."""
    if default_to_yes:
        suffix = " [Y/n]"
        default_answer = "yes"
    else:
        suffix = " [y/N]"
        default_answer = "no"
    while True:
        user_input = input(prompt + suffix)
        if user_input == "":
            print (f"Your empty response was assumed to mean '{default_answer}' (the default for this question).")
            return default_to_yes
        if user_input.lower() in ('y', 'yes'):
            return True
        if user_input.lower() in ('n', 'no'):
            return False
        print (f"Sorry, did not understand. Please answer with y, n, yes, no, or press enter to accept "
            f"the default (which is '{default_answer}' in this case, as indicated by the uppercase "
            f"'{default_answer.upper()[0]}'.)")


def import_module(module):
    """Imports a module specified by a string. Example: requests = import_module('requests')"""
    try:
        return importlib.import_module(module)
    except ImportError:
        print(f'\nError: This script uses the "{module}" module which is not installed.\n')
        if not get_consent('OK to install using pip?'):
            exit()
        subprocess.run([sys.executable, '-m', 'pip', 'install', module], check=True)
        return importlib.import_module(module)


def open_and_mkdirs(path_file):
    """Opens a file for writing. If the parent directory does not exist yet, it is created first."""
    mkdirs_for_file(path_file)
    return open(path_file, 'w', encoding='utf-8')


def mkdirs_for_file(path_file):
    """Creates the parent directory of the given file, if it does not exist yet."""
    path_dir = os.path.split(path_file)[0]
    os.makedirs(path_dir, exist_ok=True)


def rel_url(media_path, document_path):
    """Computes the relative URL needed to link from `document_path` to `media_path`.
       Assumes that `document_path` points to a file (e.g. `.md` or `.html`), not a directory."""
    return os.path.relpath(media_path, os.path.split(document_path)[0]).replace("\\", "/")


def get_twitter_api_guest_token(session, bearer_token):
    """Returns a Twitter API guest token for the current session."""
    guest_token_response = session.post("https://api.twitter.com/1.1/guest/activate.json",
                                        headers={'authorization': f'Bearer {bearer_token}'},
                                        timeout=2,
                                        )
    guest_token = json.loads(guest_token_response.content)['guest_token']
    if not guest_token:
        raise Exception(f"Failed to retrieve guest token")
    return guest_token


def get_twitter_users(session, bearer_token, guest_token, user_ids):
    """Asks Twitter for all metadata associated with user_ids."""
    users = {}
    while user_ids:
        max_batch = 100
        user_id_batch = user_ids[:max_batch]
        user_ids = user_ids[max_batch:]
        user_id_list = ",".join(user_id_batch)
        query_url = f"https://api.twitter.com/1.1/users/lookup.json?user_id={user_id_list}"
        response = session.get(query_url,
                               headers={'authorization': f'Bearer {bearer_token}', 'x-guest-token': guest_token},
                               timeout=2,
                               )
        if not response.status_code == 200:
            raise Exception(f'Failed to get user handle: {response}')
        response_json = json.loads(response.content)
        for user in response_json:
            users[user["id_str"]] = user
    return users


def lookup_users(user_ids, users):
    """Fill the users dictionary with data from Twitter"""
    # Filter out any users already known
    filtered_user_ids = [id for id in user_ids if id not in users]
    if not filtered_user_ids:
        # Don't bother opening a session if there's nothing to get
        return
    # Account metadata observed at ~2.1KB on average.
    estimated_size = int(2.1 * len(filtered_user_ids))
    print(f'{len(filtered_user_ids)} users are unknown.')
    if not get_consent(f'Download user data from Twitter (approx {estimated_size:,} KB)?'):
        return

    requests = import_module('requests')
    try:
        with requests.Session() as session:
            bearer_token = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
            guest_token = get_twitter_api_guest_token(session, bearer_token)
            retrieved_users = get_twitter_users(session, bearer_token, guest_token, filtered_user_ids)
            for user_id, user in retrieved_users.items():
                if user["screen_name"] is not None:
                    users[user_id] = UserData(user_id=user_id, handle=user["screen_name"])
        print()  # empty line for better readability of output
    except Exception as err:
        print(f'Failed to download user data: {err}')


def read_json_from_js_file(filename):
    """Reads the contents of a Twitter-produced .js file into a dictionary."""
    print(f'Parsing {filename}...')
    with open(filename, 'r', encoding='utf8') as f:
        data = f.readlines()
        # if the JSON has no real content, it can happen that the file is only one line long.
        # in this case, return an empty dict to avoid errors while trying to read non-existing lines.
        if len(data) <= 1:
            return {}
        # convert js file to JSON: replace first line with just '[', squash lines into a single string
        prefix = '['
        if '{' in data[0]:
            prefix += ' {'
        data =  prefix + ''.join(data[1:])
        # parse the resulting JSON and return as a dict
        return json.loads(data)


def extract_username(paths: PathConfig):
    """Returns the user's Twitter username from account.js."""
    account = read_json_from_js_file(paths.file_account_js)
    return account[0]['account']['username']


def escape_markdown(input_text: str) -> str:
    """
    Escape markdown control characters from input text so that the text will not break in rendered markdown.
    (Only use on unformatted text parts that do not yet have any markdown control characters added on purpose!)
    """
    characters_to_escape: str = r"\_*[]()~`>#+-=|{}.!"
    output_text: str = ''
    for char in input_text:
        if char in characters_to_escape:
            # add backslash before control char
            output_text = output_text + "\\" + char
        elif char == '\n':
            # add double space before line break
            output_text = output_text + "  " + char
        else:
            output_text = output_text + char
    return output_text


def convert_tweet(tweet, username, media_sources, users: dict, paths: PathConfig):
    """Converts a JSON-format tweet. Returns tuple of timestamp, markdown and HTML."""
    if 'tweet' in tweet.keys():
        tweet = tweet['tweet']
    timestamp_str = tweet['created_at']
    timestamp = int(round(datetime.datetime.strptime(timestamp_str, '%a %b %d %X %z %Y').timestamp()))
    # Example: Tue Mar 19 14:05:17 +0000 2019
    body_markdown = tweet['full_text']
    body_html = tweet['full_text']
    tweet_id_str = tweet['id_str']
    # for old tweets before embedded t.co redirects were added, ensure the links are
    # added to the urls entities list so that we can build correct links later on.
    if 'entities' in tweet and 'media' not in tweet['entities'] and len(tweet['entities'].get("urls", [])) == 0:
        for word in tweet['full_text'].split():
            try:
                url = urlparse(word)
            except ValueError:
                pass  # don't crash when trying to parse something that looks like a URL but actually isn't
            else:
                if url.scheme != '' and url.netloc != '' and not word.endswith('\u2026'):
                    # Shorten links similar to twitter
                    netloc_short = url.netloc[4:] if url.netloc.startswith("www.") else url.netloc
                    path_short = url.path if len(url.path + '?' + url.query) < 15 \
                        else (url.path + '?' + url.query)[:15] + '\u2026'
                    tweet['entities']['urls'].append({
                        'url': word,
                        'expanded_url': word,
                        'display_url': netloc_short + path_short,
                        'indices': [tweet['full_text'].index(word), tweet['full_text'].index(word) + len(word)],
                    })
    # replace t.co URLs with their original versions
    if 'entities' in tweet and 'urls' in tweet['entities']:
        for url in tweet['entities']['urls']:
            if 'url' in url and 'expanded_url' in url:
                expanded_url = url['expanded_url']
                body_markdown = body_markdown.replace(url['url'], expanded_url)
                expanded_url_html = f'<a href="{expanded_url}">{expanded_url}</a>'
                body_html = body_html.replace(url['url'], expanded_url_html)
    # if the tweet is a reply, construct a header that links the names
    # of the accounts being replied to the tweet being replied to
    header_markdown = ''
    header_html = ''
    if 'in_reply_to_status_id' in tweet:
        # match and remove all occurrences of '@username ' at the start of the body
        replying_to = re.match(r'^(@[0-9A-Za-z_]* )*', body_markdown)[0]
        if replying_to:
            body_markdown = body_markdown[len(replying_to):]
            body_html = body_html[len(replying_to):]
        else:
            # no '@username ' in the body: we're replying to self
            replying_to = f'@{username}'
        names = replying_to.split()
        # some old tweets lack 'in_reply_to_screen_name': use it if present, otherwise fall back to names[0]
        in_reply_to_screen_name = tweet['in_reply_to_screen_name'] if 'in_reply_to_screen_name' in tweet else names[0]
        # create a list of names of the form '@name1, @name2 and @name3' - or just '@name1' if there is only one name
        name_list = ', '.join(names[:-1]) + (f' and {names[-1]}' if len(names) > 1 else names[0])
        in_reply_to_status_id = tweet['in_reply_to_status_id']
        replying_to_url = f'https://twitter.com/{in_reply_to_screen_name}/status/{in_reply_to_status_id}'
        header_markdown += f'Replying to [{escape_markdown(name_list)}]({replying_to_url})\n\n'
        header_html += f'Replying to <a href="{replying_to_url}">{name_list}</a><br>'
    # escape tweet body for markdown rendering:
    body_markdown = escape_markdown(body_markdown)
    # replace image URLs with image links to local files
    if 'entities' in tweet and 'media' in tweet['entities'] and 'extended_entities' in tweet \
            and 'media' in tweet['extended_entities']:
        original_url = tweet['entities']['media'][0]['url']
        markdown = ''
        html = ''
        for media in tweet['extended_entities']['media']:
            if 'url' in media and 'media_url' in media:
                original_expanded_url = media['media_url']
                original_filename = os.path.split(original_expanded_url)[1]
                archive_media_filename = tweet_id_str + '-' + original_filename
                archive_media_path = os.path.join(paths.dir_input_media, archive_media_filename)
                file_output_media = os.path.join(paths.dir_output_media, archive_media_filename)
                media_url = rel_url(file_output_media, paths.example_file_output_tweets)
                markdown += '' if not markdown and body_markdown == escape_markdown(original_url) else '\n\n'
                html += '' if not html and body_html == original_url else '<br>'
                if os.path.isfile(archive_media_path):
                    # Found a matching image, use this one
                    if not os.path.isfile(file_output_media):
                        shutil.copy(archive_media_path, file_output_media)
                    markdown += f'![]({media_url})'
                    html += f'<img src="{media_url}"/>'
                    # Save the online location of the best-quality version of this file, for later upgrading if wanted
                    best_quality_url = f'https://pbs.twimg.com/media/{original_filename}:orig'
                    media_sources.append(
                        (os.path.join(paths.dir_output_media, archive_media_filename), best_quality_url)
                    )
                else:
                    # Is there any other file that includes the tweet_id in its filename?
                    archive_media_paths = glob.glob(os.path.join(paths.dir_input_media, tweet_id_str + '*'))
                    if len(archive_media_paths) > 0:
                        for archive_media_path in archive_media_paths:
                            archive_media_filename = os.path.split(archive_media_path)[-1]
                            file_output_media = os.path.join(paths.dir_output_media, archive_media_filename)
                            media_url = rel_url(file_output_media, paths.example_file_output_tweets)
                            if not os.path.isfile(file_output_media):
                                shutil.copy(archive_media_path, file_output_media)
                            markdown += f'<video controls><source src="{media_url}">Your browser ' \
                                        f'does not support the video tag.</video>\n'
                            html += f'<video controls><source src="{media_url}">Your browser ' \
                                    f'does not support the video tag.</video>\n'
                            # Save the online location of the best-quality version of this file,
                            # for later upgrading if wanted
                            if 'video_info' in media and 'variants' in media['video_info']:
                                best_quality_url = ''
                                best_bitrate = -1 # some valid videos are marked with bitrate=0 in the JSON
                                for variant in media['video_info']['variants']:
                                    if 'bitrate' in variant:
                                        bitrate = int(variant['bitrate'])
                                        if bitrate > best_bitrate:
                                            best_quality_url = variant['url']
                                            best_bitrate = bitrate
                                if best_bitrate == -1:
                                    print(f"Warning No URL found for {original_url} {original_expanded_url} "
                                          f"{archive_media_path} {media_url}")
                                    print(f"JSON: {tweet}")
                                else:
                                    media_sources.append(
                                        (os.path.join(paths.dir_output_media, archive_media_filename),
                                         best_quality_url)
                                    )
                    else:
                        print(f'Warning: missing local file: {archive_media_path}. Using original link instead: '
                              f'{original_url} (expands to {original_expanded_url})')
                        markdown += f'![]({original_url})'
                        html += f'<a href="{original_url}">{original_url}</a>'
        body_markdown = body_markdown.replace(escape_markdown(original_url), markdown)
        body_html = body_html.replace(original_url, html)
    # make the body a quote
    body_markdown = '> ' + '\n> '.join(body_markdown.splitlines())
    body_html = '<p><blockquote>' + '<br>\n'.join(body_html.splitlines()) + '</blockquote>'
    # append the original Twitter URL as a link
    original_tweet_url = f'https://twitter.com/{username}/status/{tweet_id_str}'
    icon_url = rel_url(paths.file_tweet_icon, paths.example_file_output_tweets) 
    body_markdown = header_markdown + body_markdown + f'\n\n<img src="{icon_url}" width="12" /> ' \
                                                      f'[{timestamp_str}]({original_tweet_url})'
    body_html = header_html + body_html + f'<a href="{original_tweet_url}"><img src="{icon_url}" ' \
                                          f'width="12" />&nbsp;{timestamp_str}</a></p>'
    # extract user_id:handle connections
    if 'in_reply_to_user_id' in tweet and 'in_reply_to_screen_name' in tweet and \
            tweet['in_reply_to_screen_name'] is not None:
        reply_to_id = tweet['in_reply_to_user_id']
        if int(reply_to_id) >= 0:  # some ids are -1, not sure why
            handle = tweet['in_reply_to_screen_name']
            users[reply_to_id] = UserData(user_id=reply_to_id, handle=handle)
    if 'entities' in tweet and 'user_mentions' in tweet['entities'] and tweet['entities']['user_mentions'] is not None:
        for mention in tweet['entities']['user_mentions']:
            if mention is not None and 'id' in mention and 'screen_name' in mention:
                mentioned_id = mention['id']
                if int(mentioned_id) >= 0:  # some ids are -1, not sure why
                    handle = mention['screen_name']
                    if handle is not None:
                        users[mentioned_id] = UserData(user_id=mentioned_id, handle=handle)

    return timestamp, body_markdown, body_html


def find_files_input_tweets(dir_path_input_data):
    """Identify the tweet archive's file and folder names -
    they change slightly depending on the archive size it seems."""
    input_tweets_file_templates = ['tweet.js', 'tweets.js', 'tweets-part*.js']
    files_paths_input_tweets = []
    for input_tweets_file_template in input_tweets_file_templates:
        files_paths_input_tweets += glob.glob(os.path.join(dir_path_input_data, input_tweets_file_template))
    if len(files_paths_input_tweets)==0:
        print(f'Error: no files matching {input_tweets_file_templates} in {dir_path_input_data}')
        exit()
    return files_paths_input_tweets


def find_dir_input_media(dir_path_input_data):
    input_media_dir_templates = ['tweet_media', 'tweets_media']
    input_media_dirs = []
    for input_media_dir_template in input_media_dir_templates:
        input_media_dirs += glob.glob(os.path.join(dir_path_input_data, input_media_dir_template))
    if len(input_media_dirs) == 0:
        print(f'Error: no folders matching {input_media_dir_templates} in {dir_path_input_data}')
        exit()
    if len(input_media_dirs) > 1:
        print(f'Error: multiple folders matching {input_media_dir_templates} in {dir_path_input_data}')
        exit()
    return input_media_dirs[0]


def download_file_if_larger(url, filename, index, count, sleep_time):
    """Attempts to download from the specified URL. Overwrites file if larger.
       Returns whether the file is now known to be the largest available, and the number of bytes downloaded.
    """
    requests = import_module('requests')
    imagesize = import_module('imagesize')

    pref = f'{index:3d}/{count:3d} {filename}: '
    # Sleep briefly, in an attempt to minimize the possibility of trigging some auto-cutoff mechanism
    if index > 1:
        print(f'{pref}Sleeping...', end='\r')
        time.sleep(sleep_time)
    # Request the URL (in stream mode so that we can conditionally abort depending on the headers)
    print(f'{pref}Requesting headers for {url}...', end='\r')
    byte_size_before = os.path.getsize(filename)
    try:
        with requests.get(url, stream=True, timeout=2) as res:
            if not res.status_code == 200:
                # Try to get content of response as `res.text`.
                # For twitter.com, this will be empty in most (all?) cases.
                # It is successfully tested with error responses from other domains.
                raise Exception(f'Download failed with status "{res.status_code} {res.reason}". '
                                f'Response content: "{res.text}"')
            byte_size_after = int(res.headers['content-length'])
            if byte_size_after != byte_size_before:
                # Proceed with the full download
                tmp_filename = filename+'.tmp'
                print(f'{pref}Downloading {url}...            ', end='\r')
                with open(tmp_filename,'wb') as f:
                    shutil.copyfileobj(res.raw, f)
                post = f'{byte_size_after/2**20:.1f}MB downloaded'
                width_before, height_before = imagesize.get(filename)
                width_after, height_after = imagesize.get(tmp_filename)
                pixels_before, pixels_after = width_before * height_before, width_after * height_after
                pixels_percentage_increase = 100.0 * (pixels_after - pixels_before) / pixels_before

                if width_before == -1 and height_before == -1 and width_after == -1 and height_after == -1:
                    # could not check size of both versions, probably a video or unsupported image format
                    os.replace(tmp_filename, filename)
                    bytes_percentage_increase = 100.0 * (byte_size_after - byte_size_before) / byte_size_before
                    logging.info(f'{pref}SUCCESS. New version is {bytes_percentage_increase:3.0f}% '
                                 f'larger in bytes (pixel comparison not possible). {post}')
                    return True, byte_size_after
                elif width_before == -1 or height_before == -1 or width_after == -1 or height_after == -1:
                    # could not check size of one version, this should not happen (corrupted download?)
                    logging.info(f'{pref}SKIPPED. Pixel size comparison inconclusive: '
                                 f'{width_before}*{height_before}px vs. {width_after}*{height_after}px. {post}')
                    return False, byte_size_after
                elif pixels_after >= pixels_before:
                    os.replace(tmp_filename, filename)
                    bytes_percentage_increase = 100.0 * (byte_size_after - byte_size_before) / byte_size_before
                    if bytes_percentage_increase >= 0:
                        logging.info(f'{pref}SUCCESS. New version is {bytes_percentage_increase:3.0f}% larger in bytes '
                                     f'and {pixels_percentage_increase:3.0f}% larger in pixels. {post}')
                    else:
                        logging.info(f'{pref}SUCCESS. New version is actually {-bytes_percentage_increase:3.0f}% '
                                     f'smaller in bytes but {pixels_percentage_increase:3.0f}% '
                                     f'larger in pixels. {post}')
                    return True, byte_size_after
                else:
                    logging.info(f'{pref}SKIPPED. Online version has {-pixels_percentage_increase:3.0f}% '
                                 f'smaller pixel size. {post}')
                    return True, byte_size_after
            else:
                logging.info(f'{pref}SKIPPED. Online version is same byte size, assuming same content. Not downloaded.')
                return True, 0
    except Exception as err:
        logging.error(f"{pref}FAIL. Media couldn't be retrieved from {url} because of exception: {err}")
        return False, 0


def download_larger_media(media_sources, paths: PathConfig):
    """Uses (filename, URL) tuples in media_sources to download files from remote storage.
       Aborts downloads if the remote file is the same size or smaller than the existing local version.
       Retries the failed downloads several times, with increasing pauses between each to avoid being blocked.
    """
    # Log to file as well as the console
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(message)s')
    mkdirs_for_file(paths.file_download_log)
    logfile_handler = logging.FileHandler(filename=paths.file_download_log, mode='w')
    logfile_handler.setLevel(logging.INFO)
    logging.getLogger().addHandler(logfile_handler)
    # Download new versions
    start_time = time.time()
    total_bytes_downloaded = 0
    sleep_time = 0.25
    remaining_tries = 5
    while remaining_tries > 0:
        number_of_files = len(media_sources)
        success_count = 0
        retries = []
        for index, (local_media_path, media_url) in enumerate(media_sources):
            success, bytes_downloaded = download_file_if_larger(
                media_url, local_media_path, index + 1, number_of_files, sleep_time
            )
            if success:
                success_count += 1
            else:
                retries.append((local_media_path, media_url))
            total_bytes_downloaded += bytes_downloaded

            # show % done and estimated remaining time:
            time_elapsed: float = time.time() - start_time
            estimated_time_per_file: float = time_elapsed / (index + 1)
            estimated_time_remaining: datetime.datetime = \
                datetime.datetime.fromtimestamp(
                    (number_of_files - (index + 1)) * estimated_time_per_file,
                    tz=datetime.timezone.utc
                )
            if estimated_time_remaining.hour >= 1:
                time_remaining_string: str = \
                    f"{estimated_time_remaining.hour} hour{'' if estimated_time_remaining.hour == 1 else 's'} " \
                    f"{estimated_time_remaining.minute} minute{'' if estimated_time_remaining.minute == 1 else 's'}"
            elif estimated_time_remaining.minute >= 1:
                time_remaining_string: str = \
                    f"{estimated_time_remaining.minute} minute{'' if estimated_time_remaining.minute == 1 else 's'} " \
                    f"{estimated_time_remaining.second} second{'' if estimated_time_remaining.second == 1 else 's'}"
            else:
                time_remaining_string: str = \
                    f"{estimated_time_remaining.second} second{'' if estimated_time_remaining.second == 1 else 's'}"

            if index + 1 == number_of_files:
                print('    100 % done.')
            else:
                print(f'    {(100*(index+1)/number_of_files):.1f} % done, about {time_remaining_string} remaining...')

        media_sources = retries
        remaining_tries -= 1
        sleep_time += 2
        logging.info(f'\n{success_count} of {number_of_files} tested media files '
                     f'are known to be the best-quality available.\n')
        if len(retries) == 0:
            break
        if remaining_tries > 0:
            print(f'----------------------\n\nRetrying the ones that failed, with a longer sleep. '
                  f'{remaining_tries} tries remaining.\n')
    end_time = time.time()

    logging.info(f'Total downloaded: {total_bytes_downloaded/2**20:.1f}MB = {total_bytes_downloaded/2**30:.2f}GB')
    logging.info(f'Time taken: {end_time-start_time:.0f}s')
    print(f'Wrote log to {paths.file_download_log}')


def parse_tweets(username, users, html_template, paths: PathConfig):
    """Read tweets from paths.files_input_tweets, write to *.md and *.html.
       Copy the media used to paths.dir_output_media.
       Collect user_id:user_handle mappings for later use, in 'users'.
       Returns the mapping from media filename to best-quality URL.
   """
    tweets = []
    media_sources = []
    for tweets_js_filename in paths.files_input_tweets:
        json = read_json_from_js_file(tweets_js_filename)
        for tweet in json:
            tweets.append(convert_tweet(tweet, username, media_sources, users, paths))
    tweets.sort(key=lambda tup: tup[0]) # oldest first

    # Group tweets by month
    grouped_tweets = defaultdict(list)
    for timestamp, md, html in tweets:
        # Use a (markdown) filename that can be imported into Jekyll: YYYY-MM-DD-your-title-here.md
        dt = datetime.datetime.fromtimestamp(timestamp)
        grouped_tweets[(dt.year, dt.month)].append((md, html))

    for (year, month), content in grouped_tweets.items():
        # Write into *.md files
        md_string = '\n\n----\n\n'.join(md for md, _ in content)
        md_path = paths.create_path_for_file_output_tweets(year, month, format="md")
        with open_and_mkdirs(md_path) as f:
            f.write(md_string)

        # Write into *.html files
        html_string = '<hr>\n'.join(html for _, html in content)
        html_path = paths.create_path_for_file_output_tweets(year, month, format="html")
        with open_and_mkdirs(html_path) as f:
            f.write(html_template.format(html_string))

    print(f'Wrote {len(tweets)} tweets to *.md and *.html, '
          f'with images and video embedded from {paths.dir_output_media}')

    return media_sources


def collect_user_ids_from_followings(paths) -> list:
    """
     Collect all user ids that appear in the followings archive data.
     (For use in bulk online lookup from Twitter.)
    """
    # read JSON file from archive
    following_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'following.js'))
    # collect all user ids in a list
    following_ids = []
    for follow in following_json:
        if 'following' in follow and 'accountId' in follow['following']:
            following_ids.append(follow['following']['accountId'])
    return following_ids


def parse_followings(users, user_id_url_template, paths: PathConfig):
    """Parse paths.dir_input_data/following.js, write to paths.file_output_following.
    """
    following = []
    following_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'following.js'))
    following_ids = []
    for follow in following_json:
        if 'following' in follow and 'accountId' in follow['following']:
            following_ids.append(follow['following']['accountId'])
    for following_id in following_ids:
        handle = users[following_id].handle if following_id in users else '~unknown~handle~'
        following.append(handle + ' ' + user_id_url_template.format(following_id))
    following.sort()
    following_output_path = paths.create_path_for_file_output_single(format="txt", kind="following")
    with open_and_mkdirs(following_output_path) as f:
        f.write('\n'.join(following))
    print(f"Wrote {len(following)} accounts to {following_output_path}")


def collect_user_ids_from_followers(paths) -> list:
    """
     Collect all user ids that appear in the followers archive data.
     (For use in bulk online lookup from Twitter.)
    """
    # read JSON file from archive
    follower_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'follower.js'))
    # collect all user ids in a list
    follower_ids = []
    for follower in follower_json:
        if 'follower' in follower and 'accountId' in follower['follower']:
            follower_ids.append(follower['follower']['accountId'])
    return follower_ids


def parse_followers(users, user_id_url_template, paths: PathConfig):
    """Parse paths.dir_input_data/followers.js, write to paths.file_output_followers.
    """
    followers = []
    follower_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'follower.js'))
    follower_ids = []
    for follower in follower_json:
        if 'follower' in follower and 'accountId' in follower['follower']:
            follower_ids.append(follower['follower']['accountId'])
    for follower_id in follower_ids:
        handle = users[follower_id].handle if follower_id in users else '~unknown~handle~'
        followers.append(handle + ' ' + user_id_url_template.format(follower_id))
    followers.sort()
    followers_output_path = paths.create_path_for_file_output_single(format="txt", kind="followers")
    with open_and_mkdirs(followers_output_path) as f:
        f.write('\n'.join(followers))
    print(f"Wrote {len(followers)} accounts to {followers_output_path}")


def chunks(lst: list, n: int):
    """Yield successive n-sized chunks from lst."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]


def collect_user_ids_from_direct_messages(paths) -> list:
    """
     Collect all user ids that appear in the direct messages archive data.
     (For use in bulk online lookup from Twitter.)
    """
    # read JSON file from archive
    dms_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'direct-messages.js'))
    # collect all user ids in a set
    dms_user_ids = set()
    for conversation in dms_json:
        if 'dmConversation' in conversation and 'conversationId' in conversation['dmConversation']:
            dm_conversation = conversation['dmConversation']
            conversation_id = dm_conversation['conversationId']
            user1_id, user2_id = conversation_id.split('-')
            dms_user_ids.add(user1_id)
            dms_user_ids.add(user2_id)
    return list(dms_user_ids)


def parse_direct_messages(username, users, user_id_url_template, paths: PathConfig):
    """Parse paths.dir_input_data/direct-messages.js, write to one markdown file per conversation.
    """
    # read JSON file
    dms_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'direct-messages.js'))

    # Parse the DMs and store the messages in a dict
    conversations_messages = defaultdict(list)
    for conversation in dms_json:
        if 'dmConversation' in conversation and 'conversationId' in conversation['dmConversation']:
            dm_conversation = conversation['dmConversation']
            conversation_id = dm_conversation['conversationId']
            user1_id, user2_id = conversation_id.split('-')
            messages = []
            if 'messages' in dm_conversation:
                for message in dm_conversation['messages']:
                    if 'messageCreate' in message:
                        message_create = message['messageCreate']
                        if all(tag in message_create for tag in ['senderId', 'recipientId', 'text', 'createdAt']):
                            from_id = message_create['senderId']
                            to_id = message_create['recipientId']
                            body = message_create['text']
                            # replace t.co URLs with their original versions
                            if 'urls' in message_create and len(message_create['urls']) > 0:
                                for url in message_create['urls']:
                                    if 'url' in url and 'expanded' in url:
                                        expanded_url = url['expanded']
                                        body = body.replace(url['url'], expanded_url)
                            # escape message body for markdown rendering:
                            body_markdown = escape_markdown(body)
                            # replace image URLs with image links to local files
                            if 'mediaUrls' in message_create \
                                    and len(message_create['mediaUrls']) == 1 \
                                    and 'urls' in message_create:
                                original_expanded_url = message_create['urls'][0]['expanded']
                                message_id = message_create['id']
                                media_hash_and_type = message_create['mediaUrls'][0].split('/')[-1]
                                media_id = message_create['mediaUrls'][0].split('/')[-2]
                                archive_media_filename = f'{message_id}-{media_hash_and_type}'
                                new_url = os.path.join(paths.dir_output_media, archive_media_filename)
                                archive_media_path = \
                                    os.path.join(paths.dir_input_data, 'direct_messages_media', archive_media_filename)
                                if os.path.isfile(archive_media_path):
                                    # found a matching image, use this one
                                    if not os.path.isfile(new_url):
                                        shutil.copy(archive_media_path, new_url)
                                    image_markdown = f'\n![]({new_url})\n'
                                    body_markdown = body_markdown.replace(
                                        escape_markdown(original_expanded_url), image_markdown
                                    )

                                    # Save the online location of the best-quality version of this file,
                                    # for later upgrading if wanted
                                    best_quality_url = \
                                        f'https://ton.twitter.com/i//ton/data/dm/' \
                                        f'{message_id}/{media_id}/{media_hash_and_type}'
                                    # there is no ':orig' here, the url without any suffix has the original size

                                    # TODO: a cookie (and a 'Referer: https://twitter.com' header)
                                    #  is needed to retrieve it, so the url might be useless anyway...

                                    # WARNING: Do not uncomment the statement below until the cookie problem is solved!
                                    # media_sources.append(
                                    #     (
                                    #         os.path.join(output_media_folder_name, archive_media_filename),
                                    #         best_quality_url
                                    #     )
                                    # )

                                else:
                                    archive_media_paths = glob.glob(
                                        os.path.join(paths.dir_input_data, 'direct_messages_media', message_id + '*'))
                                    if len(archive_media_paths) > 0:
                                        for archive_media_path in archive_media_paths:
                                            archive_media_filename = os.path.split(archive_media_path)[-1]
                                            media_url = os.path.join(paths.dir_output_media, archive_media_filename)
                                            if not os.path.isfile(media_url):
                                                shutil.copy(archive_media_path, media_url)
                                            video_markdown = f'\n<video controls><source src="{media_url}">' \
                                                             f'Your browser does not support the video tag.</video>\n'
                                            body_markdown = body_markdown.replace(
                                                escape_markdown(original_expanded_url), video_markdown
                                            )

                                    # TODO: maybe  also save the online location of the best-quality version for videos?
                                    #  (see above)

                                    else:
                                        print(f'Warning: missing local file: {archive_media_path}. '
                                              f'Using original link instead: {original_expanded_url})')

                            created_at = message_create['createdAt']  # example: 2022-01-27T15:58:52.744Z
                            timestamp = \
                                int(round(datetime.datetime.strptime(created_at, '%Y-%m-%dT%X.%fZ').timestamp()))

                            from_handle = escape_markdown(users[from_id].handle) if from_id in users \
                                else user_id_url_template.format(from_id)
                            to_handle = escape_markdown(users[to_id].handle) if to_id in users \
                                else user_id_url_template.format(to_id)

                            # make the body a quote
                            body_markdown = '> ' + '\n> '.join(body_markdown.splitlines())
                            message_markdown = f'{from_handle} -> {to_handle}: ({created_at}) \n\n' \
                                               f'{body_markdown}'
                            messages.append((timestamp, message_markdown))

            # find identifier for the conversation
            other_user_id = user2_id if (user1_id in users and users[user1_id].handle == username) else user1_id

            # collect messages per identifying user in conversations_messages dict
            conversations_messages[other_user_id].extend(messages)

    # output as one file per conversation (or part of long conversation)
    num_written_messages = 0
    num_written_files = 0
    for other_user_id, messages in conversations_messages.items():
        # sort messages by timestamp
        messages.sort(key=lambda tup: tup[0])

        other_user_name = escape_markdown(users[other_user_id].handle) if other_user_id in users \
            else user_id_url_template.format(other_user_id)

        other_user_short_name: str = users[other_user_id].handle if other_user_id in users else other_user_id

        escaped_username = escape_markdown(username)

        # if there are more than 1000 messages, the conversation was split up in the twitter archive.
        # following this standard, also split up longer conversations in the output files:

        if len(messages) > 1000:
            for chunk_index, chunk in enumerate(chunks(messages, 1000)):
                markdown = ''
                markdown += f'### Conversation between {escaped_username} and {other_user_name}, ' \
                            f'part {chunk_index+1}: ###\n\n----\n\n'
                markdown += '\n\n----\n\n'.join(md for _, md in chunk)
                conversation_output_path = paths.create_path_for_file_output_dms(name=other_user_short_name, index=(chunk_index + 1), format="md")

                # write part to a markdown file
                with open_and_mkdirs(conversation_output_path) as f:
                    f.write(markdown)
                print(f'Wrote {len(chunk)} messages to {conversation_output_path}')
                num_written_files += 1

        else:
            markdown = ''
            markdown += f'### Conversation between {escaped_username} and {other_user_name}: ###\n\n----\n\n'
            markdown += '\n\n----\n\n'.join(md for _, md in messages)
            conversation_output_path = paths.create_path_for_file_output_dms(name=other_user_short_name, format="md")

            with open_and_mkdirs(conversation_output_path) as f:
                f.write(markdown)
            print(f'Wrote {len(messages)} messages to {conversation_output_path}')
            num_written_files += 1

        num_written_messages += len(messages)

    print(f"\nWrote {len(conversations_messages)} direct message conversations "
          f"({num_written_messages} total messages) to {num_written_files} markdown files\n")


def make_conversation_name_safe_for_filename(conversation_name: str) -> str:
    """
    Remove/replace characters that could be unsafe in filenames
    """
    forbidden_chars = \
        ['"', "'", '*', '/', '\\', ':', '<', '>', '?', '|', '!', '@', ';', ',', '=', '.', '\n', '\r', '\t']
    new_conversation_name = ''
    for char in conversation_name:
        if char in forbidden_chars:
            new_conversation_name = new_conversation_name + '_'
        elif char.isspace():
            # replace spaces with underscores
            new_conversation_name = new_conversation_name + '_'
        elif char == 0x7F or (0x1F >= ord(char) >= 0x00):
            # 0x00 - 0x1F and 0x7F are also forbidden, just discard them
            continue
        else:
            new_conversation_name = new_conversation_name + char

    return new_conversation_name


def find_group_dm_conversation_participant_ids(conversation: dict) -> set:
    """
    Find IDs of all participating Users in a group direct message conversation
    """
    group_user_ids = set()
    if 'dmConversation' in conversation and 'conversationId' in conversation['dmConversation']:
        dm_conversation = conversation['dmConversation']
        if 'messages' in dm_conversation:
            for message in dm_conversation['messages']:
                if 'messageCreate' in message:
                    group_user_ids.add(message['messageCreate']['senderId'])
                elif 'joinConversation' in message:
                    group_user_ids.add(message['joinConversation']['initiatingUserId'])
                    for participant_id in message['joinConversation']['participantsSnapshot']:
                        group_user_ids.add(participant_id)
                elif "participantsJoin" in message:
                    group_user_ids.add(message['participantsJoin']['initiatingUserId'])
                    for participant_id in message['participantsJoin']['userIds']:
                        group_user_ids.add(participant_id)
    return group_user_ids


def collect_user_ids_from_group_direct_messages(paths) -> list:
    """
     Collect all user ids that appear in the group direct messages archive data.
     (For use in bulk online lookup from Twitter.)
    """
    # read JSON file from archive
    group_dms_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'direct-messages-group.js'))
    # collect all user ids in a set
    group_dms_user_ids = set()
    for conversation in group_dms_json:
        participants = find_group_dm_conversation_participant_ids(conversation)
        for participant_id in participants:
            group_dms_user_ids.add(participant_id)
    return list(group_dms_user_ids)


def parse_group_direct_messages(username, users, user_id_url_template, paths):
    """Parse data_folder/direct-messages-group.js, write to one markdown file per conversation.
    """
    # read JSON file from archive
    group_dms_json = read_json_from_js_file(os.path.join(paths.dir_input_data, 'direct-messages-group.js'))

    # Parse the group DMs, store messages and metadata in a dict
    group_conversations_messages = defaultdict(list)
    group_conversations_metadata = defaultdict(dict)
    for conversation in group_dms_json:
        if 'dmConversation' in conversation and 'conversationId' in conversation['dmConversation']:
            dm_conversation = conversation['dmConversation']
            conversation_id = dm_conversation['conversationId']
            participants = find_group_dm_conversation_participant_ids(conversation)
            participant_names = []
            for participant_id in participants:
                if participant_id in users:
                    participant_names.append(users[participant_id].handle)
                else:
                    participant_names.append(user_id_url_template.format(participant_id))

            # save names in metadata
            group_conversations_metadata[conversation_id]['participants'] = participants
            group_conversations_metadata[conversation_id]['participant_names'] = participant_names
            group_conversations_metadata[conversation_id]['conversation_names'] = [(0, conversation_id)]
            group_conversations_metadata[conversation_id]['participant_message_count'] = defaultdict(int)
            for participant_id in participants:
                # init every participant's message count with 0, so that users with no activity are not ignored
                group_conversations_metadata[conversation_id]['participant_message_count'][participant_id] = 0
            messages = []
            if 'messages' in dm_conversation:
                for message in dm_conversation['messages']:
                    if 'messageCreate' in message:
                        message_create = message['messageCreate']
                        if all(tag in message_create for tag in ['senderId', 'text', 'createdAt']):
                            from_id = message_create['senderId']
                            # count how many messages this user has sent to the group
                            group_conversations_metadata[conversation_id]['participant_message_count'][from_id] += 1
                            body = message_create['text']
                            # replace t.co URLs with their original versions
                            if 'urls' in message_create:
                                for url in message_create['urls']:
                                    if 'url' in url and 'expanded' in url:
                                        expanded_url = url['expanded']
                                        body = body.replace(url['url'], expanded_url)
                            # escape message body for markdown rendering:
                            body_markdown = escape_markdown(body)
                            # replace image URLs with image links to local files
                            if 'mediaUrls' in message_create \
                                    and len(message_create['mediaUrls']) == 1 \
                                    and 'urls' in message_create:
                                original_expanded_url = message_create['urls'][0]['expanded']
                                message_id = message_create['id']
                                media_hash_and_type = message_create['mediaUrls'][0].split('/')[-1]
                                media_id = message_create['mediaUrls'][0].split('/')[-2]
                                archive_media_filename = f'{message_id}-{media_hash_and_type}'
                                new_url = os.path.join(paths.dir_output_media, archive_media_filename)
                                archive_media_path = \
                                    os.path.join(paths.dir_input_data, 'direct_messages_group_media',
                                                 archive_media_filename)
                                if os.path.isfile(archive_media_path):
                                    # found a matching image, use this one
                                    if not os.path.isfile(new_url):
                                        shutil.copy(archive_media_path, new_url)
                                    image_markdown = f'\n![]({new_url})\n'
                                    body_markdown = body_markdown.replace(
                                        escape_markdown(original_expanded_url), image_markdown
                                    )

                                    # Save the online location of the best-quality version of this file,
                                    # for later upgrading if wanted
                                    best_quality_url = \
                                        f'https://ton.twitter.com/i//ton/data/dm/' \
                                        f'{message_id}/{media_id}/{media_hash_and_type}'
                                    # there is no ':orig' here, the url without any suffix has the original size

                                    # TODO: a cookie (and a 'Referer: https://twitter.com' header)
                                    #  is needed to retrieve it, so the url might be useless anyway...

                                    # WARNING: Do not uncomment the statement below until the cookie problem is solved!
                                    # media_sources.append(
                                    #     (
                                    #         os.path.join(output_media_folder_name, archive_media_filename),
                                    #         best_quality_url
                                    #     )
                                    # )

                                else:
                                    archive_media_paths = glob.glob(
                                        os.path.join(paths.dir_input_data, 'direct_messages_group_media',
                                                     message_id + '*'))
                                    if len(archive_media_paths) > 0:
                                        for archive_media_path in archive_media_paths:
                                            archive_media_filename = os.path.split(archive_media_path)[-1]
                                            media_url = os.path.join(paths.dir_output_media,
                                                                     archive_media_filename)
                                            if not os.path.isfile(media_url):
                                                shutil.copy(archive_media_path, media_url)
                                            video_markdown = f'\n<video controls><source src="{media_url}">' \
                                                             f'Your browser does not support the video tag.</video>\n'
                                            body_markdown = body_markdown.replace(
                                                escape_markdown(original_expanded_url), video_markdown
                                            )

                                    # TODO: maybe  also save the online location of the best-quality version for videos?
                                    #  (see above)

                                    else:
                                        print(f'Warning: missing local file: {archive_media_path}. '
                                              f'Using original link instead: {original_expanded_url})')
                            created_at = message_create['createdAt']  # example: 2022-01-27T15:58:52.744Z
                            timestamp = int(round(
                                datetime.datetime.strptime(created_at, '%Y-%m-%dT%X.%fZ').timestamp()
                            ))
                            from_handle = escape_markdown(users[from_id].handle) if from_id in users \
                                else user_id_url_template.format(from_id)
                            # make the body a quote
                            body_markdown = '> ' + '\n> '.join(body_markdown.splitlines())
                            message_markdown = f'{from_handle}: ({created_at})\n\n' \
                                               f'{body_markdown}'
                            messages.append((timestamp, message_markdown))
                    elif "conversationNameUpdate" in message:
                        conversation_name_update = message['conversationNameUpdate']
                        if all(tag in conversation_name_update for tag in ['initiatingUserId', 'name', 'createdAt']):
                            from_id = conversation_name_update['initiatingUserId']
                            body_markdown = f"_changed group name to: {escape_markdown(conversation_name_update['name'])}_"
                            created_at = conversation_name_update['createdAt']  # example: 2022-01-27T15:58:52.744Z
                            timestamp = int(round(
                                datetime.datetime.strptime(created_at, '%Y-%m-%dT%X.%fZ').timestamp()
                            ))
                            from_handle = escape_markdown(users[from_id].handle) if from_id in users \
                                else user_id_url_template.format(from_id)
                            message_markdown = f'{from_handle}: ({created_at})\n\n{body_markdown}'
                            messages.append((timestamp, message_markdown))
                            # save metadata about name change:
                            group_conversations_metadata[conversation_id]['conversation_names'].append(
                                (timestamp, conversation_name_update['name'])
                            )
                    elif "joinConversation" in message:
                        join_conversation = message['joinConversation']
                        if all(tag in join_conversation for tag in ['initiatingUserId', 'createdAt']):
                            from_id = join_conversation['initiatingUserId']
                            created_at = join_conversation['createdAt']  # example: 2022-01-27T15:58:52.744Z
                            timestamp = int(round(
                                datetime.datetime.strptime(created_at, '%Y-%m-%dT%X.%fZ').timestamp()
                            ))
                            from_handle = escape_markdown(users[from_id].handle) if from_id in users \
                                else user_id_url_template.format(from_id)
                            escaped_username = escape_markdown(username)
                            body_markdown = f'_{from_handle} added {escaped_username} to the group_'
                            message_markdown = f'{from_handle}: ({created_at})\n\n{body_markdown}'
                            messages.append((timestamp, message_markdown))
                    elif "participantsJoin" in message:
                        participants_join = message['participantsJoin']
                        if all(tag in participants_join for tag in ['initiatingUserId', 'userIds', 'createdAt']):
                            from_id = participants_join['initiatingUserId']
                            created_at = participants_join['createdAt']  # example: 2022-01-27T15:58:52.744Z
                            timestamp = int(round(
                                datetime.datetime.strptime(created_at, '%Y-%m-%dT%X.%fZ').timestamp()
                            ))
                            from_handle = escape_markdown(users[from_id].handle) if from_id in users \
                                else user_id_url_template.format(from_id)
                            joined_ids = participants_join['userIds']
                            joined_handles = [escape_markdown(users[joined_id].handle) if joined_id in users
                                              else user_id_url_template.format(joined_id) for joined_id in joined_ids]
                            name_list = ', '.join(joined_handles[:-1]) + \
                                        (f' and {joined_handles[-1]}' if len(joined_handles) > 1 else
                                         joined_handles[0])
                            body_markdown = f'_{from_handle} added {name_list} to the group_'
                            message_markdown = f'{from_handle}: ({created_at})\n\n{body_markdown}'
                            messages.append((timestamp, message_markdown))
                    elif "participantsLeave" in message:
                        participants_leave = message['participantsLeave']
                        if all(tag in participants_leave for tag in ['userIds', 'createdAt']):
                            created_at = participants_leave['createdAt']  # example: 2022-01-27T15:58:52.744Z
                            timestamp = int(round(
                                datetime.datetime.strptime(created_at, '%Y-%m-%dT%X.%fZ').timestamp()
                            ))
                            left_ids = participants_leave['userIds']
                            left_handles = [escape_markdown(users[left_id].handle) if left_id in users
                                            else user_id_url_template.format(left_id) for left_id in left_ids]
                            name_list = ', '.join(left_handles[:-1]) + \
                                        (f' and {left_handles[-1]}' if len(left_handles) > 1 else
                                         left_handles[0])
                            body_markdown = f'_{name_list} left the group_'
                            message_markdown = f'{name_list}: ({created_at})\n\n{body_markdown}'
                            messages.append((timestamp, message_markdown))

            # collect messages per conversation in group_conversations_messages dict
            group_conversations_messages[conversation_id].extend(messages)

    # output as one file per conversation (or part of long conversation)
    num_written_messages = 0
    num_written_files = 0
    for conversation_id, messages in group_conversations_messages.items():
        # sort messages by timestamp
        messages.sort(key=lambda tup: tup[0])
        # create conversation name for use in filename:
        # first, try to find an official name in the parsed conversation data

        # Not-so-fun fact:
        # If the name was set before the archive's owner joined the group, the name is not included
        # in the archive data and can't be found anywhere (except by looking it up from twitter,
        # and that would probably need a cookie). So there are many groups that do actually have a name,
        # but it can't be used here because we don't know it.

        group_conversations_metadata[conversation_id]['conversation_names'].sort(key=lambda tup: tup[0], reverse=True)
        official_name = group_conversations_metadata[conversation_id]['conversation_names'][0][1]
        safe_group_name = make_conversation_name_safe_for_filename(official_name)
        if len(safe_group_name) < 2:
            # discard name if it's too short (because of collision risk)
            group_name = conversation_id
        else:
            group_name = safe_group_name

        if group_name == conversation_id:
            # try to make a nice list of participant handles for the conversation name
            handles = []
            for participant_id, message_count in \
                    group_conversations_metadata[conversation_id]['participant_message_count'].items():
                if participant_id in users:
                    participant_handle = users[participant_id].handle
                    if participant_handle != username:
                        handles.append((participant_handle, message_count))
            # sort alphabetically by handle first, for a more deterministic order
            handles.sort(key=lambda tup: tup[0])
            # sort so that the most active users are at the start of the list
            handles.sort(key=lambda tup: tup[1], reverse=True)
            if len(handles) == 1:
                group_name = \
                    f'{handles[0][0]}_and_{len(group_conversations_metadata[conversation_id]["participants"]) - 1}_more'
            elif len(handles) == 2 and len(group_conversations_metadata[conversation_id]["participants"]) == 3:
                group_name = f'{handles[0][0]}_and_{handles[1][0]}_and_{username}'
            elif len(handles) >= 2:
                group_name = \
                    f'{handles[0][0]}_and_{handles[1][0]}_and' \
                    f'_{len(group_conversations_metadata[conversation_id]["participants"]) - 2}_more'
            else:
                # just use the conversation id
                group_name = conversation_id

        # create a list of names of the form '@name1, @name2 and @name3'
        # to use as a headline in the output file
        escaped_participant_names = [
            escape_markdown(participant_name)
            for participant_name in group_conversations_metadata[conversation_id]['participant_names']
        ]
        name_list = ', '.join(escaped_participant_names[:-1]) + \
                    (f' and {escaped_participant_names[-1]}'
                     if len(escaped_participant_names) > 1
                     else escaped_participant_names[0])

        if len(messages) > 1000:
            for chunk_index, chunk in enumerate(chunks(messages, 1000)):
                markdown = ''
                markdown += f'## {official_name} ##\n\n'
                markdown += f'### Group conversation between {name_list}, part {chunk_index + 1}: ###\n\n----\n\n'
                markdown += '\n\n----\n\n'.join(md for _, md in chunk)
                conversation_output_filename = paths.create_path_for_file_output_dms(
                    name=group_name, format="md", kind="DMs-Group", index=chunk_index + 1
                )
                
                # write part to a markdown file
                with open_and_mkdirs(conversation_output_filename) as f:
                    f.write(markdown)
                print(f'Wrote {len(chunk)} messages to {conversation_output_filename}')
                num_written_files += 1
        else:
            markdown = ''
            markdown += f'## {official_name} ##\n\n'
            markdown += f'### Group conversation between {name_list}: ###\n\n----\n\n'
            markdown += '\n\n----\n\n'.join(md for _, md in messages)
            conversation_output_filename = \
                paths.create_path_for_file_output_dms(name=group_name, format="md", kind="DMs-Group")

            with open_and_mkdirs(conversation_output_filename) as f:
                f.write(markdown)
            print(f'Wrote {len(messages)} messages to {conversation_output_filename}')
            num_written_files += 1

        num_written_messages += len(messages)

    print(f"\nWrote {len(group_conversations_messages)} direct message group conversations "
          f"({num_written_messages} total messages) to {num_written_files} markdown files")


def migrate_old_output(paths: PathConfig):
    """If present, moves media and cache files from the archive root to the new locations in 
    `paths.dir_output_media` and `paths.dir_output_cache`. Then deletes old output files 
    (md, html, txt) from the archive root, if the user consents."""

    # Create new folders, so we can potentially use them to move files there
    os.makedirs(paths.dir_output_media, exist_ok=True)
    os.makedirs(paths.dir_output_cache, exist_ok=True)

    # Move files that we can re-use:
    if os.path.exists(os.path.join(paths.dir_archive, "media")):
        files_to_move = glob.glob(os.path.join(paths.dir_archive, "media", "*"))
        if len(files_to_move) > 0:
            print(f"Moving {len(files_to_move)} files from 'media' to '{paths.dir_output_media}'")
            for file_path_to_move in files_to_move:
                file_name_to_move = os.path.split(file_path_to_move)[1]
                os.rename(file_path_to_move, os.path.join(paths.dir_output_media, file_name_to_move))
        os.rmdir(os.path.join(paths.dir_archive, "media"))

    known_tweets_old_path = os.path.join(paths.dir_archive, "known_tweets.json")
    known_tweets_new_path = os.path.join(paths.dir_output_cache, "known_tweets.json")
    if os.path.exists(known_tweets_old_path):
        os.rename(known_tweets_old_path, known_tweets_new_path)

    # Delete files that would be overwritten anyway (if user consents):
    output_globs = [
        "TweetArchive.html",
        "*Tweet-Archive*.html",
        "*Tweet-Archive*.md",
        "DMs-Archive-*.html",
        "DMs-Archive-*.md",
        "DMs-Group-Archive-*.html",
        "DMs-Group-Archive-*.md",
        "followers.txt",
        "following.txt",
    ]
    files_to_delete = []
    
    for output_glob in output_globs:
        files_to_delete += glob.glob(os.path.join(paths.dir_archive, output_glob))
        
    # TODO maybe remove those files only after the new ones have been generated? This way, the user would never
    # end up with less output than before. On the other hand, they might end up with old *and* new versions
    # of the output, if the script crashes before it reaches the code to delete the old version.
    if len(files_to_delete) > 0:
        print(f"\nThere are {len(files_to_delete)} files in the root of the archive,")
        print("which were probably generated from an older version of this script.")
        print("Since then, the directory layout of twitter-archive-parser has changed")
        print("and these files are generated into the sub-directory 'parser-output' or")
        print("various sub-sub-directories therein. These are the affected files:")

        for file_to_delete in files_to_delete:
            print(file_to_delete)

        user_input = input('\nOK delete these files? (If the the directory layout would not have changed, they would be overwritten anyway) [y/N]')
        if user_input.lower() in ('y', 'yes'):
            for file_to_delete in files_to_delete:
                os.remove(file_to_delete)
            print(f"Files have been deleted. New versions of these files will be generated into 'parser-output' soon.")


def is_archive(path):
    """Return true if there is a Twitter archive at the given path"""
    return os.path.isfile(os.path.join(path, 'data', 'account.js'))


def find_archive():
    """
    Search for the archive
    1. First try the working directory.
    2. Then try the script directory.
    3. Finally prompt the user.
    """
    if is_archive('.'):
        return '.'
    script_dir = os.path.dirname(__file__)
    if script_dir != os.getcwd():
        if is_archive(script_dir):
            return script_dir
    print('Archive not found in working directory or script directory.\n'
          'Please enter the path of your Twitter archive, or just press Enter to exit.\n'
          'On most operating systems, you can also try to drag and drop your archive folder '
          'into the terminal window, and it will paste its path automatically.\n')
    # Give the user as many attempts as they need.
    while True:
        input_path = input('Archive path: ')
        if not input_path:
            exit()
        if is_archive(input_path):
            return input_path
        print(f'Archive not found at {input_path}')


def main():
    archive_path = find_archive()
    paths = PathConfig(dir_archive=archive_path)

    # Extract the archive owner's username from data/account.js
    username = extract_username(paths)

    user_id_url_template = 'https://twitter.com/i/user/{}'

    html_template = """\
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet"
          href="https://unpkg.com/@picocss/pico@latest/css/pico.min.css">
    <title>Your Twitter archive!</title>
</head>
<body>
    <h1>Your twitter archive</h1>
    <main class="container">
    {}
    </main>
</body>
</html>"""

    users = {}

    migrate_old_output(paths)

    # Make a folder to copy the images and videos into.
    os.makedirs(paths.dir_output_media, exist_ok=True)
    if not os.path.isfile(paths.file_tweet_icon):
        shutil.copy('assets/images/favicon.ico', paths.file_tweet_icon)

    media_sources = parse_tweets(username, users, html_template, paths)

    following_ids = collect_user_ids_from_followings(paths)
    print(f'found {len(following_ids)} user IDs in followings.')
    follower_ids = collect_user_ids_from_followers(paths)
    print(f'found {len(follower_ids)} user IDs in followers.')
    dms_user_ids = collect_user_ids_from_direct_messages(paths)
    print(f'found {len(dms_user_ids)} user IDs in direct messages.')
    group_dms_user_ids = collect_user_ids_from_group_direct_messages(paths)
    print(f'found {len(group_dms_user_ids)} user IDs in group direct messages.')

    # bulk lookup for user handles from followers, followings, direct messages and group direct messages
    collected_user_ids_without_followers = list(
        set(following_ids).union(set(dms_user_ids)).union(set(group_dms_user_ids))
    )
    collected_user_ids_only_in_followers: set = set(follower_ids).difference(set(collected_user_ids_without_followers))
    collected_user_ids: list = list(set(collected_user_ids_without_followers)
                                    .union(collected_user_ids_only_in_followers))

    print(f'\nfound {len(collected_user_ids)} user IDs overall.')

    # give the user a choice if followers should be included in the lookup
    # (but only in case they make up a large amount):
    unknown_collected_user_ids: set = set(collected_user_ids).difference(users.keys())
    unknown_follower_user_ids: set = unknown_collected_user_ids.intersection(collected_user_ids_only_in_followers)
    if len(unknown_follower_user_ids) > 5000:
        # Account metadata observed at ~2.1KB on average.
        estimated_follower_lookup_size = int(2.1 * len(unknown_follower_user_ids))
        # we can look up at least 3000 users per minute.
        estimated_max_follower_lookup_time_in_minutes = len(unknown_follower_user_ids) / 3000
        print(
            f'For some user IDs, the @handle is not included in the archive data. '
            f'Unknown user handles can be looked up online.'
            f'{len(unknown_follower_user_ids)} of {len(unknown_collected_user_ids)} total '
            f'user IDs with unknown handles are from your followers. Online lookup would be '
            f'about {estimated_follower_lookup_size:,} KB smaller and up to '
            f'{estimated_max_follower_lookup_time_in_minutes:.1f} minutes faster without them.\n'
        )

        if not get_consent(f'Do you want to include handles of your followers '
                           f'in the online lookup of user handles anyway?', default_to_yes=True):
            collected_user_ids = collected_user_ids_without_followers

    lookup_users(collected_user_ids, users)

    parse_followings(users, user_id_url_template, paths)
    parse_followers(users, user_id_url_template, paths)
    parse_direct_messages(username, users, user_id_url_template, paths)
    parse_group_direct_messages(username, users, user_id_url_template, paths)

    # Download larger images, if the user agrees
    print(f"\nThe archive doesn't contain the original-size images. We can attempt to download them from twimg.com.")
    print(f'Please be aware that this script may download a lot of data, which will cost you money if you are')
    print(f'paying for bandwidth. Please be aware that the servers might block these requests if they are too')
    print(f'frequent. This script may not work if your account is protected. You may want to set it to public')
    print(f'before starting the download.\n')

    if get_consent('OK to start downloading?'):
        download_larger_media(media_sources, paths)
        print('In case you set your account to public before initiating the download, '
              'do not forget to protect it again.')


if __name__ == "__main__":
    main()
