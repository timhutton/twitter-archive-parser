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
import traceback
from typing import List
# hot-loaded if needed, see import_module():
#  imagesize
#  requests


# Print a compile-time error in Python < 3.6. This line does nothing in Python 3.6+ but is reported to the user
# as an error (because it is the first line that fails to compile) in older versions.
f' Error: This script requires Python 3.6 or later.'


class UserData:
    def __init__(self, id, handle = None):
        self.id = id
        self.handle = handle


def import_module(module):
    """Imports a module specified by a string. Example: requests = import_module('requests')"""
    try:
        return importlib.import_module(module)
    except ImportError:
        print(f'\nError: This script uses the "{module}" module which is not installed.\n')
        user_input = input('OK to install using pip? [y/n]')
        if not user_input.lower() in ('y', 'yes'):
            exit()
        subprocess.run([sys.executable, '-m', 'pip', 'install', module], check=True)
        return importlib.import_module(module)


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


# TODO if downloading fails within the for loop, we should be able to return the already 
# fetched users, but also make it clear that it is incomplete. Maybe do it like in get_tweets.
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

def get_tweets(session, bearer_token, guest_token, tweet_ids, include_user=True, include_alt_text=True):
    """Get the json metadata for multiple tweets.
    If include_user is False, you will only get a numerical id for the user.
    Returns `tweets, remaining_tweet_ids` where `tweets`. If all goes well, `tweets` will contain all
    tweets, and `remaining_tweet_ids` is empty. If something goes wrong, downloading is stopped
    and only the tweets we got until then are returned. 
    TODO In some cases, up to 100 tweets may be both in `tweets` and `remaining_tweet_ids`."""
    tweets = {}
    remaining_tweet_ids = tweet_ids.copy()
    try:
        while remaining_tweet_ids:
            max_batch = 100
            tweet_id_batch = remaining_tweet_ids[:max_batch]
            tweet_id_list = ",".join(map(str,tweet_id_batch))
            print(f"Download {len(tweet_id_batch)} tweets of {len(remaining_tweet_ids)} remaining...")
            query_url = f"https://api.twitter.com/1.1/statuses/lookup.json?id={tweet_id_list}&tweet_mode=extended"
            if not include_user:
                query_url += "&trim_user=1"
            if include_alt_text:
                query_url += "&include_ext_alt_text=1"
            response = session.get(query_url,
                                headers={'authorization': f'Bearer {bearer_token}', 'x-guest-token': guest_token}, timeout=5)
            if response.status_code == 429:
                # Rate limit exceeded - get a new token
                guest_token = get_twitter_api_guest_token(session, bearer_token)
                continue
            if not response.status_code == 200:
                raise Exception(f'Failed to get tweets: {response}')
            response_json = json.loads(response.content)
            for tweet in response_json:
                if "id_str" in tweet:
                    tweets[tweet["id_str"]] = tweet
                else:
                    print (f"Tweet could not be returned because it has no id: {tweet}")
            remaining_tweet_ids = remaining_tweet_ids[max_batch:]
    except Exception as err:
        traceback.print_exc()
        print(f"Exception during batch download of tweets: {err}");
        print(f"Try to work with the tweets we got so far.");
    return tweets, remaining_tweet_ids

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
    user_input = input(f'Download user data from Twitter (approx {estimated_size:,}KB)? [y/n]')
    if user_input.lower() not in ('y', 'yes'):
        return
    requests = import_module('requests')
    try:
        with requests.Session() as session:
            bearer_token = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
            guest_token = get_twitter_api_guest_token(session, bearer_token)
            retrieved_users = get_twitter_users(session, bearer_token, guest_token, filtered_user_ids)
            for user_id, user in retrieved_users.items():
                users[user_id] = UserData(user_id, user["screen_name"])
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


def extract_username(account_js_filename):
    """Returns the user's Twitter username from account.js."""
    account = read_json_from_js_file(account_js_filename)
    return account[0]['account']['username']

def collect_tweet_id(tweet):
    if 'tweet' in tweet.keys():
        tweet = tweet['tweet']
    return tweet['id_str']

# returns an int if you give it either an int or a str that can be parsed as 
# an int. Otherwise, returns None.
def parse_as_number(str_or_number):
    if isinstance(str_or_number, str):
        if str_or_number.isnumeric():
            return int(str_or_number)
        else:
            return None
    elif isinstance(str_or_number, int):
        return str_or_number
    else:
        return None

def equal_ignore_types(a, b):
    """Recognizes two things as equal even if one is a str and the other is a number (but with identical content), or if both are lists or both are dicts, and all of their nested values are equal_ignore_types"""
    if a == b:
        return True
    if parse_as_number(a) is not None and parse_as_number(b) is not None: 
        return parse_as_number(a) == parse_as_number(b)
    if isinstance(a, dict) and isinstance (b, dict):
        if len(a) != len(b):
            return False
        for key in a.keys():
            if not equal_ignore_types(a[key], b[key]):
                return False
        return True
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return False
        for i in range(len(a)):
            if not equal_ignore_types(a[i], b[i]):
                return False
        return True
    return False

def merge_lists(a: list, b: list, ignore_types:bool=False):
    """Adds all items from b to a which are not already in a. If you pass ignore_types=True, it uses equal_ignore_types internally, and also recognizes two list items as equal if they both are dicts with equal id_str values in it, which results in merging the dicts instead of adding both separately to the result. Modifies a and returns a."""
    for item_b in b:
        found_in_a = False
        if ignore_types:
            for item_a in a:
                if equal_ignore_types(item_a, item_b):
                    found_in_a = True
                    break
                if isinstance(item_a, dict) and isinstance(item_b, dict) and has_path(item_a, ['id_str']) and has_path(item_b, ['id_str']) and item_a['id_str'] == item_b['id_str']:
                    merge_dicts(item_a, item_b)
        else:
            found_in_a = item_b in a

        if not found_in_a:
            a.append(item_b)
    return a


# Taken from https://stackoverflow.com/a/7205107/39946, then adapted to
# some commonly observed twitter specifics.
def merge_dicts(a, b, path=None):
    "merges b into a"
    if path is None: path = []
    for key in b:
        if key in a:
            if isinstance(a[key], dict) and isinstance(b[key], dict):
                merge_dicts(a[key], b[key], path + [str(key)])
            elif isinstance(a[key], list) and isinstance(b[key], list):
                merge_lists(a[key], b[key], ignore_types=True)
            elif a[key] == b[key]:
                pass # same leaf value
            elif key == 'retweet_count' or key == 'favorite_count':
                a[key] = max(parse_as_number(a[key]), parse_as_number(b[key]))
            elif key in ['possibly_sensitive']:
                # ignore conflicts in unimportant fields that tend to differ
                pass
            elif parse_as_number(a[key]) == parse_as_number(b[key]):
                # Twitter sometimes puts numbers into strings, so that the same number might be 3 or '3'
                a[key] = parse_as_number(a[key])
            elif a[key] is None and b[key] is not None:
                # just as if `not key in a`
                a[key] = b[key]
            elif a[key] is not None and b[key] is None:
                # Nothing to update
                pass
            else:
                raise Exception(f"Conflict at {'.'.join(path + [str(key)])}, value '{a[key]}' vs. '{b[key]}'")
        else:
            a[key] = b[key]
    return a

def unwrap_tweet(tweet):
    if 'tweet' in tweet.keys():
        return tweet['tweet']
    else:
        return tweet

def add_known_tweet(known_tweets, new_tweet):
    tweet_id = new_tweet['id_str']
    if tweet_id in known_tweets:
        if known_tweets[tweet_id] == new_tweet:
            pass
            #print(f"Tweet {tweet_id} was already known with identical contents")
        else:
            try:
                merge_dicts(known_tweets[tweet_id], new_tweet)
            except Exception as err:
                print(traceback.format_exc())
                print(f"Tweet {tweet_id} could not be merged: {err}")
                
    else:
        #print(f"Tweet {tweet_id} is new")
        known_tweets[tweet_id] = new_tweet

def collect_tweet_references(tweet, known_tweets, counts):
    tweet = unwrap_tweet(tweet)
    tweet_ids = set()

    # Collect quoted tweets
    if has_path(tweet, ['entities', 'urls']):
        for url in tweet['entities']['urls']:
            if 'url' in url and 'expanded_url' in url:
                expanded_url = url['expanded_url']
                matches = re.match(r'^https://twitter.com/([0-9A-Za-z_]*)/status/(\d+)$', expanded_url)
                if (matches):
                    #user_handle = matches[1]
                    quoted_id = matches[2]
                    if (quoted_id in known_tweets):
                        counts['known_quote'] += 1
                    else:
                        tweet_ids.add(quoted_id)
                        print(f"Need to download tweet {tweet['id_str']} because of being quoted")
                        counts['quote'] += 1

    # Collect previous tweets in conversation
    # Only do this for tweets from our original archive
    if 'from_archive' in tweet and has_path(tweet, ['in_reply_to_status_id_str']):
        prev_tweet_id = parse_as_number(tweet['in_reply_to_status_id_str'])
        if (prev_tweet_id in known_tweets):
            counts['known_reply'] += 1
        else:
            tweet_ids.add(prev_tweet_id)
            print(f"Need to download tweet {prev_tweet_id} because of reply to it")
            counts['reply'] += 1

    # Collect retweets
    # Don't do this if we already re-downloaded this tweet
    if not 'from_api' in tweet and 'full_text' in tweet and tweet['full_text'].startswith('RT @'):
        tweet_ids.add(tweet['id_str'])
        print(f"Need to download tweet {tweet['id_str']} because of retweet")
        counts['retweet'] += 1

    # Collect tweets with media, which might lack alt text
    # TODO we might filter for media which has "type" : "photo" because there is no alt text for videos
    # Don't do this if we already re-downloaded this tweet with alt texts enabled
    if not 'download_with_alt_text' in tweet and has_path(tweet, ['entities', 'media']):
        tweet_ids.add(tweet['id_str'])
        print(f"Need to download tweet {tweet['id_str']} because of contained media")
        counts['media'] += 1

    if None in tweet_ids:
        raise Exception(f"Tweet has id None: {tweet}")

    return tweet_ids

def has_path(dict, index_path: List[str]):
    """Walks a path through nested dicts or lists, and returns True if all the keys are present, and all of the values are not None."""
    for index in index_path:
        if not index in dict:
            return False
        dict = dict[index]
        if dict is None:
            return False
    return True

def convert_tweet(tweet, username, archive_media_folder, output_media_folder_name,
                  tweet_icon_path, media_sources: dict, users, referenced_tweets):
    """Converts a JSON-format tweet. Returns tuple of timestamp, markdown and HTML."""
    # TODO actually use `referenced_tweets`
    tweet = unwrap_tweet(tweet)
    timestamp_str = tweet['created_at']
    timestamp = int(round(datetime.datetime.strptime(timestamp_str, '%a %b %d %X %z %Y').timestamp())) # Example: Tue Mar 19 14:05:17 +0000 2019
    body_markdown = tweet['full_text']
    body_html = tweet['full_text']
    tweet_id_str = tweet['id_str']
    # replace t.co URLs with their original versions
    if has_path(tweet, ['entities', 'urls']):
        for url in tweet['entities']['urls']:
            if 'url' in url and 'expanded_url' in url:
                expanded_url = url['expanded_url']
                body_markdown = body_markdown.replace(url['url'], expanded_url)
                expanded_url_html = f'<a href="{expanded_url}">{expanded_url}</a>'
                body_html = body_html.replace(url['url'], expanded_url_html)
    # if the tweet is a reply, construct a header that links the names of the accounts being replied to the tweet being replied to
    header_markdown = ''
    header_html = ''
    if has_path(tweet, ['in_reply_to_status_id']):
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
        header_markdown += f'Replying to [{name_list}]({replying_to_url})\n\n'
        header_html += f'Replying to <a href="{replying_to_url}">{name_list}</a><br>'
    # replace image URLs with image links to local files
    if has_path(tweet, ['entities', 'media']) and has_path(tweet, ['extended_entities', 'media']) \
        and len(tweet['entities']['media']) > 0 and 'url' in tweet['entities']['media'][0]:
            
        original_url = tweet['entities']['media'][0]['url']
        markdown = ''
        html = ''
        for media in tweet['extended_entities']['media']:
            if 'url' in media and 'media_url' in media:
                original_expanded_url = media['media_url']
                original_filename = os.path.split(original_expanded_url)[1]
                archive_media_filename = tweet_id_str + '-' + original_filename
                archive_media_path = os.path.join(archive_media_folder, archive_media_filename)
                new_url = output_media_folder_name + archive_media_filename
                markdown += '' if not markdown and body_markdown == original_url else '\n\n'
                html += '' if not html and body_html == original_url else '<br>'
                # if file exists, this means that file is probably an image (not a video)
                if os.path.isfile(archive_media_path):
                    # Found a matching image, use this one
                    if not os.path.isfile(new_url):
                        shutil.copy(archive_media_path, new_url)
                    markdown += f'![]({new_url})'
                    html += f'<img src="{new_url}"/>'
                    # Save the online location of the best-quality version of this file, for later upgrading if wanted
                    best_quality_url = f'https://pbs.twimg.com/media/{original_filename}:orig'
                    media_sources[os.path.join(output_media_folder_name, archive_media_filename)] = best_quality_url
                else:
                    # If the file does not exists, it might be a video. Then its filename might
                    # be found like this:
                    # Is there any other file that includes the tweet_id in its filename?
                    archive_media_paths = glob.glob(os.path.join(archive_media_folder, tweet_id_str + '*'))
                    if len(archive_media_paths) > 0:
                        for archive_media_path in archive_media_paths:
                            archive_media_filename = os.path.split(archive_media_path)[-1]
                            media_url = f'{output_media_folder_name}{archive_media_filename}'
                            if not os.path.isfile(media_url):
                                shutil.copy(archive_media_path, media_url)
                            markdown += f'<video controls><source src="{media_url}">Your browser does not support the video tag.</video>\n'
                            html += f'<video controls><source src="{media_url}">Your browser does not support the video tag.</video>\n'
                            # Save the online location of the best-quality version of this file, for later upgrading if wanted
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
                                    print(f"Warning No URL found for {original_url} {original_expanded_url} {archive_media_path} {media_url}")
                                    print(f"JSON: {tweet}")
                                else:
                                    media_sources[os.path.join(output_media_folder_name, archive_media_filename)] = best_quality_url
                    else:
                        print(f'Warning: missing local file: {archive_media_path}. Using original link instead: {original_url} (expands to {original_expanded_url})')
                        markdown += f'![]({original_url})'
                        html += f'<a href="{original_url}">{original_url}</a>'
        body_markdown = body_markdown.replace(original_url, markdown)
        body_html = body_html.replace(original_url, html)
    # make the body a quote
    body_markdown = '> ' + '\n> '.join(body_markdown.splitlines())
    body_html = '<p><blockquote>' + '<br>\n'.join(body_html.splitlines()) + '</blockquote>'
    # append the original Twitter URL as a link
    original_tweet_url = f'https://twitter.com/{username}/status/{tweet_id_str}'
    body_markdown = header_markdown + body_markdown + f'\n\n<img src="{tweet_icon_path}" width="12" /> [{timestamp_str}]({original_tweet_url})'
    body_html = header_html + body_html + f'<a href="{original_tweet_url}"><img src="{tweet_icon_path}" width="12" />&nbsp;{timestamp_str}</a></p>'
    # extract user_id:handle connections
    if 'in_reply_to_user_id' in tweet and 'in_reply_to_screen_name' in tweet:
        id = tweet['in_reply_to_user_id']
        if id is not None and int(id) >= 0: # some ids are -1, not sure why
            handle = tweet['in_reply_to_screen_name']
            users[id] = UserData(id=id, handle=handle)
    if 'entities' in tweet and 'user_mentions' in tweet['entities'] and tweet['entities']['user_mentions'] is not None:
        for mention in tweet['entities']['user_mentions']:
            id = mention['id']
            if int(id) >= 0: # some ids are -1, not sure why
                handle = mention['screen_name']
                users[id] = UserData(id=id, handle=handle)

    return timestamp, body_markdown, body_html


def find_input_filenames(data_folder):
    """Identify the tweet archive's file and folder names - they change slightly depending on the archive size it seems."""
    tweet_js_filename_templates = ['tweet.js', 'tweets.js', 'tweets-part*.js']
    input_filenames = []
    for tweet_js_filename_template in tweet_js_filename_templates:
        input_filenames += glob.glob(os.path.join(data_folder, tweet_js_filename_template))
    if len(input_filenames)==0:
        print(f'Error: no files matching {tweet_js_filename_templates} in {data_folder}')
        exit()
    tweet_media_folder_name_templates = ['tweet_media', 'tweets_media']
    tweet_media_folder_names = []
    for tweet_media_folder_name_template in tweet_media_folder_name_templates:
        tweet_media_folder_names += glob.glob(os.path.join(data_folder, tweet_media_folder_name_template))
    if len(tweet_media_folder_names) == 0:
        print(f'Error: no folders matching {tweet_media_folder_name_templates} in {data_folder}')
        exit()
    if len(tweet_media_folder_names) > 1:
        print(f'Error: multiple folders matching {tweet_media_folder_name_templates} in {data_folder}')
        exit()
    archive_media_folder = tweet_media_folder_names[0]
    return input_filenames, archive_media_folder


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
                # Try to get content of response as `res.text`. For twitter.com, this will be empty in most (all?) cases.
                # It is successfully tested with error responses from other domains.
                raise Exception(f'Download failed with status "{res.status_code} {res.reason}". Response content: "{res.text}"')
            byte_size_after = int(res.headers['content-length'])
            if (byte_size_after != byte_size_before):
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

                if (width_before == -1 and height_before == -1 and width_after == -1 and height_after == -1):
                    # could not check size of both versions, probably a video or unsupported image format
                    os.replace(tmp_filename, filename)
                    bytes_percentage_increase = 100.0 * (byte_size_after - byte_size_before) / byte_size_before
                    logging.info(f'{pref}SUCCESS. New version is {bytes_percentage_increase:3.0f}% '
                                 f'larger in bytes (pixel comparison not possible). {post}')
                    return True, byte_size_after
                elif (width_before == -1 or height_before == -1 or width_after == -1 or height_after == -1):
                    # could not check size of one version, this should not happen (corrupted download?)
                    logging.info(f'{pref}SKIPPED. Pixel size comparison inconclusive: '
                                 f'{width_before}*{height_before}px vs. {width_after}*{height_after}px. {post}')
                    return False, byte_size_after
                elif (pixels_after >= pixels_before):
                    os.replace(tmp_filename, filename)
                    bytes_percentage_increase = 100.0 * (byte_size_after - byte_size_before) / byte_size_before
                    if (bytes_percentage_increase >= 0):
                        logging.info(f'{pref}SUCCESS. New version is {bytes_percentage_increase:3.0f}% larger in bytes '
                                    f'and {pixels_percentage_increase:3.0f}% larger in pixels. {post}')
                    else:
                        logging.info(f'{pref}SUCCESS. New version is actually {-bytes_percentage_increase:3.0f}% smaller in bytes '
                                f'but {pixels_percentage_increase:3.0f}% larger in pixels. {post}')
                    return True, byte_size_after
                else:
                    logging.info(f'{pref}SKIPPED. Online version has {-pixels_percentage_increase:3.0f}% smaller pixel size. {post}')
                    return True, byte_size_after
            else:
                logging.info(f'{pref}SKIPPED. Online version is same byte size, assuming same content. Not downloaded.')
                return True, 0
    except Exception as err:
        logging.error(f"{pref}FAIL. Media couldn't be retrieved from {url} because of exception: {err}")
        return False, 0


def download_larger_media(media_sources: dict, log_path):
    """Uses (filename, URL) tuples in media_sources to download files from remote storage.
       Aborts downloads if the remote file is the same size or smaller than the existing local version.
       Retries the failed downloads several times, with increasing pauses between each to avoid being blocked.
    """
    # Log to file as well as the console
    logging.basicConfig(stream=sys.stdout, level=logging.INFO, format='%(message)s')
    logfile_handler = logging.FileHandler(filename=log_path, mode='w')
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
        for index, (local_media_path, media_url) in enumerate(media_sources.items()):
            success, bytes_downloaded = download_file_if_larger(media_url, local_media_path, index + 1, number_of_files, sleep_time)
            if success:
                success_count += 1
            else:
                retries.append((local_media_path, media_url))
            total_bytes_downloaded += bytes_downloaded
        media_sources = retries
        remaining_tries -= 1
        sleep_time += 2
        logging.info(f'\n{success_count} of {number_of_files} tested media files are known to be the best-quality available.\n')
        if len(retries) == 0:
            break
        if remaining_tries > 0:
            print(f'----------------------\n\nRetrying the ones that failed, with a longer sleep. {remaining_tries} tries remaining.\n')
    end_time = time.time()

    logging.info(f'Total downloaded: {total_bytes_downloaded/2**20:.1f}MB = {total_bytes_downloaded/2**30:.2f}GB')
    logging.info(f'Time taken: {end_time-start_time:.0f}s')
    print(f'Wrote log to {log_path}')


def parse_tweets(input_filenames, username, users, html_template, archive_media_folder,
                 output_media_folder_name, tweet_icon_path, output_html_filename) -> dict:
    """Read tweets from input_filenames, write to *.md and output_html_filename.
       Copy the media used to output_media_folder_name.
       Collect user_id:user_handle mappings for later use, in 'users'.
       Returns the mapping from media filename to best-quality URL.
    """
    converted_tweets = []
    media_sources = {}
    counts = defaultdict(int)
    known_tweets = {}

    # TODO If we run this tool multiple times, in `known_tweets` we will have our own tweets as
    # well as related tweets by others. With each run, the tweet graph is expanded. We probably do
    # not want this. To stop it, implement one of these:
    # 1. keep own tweets and other tweets in different dicts
    # 2. put them all in one dict, but mark the tweets by others, so that certain steps will ignore them
    # 3. use the data that is already present in a tweet to distinguish own tweets from others

    # Load tweets that we saved in an earlier run between pass 2 and 3
    tweet_dict_filename = 'known_tweets.json'
    if os.path.exists(tweet_dict_filename):
        with open(tweet_dict_filename, 'r', encoding='utf8') as f:
            known_tweets = json.load(f)
    
    # Fist pass: Load tweets from all archive files and add them to known_tweets
    for tweets_js_filename in input_filenames:
        json_result = read_json_from_js_file(tweets_js_filename)
        for tweet in json_result:
            tweet = unwrap_tweet(tweet)
            tweet['from_archive'] = True
            add_known_tweet(known_tweets, tweet)

    tweet_ids_to_download = set()
    
    # Second pass: Iterate through all those tweets
    for tweet in known_tweets.values():
        tweet_ids_to_download.update(collect_tweet_references(tweet, known_tweets, counts))

    # (Maybe) download referenced tweets
    # TODO ask user for consent to download
    referenced_tweets = []
    if (len(tweet_ids_to_download) > 0):
        print(f"Found references to {len(tweet_ids_to_download)} tweets which should be downloaded. Breakdown of download reasons:")
        for reason in ['quote', 'reply', 'retweet', 'media']:
            print(f" * {counts[reason]} because of {reason}")
        print(f"There were {counts['known_reply']} references to tweets which are already known so we don't need to download them (not included in the numbers above).")
        # TODO maybe ask the user if we should start downloading
        # TODO maybe give an estimate of download size and/or time
        # TODO maybe let the user choose which of the tweets to download, by selecting a subset of those reasons
        requests = import_module('requests')
        try:
            with requests.Session() as session:
                bearer_token = 'AAAAAAAAAAAAAAAAAAAAANRILgAAAAAAnNwIzUejRCOuH5E6I8xnZz4puTs%3D1Zv7ttfk8LF81IUq16cHjhLTvJu4FA33AGWWjCpTnA'
                guest_token = get_twitter_api_guest_token(session, bearer_token)
                # TODO We could download user data together with the tweets, because we will need it anyway. But we might download the data for each user multiple times then.
                downloaded_tweets, remaining_tweet_ids = get_tweets(session, bearer_token, guest_token, list(tweet_ids_to_download), False)
                # TODO maybe react if remaining_tweet_ids contains tweets
                for downloaded_tweet in downloaded_tweets.values():
                    downloaded_tweet = unwrap_tweet(downloaded_tweet)
                    downloaded_tweet['from_api'] = True
                    downloaded_tweet['download_with_user'] = False
                    downloaded_tweet['download_with_alt_text'] = True
                    add_known_tweet(known_tweets, downloaded_tweet)
                with open(tweet_dict_filename, "w") as outfile:
                    json.dump(known_tweets, outfile, indent=2)
                print(f"Saved {len(known_tweets)} tweets to '{tweet_dict_filename}'.")

        except Exception as err:
            print(f'Failed to download tweets: {err}')

    # Third pass: convert tweets, using the downloaded references from pass 2
    for tweet in known_tweets.values():
        try:
            converted_tweets.append(convert_tweet(tweet, username, archive_media_folder,
                                        output_media_folder_name, tweet_icon_path,
                                        media_sources, users, referenced_tweets))
        except Exception as err:
            print(f"Could not convert tweet {tweet['id_str']} because: {err}")
    converted_tweets.sort(key=lambda tup: tup[0]) # oldest first

    # Group tweets by month (for markdown)
    grouped_tweets_markdown = defaultdict(list)
    for timestamp, md, _ in converted_tweets:
        # Use a markdown filename that can be imported into Jekyll: YYYY-MM-DD-your-title-here.md
        dt = datetime.datetime.fromtimestamp(timestamp)
        markdown_filename = f'{dt.year}-{dt.month:02}-01-Tweet-Archive-{dt.year}-{dt.month:02}.md' # change to group by day or year or timestamp
        grouped_tweets_markdown[markdown_filename].append(md)

    # Write into *.md files
    for filename, md in grouped_tweets_markdown.items():
        md_string =  '\n\n----\n\n'.join(md)
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(md_string)

    # Write into html file
    all_html_string = '<hr>\n'.join(html for _, _, html in converted_tweets)
    with open(output_html_filename, 'w', encoding='utf-8') as f:
        f.write(html_template.format(all_html_string))

    print(f'Wrote {len(converted_tweets)} tweets to *.md and {output_html_filename}, with images and video embedded from {output_media_folder_name}')

    return media_sources


def parse_followings(data_folder, users, user_id_URL_template, output_following_filename):
    """Parse data_folder/following.js, write to output_following_filename.
       Query Twitter API for the missing user handles, if the user agrees.
    """
    following = []
    following_json = read_json_from_js_file(os.path.join(data_folder, 'following.js'))
    following_ids = []
    for follow in following_json:
        if 'following' in follow and 'accountId' in follow['following']:
            following_ids.append(follow['following']['accountId'])
    lookup_users(following_ids, users)
    for id in following_ids:
        handle = users[id].handle if id in users else '~unknown~handle~'
        following.append(handle + ' ' + user_id_URL_template.format(id))
    following.sort()
    with open(output_following_filename, 'w', encoding='utf8') as f:
        f.write('\n'.join(following))
    print(f"Wrote {len(following)} accounts to {output_following_filename}")


def parse_followers(data_folder, users, user_id_URL_template, output_followers_filename):
    """Parse data_folder/followers.js, write to output_followers_filename.
       Query Twitter API for the missing user handles, if the user agrees.
    """
    followers = []
    follower_json = read_json_from_js_file(os.path.join(data_folder, 'follower.js'))
    follower_ids = []
    for follower in follower_json:
        if 'follower' in follower and 'accountId' in follower['follower']:
            follower_ids.append(follower['follower']['accountId'])
    lookup_users(follower_ids, users)
    for id in follower_ids:
        handle = users[id].handle if id in users else '~unknown~handle~'
        followers.append(handle + ' ' + user_id_URL_template.format(id))
    followers.sort()
    with open(output_followers_filename, 'w', encoding='utf8') as f:
        f.write('\n'.join(followers))
    print(f"Wrote {len(followers)} accounts to {output_followers_filename}")


def parse_direct_messages(data_folder, username, users, user_id_URL_template, dm_output_filename_template):
    """Parse data_folder/direct-messages.js, write to one markdown file per conversation.
       Query Twitter API for the missing user handles, if the user agrees.
    """
    # Scan the DMs for missing user handles
    dms_json = read_json_from_js_file(os.path.join(data_folder, 'direct-messages.js'))
    dm_user_ids = set()
    for conversation in dms_json:
        if 'dmConversation' in conversation and 'conversationId' in conversation['dmConversation']:
            dm_conversation = conversation['dmConversation']
            conversation_id = dm_conversation['conversationId']
            user1_id, user2_id = conversation_id.split('-')
            dm_user_ids.add(user1_id)
            dm_user_ids.add(user2_id)
    lookup_users(list(dm_user_ids), users)
    # Parse the DMs
    num_written_messages = 0
    long_conversations = []
    for conversation in dms_json:
        markdown = ''
        if 'dmConversation' in conversation and 'conversationId' in conversation['dmConversation']:
            dm_conversation = conversation['dmConversation']
            conversation_id = dm_conversation['conversationId']
            user1_id,user2_id = conversation_id.split('-')
            user1_handle = users[user1_id].handle if user1_id in users else user_id_URL_template.format(user1_id)
            user2_handle = users[user2_id].handle if user2_id in users else user_id_URL_template.format(user2_id)
            markdown += f'## Conversation between {user1_handle} and {user2_handle}: ##\n'
            messages = []
            if 'messages' in dm_conversation:
                for message in dm_conversation['messages']:
                    if 'messageCreate' in message:
                        messageCreate = message['messageCreate']
                        if all(tag in messageCreate for tag in ['senderId', 'recipientId', 'text', 'createdAt']):
                            from_id = messageCreate['senderId']
                            to_id = messageCreate['recipientId']
                            body = messageCreate['text']
                            created_at = messageCreate['createdAt'] # example: 2022-01-27T15:58:52.744Z
                            timestamp = int(round(datetime.datetime.strptime(created_at, '%Y-%m-%dT%X.%fZ').timestamp()))
                            from_handle = users[from_id].handle if from_id in users else user_id_URL_template.format(from_id)
                            to_handle = users[to_id].handle if to_id in users else user_id_URL_template.format(to_id)
                            message_markdown = f'\n\n### {from_handle} -> {to_handle}: ({created_at}) ###\n```\n{body}\n```'
                            messages.append((timestamp, message_markdown))
            messages.sort(key=lambda tup: tup[0])
            markdown += ''.join(md for _, md in messages)
            num_written_messages += len(messages)

            # output as one file per conversation
            other_user_id = user2_id if user1_handle == username else user1_id
            other_user: str = users[other_user_id].handle if other_user_id in users else other_user_id
            conversation_output_filename = dm_output_filename_template.format(other_user)

            # if there are 1000 or more messages, the conversation is split up in the twitter archive.
            # The first output file should not be overwritten, so the filename has to be adapted.
            if len(messages) > 999 or other_user in long_conversations:
                long_conversations.append(other_user)
            if other_user in long_conversations:
                part_count = 0
                for name in long_conversations:
                    if name == other_user:
                        part_count += 1
                conversation_output_filename = dm_output_filename_template.format(other_user+'_part'+str(part_count))

            with open(conversation_output_filename, 'w', encoding='utf8') as f:
                f.write(markdown)
            print(f'Wrote {len(messages)} messages to {conversation_output_filename}')

    print(f"\nWrote {len(dms_json)} direct message conversations ({num_written_messages} total messages) to markdown files")


def main():

    input_folder = '.'
    output_media_folder_name = 'media/'
    tweet_icon_path = f'{output_media_folder_name}tweet.ico'
    output_html_filename = 'TweetArchive.html'
    data_folder = os.path.join(input_folder, 'data')
    account_js_filename = os.path.join(data_folder, 'account.js')
    log_path = os.path.join(output_media_folder_name, 'download_log.txt')
    output_following_filename = 'following.txt'
    output_followers_filename = 'followers.txt'
    user_id_URL_template = 'https://twitter.com/i/user/{}'
    dm_output_filename_template = 'DMs-Archive-{}.md'

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

    # Extract the username from data/account.js
    if not os.path.isfile(account_js_filename):
        print(f'Error: Failed to load {account_js_filename}. Start this script in the root folder of your Twitter archive.')
        exit()
    username = extract_username(account_js_filename)

    # Identify the file and folder names - they change slightly depending on the archive size it seems.
    input_filenames, archive_media_folder = find_input_filenames(data_folder)

    # Make a folder to copy the images and videos into.
    os.makedirs(output_media_folder_name, exist_ok = True)
    if not os.path.isfile(tweet_icon_path):
        shutil.copy('assets/images/favicon.ico', tweet_icon_path);

    media_sources = parse_tweets(input_filenames, username, users, html_template, archive_media_folder,
                                 output_media_folder_name, tweet_icon_path, output_html_filename)
    parse_followings(data_folder, users, user_id_URL_template, output_following_filename)
    parse_followers(data_folder, users, user_id_URL_template, output_followers_filename)
    parse_direct_messages(data_folder, username, users, user_id_URL_template, dm_output_filename_template)

    # Download larger images, if the user agrees
    print(f"\nThe archive doesn't contain the original-size images. We can attempt to download them from twimg.com.")
    print(f'Please be aware that this script may download a lot of data, which will cost you money if you are')
    print(f'paying for bandwidth. Please be aware that the servers might block these requests if they are too')
    print(f'frequent. This script may not work if your account is protected. You may want to set it to public')
    print(f'before starting the download.')
    user_input = input('\nOK to start downloading? [y/n]')
    if user_input.lower() in ('y', 'yes'):
        download_larger_media(media_sources, log_path)
        print('In case you set your account to public before initiating the download, do not forget to protect it again.')


if __name__ == "__main__":
    main()
