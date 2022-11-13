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

from collections import defaultdict
import datetime
import glob
import json
import os
import shutil

def read_json_from_js_file(filename):
    """Reads the contents of a Twitter-produced .js file into a dictionary."""
    with open(filename, 'r', encoding='utf8') as f:
        data = f.readlines()
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

def tweet_json_to_markdown(tweet, username, archive_media_folder, output_media_folder_name):
    """Converts a JSON-format tweet into markdown. Returns tuple of timestamp and markdown."""
    tweet = tweet['tweet']
    timestamp_str = tweet['created_at']
    timestamp = int(round(datetime.datetime.strptime(timestamp_str, '%a %b %d %X %z %Y').timestamp())) # Example: Tue Mar 19 14:05:17 +0000 2019
    body = tweet['full_text']
    tweet_id_str = tweet['id_str']
    # replace t.co URLs with their original versions
    if 'entities' in tweet and 'urls' in tweet['entities']:
        for url in tweet['entities']['urls']:
            if 'url' in url and 'expanded_url' in url:
                body = body.replace(url['url'], url['expanded_url'])
    # replace image URLs with markdown image links to local files
    if 'entities' in tweet and 'media' in tweet['entities']:
        for media in tweet['entities']['media']:
            if 'url' in media and 'media_url' in media:
                original_url = media['url']
                original_expanded_url = media['media_url']
                original_filename = os.path.split(original_expanded_url)[1]
                local_filename = os.path.join(archive_media_folder, tweet_id_str + '-' + original_filename)
                new_url = output_media_folder_name + tweet_id_str + '-' + original_filename
                if os.path.isfile(local_filename):
                    # Found a matching image, use this one
                    shutil.copy(local_filename, new_url)
                    markdown = f'![]({new_url})'
                else:
                    # Is there any other file that includes the tweet_id in its filename?
                    media_filenames = glob.glob(os.path.join(archive_media_folder, tweet_id_str + '*'))
                    if len(media_filenames) > 0:
                        markdown = ''
                        for media_filename in media_filenames:
                            media_url = f'{output_media_folder_name}{os.path.split(media_filename)[-1]}'
                            shutil.copy(media_filename, media_url)
                            markdown += f'\n\n<video controls><source src="{media_url}">Your browser does not support the video tag.</video>\n{media_url}'
                    else:
                        print(f'Warning: missing local file: {local_filename}. Using original link instead: {original_url} (expands to {original_expanded_url})')
                        markdown = f'![]({original_url})'
                body = body.replace(original_url, markdown)
    # append the original Twitter URL as a link
    body += f'\n\n(Originally on Twitter: [{timestamp_str}](https://twitter.com/{username}/status/{tweet_id_str}))'
    return timestamp, body

def main():

    input_folder = '.'
    output_media_folder_name = 'media/'

    # Identify the file and folder names - they change slightly depending on the archive size it seems
    data_folder = os.path.join(input_folder, 'data')
    account_js_filename = os.path.join(data_folder, 'account.js')
    if not os.path.isfile(account_js_filename):
        print(f'Error: Failed to load {account_js_filename}. Start this script in the root folder of your Twitter archive.')
        exit()
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
    if len(tweet_media_folder_names)==0:
        print(f'Error: no folders matching {tweet_media_folder_name_templates} in {data_folder}')
        exit()
    if len(tweet_media_folder_names) > 1:
        print(f'Error: multiple folders matching {tweet_media_folder_name_templates} in {data_folder}')
        exit()
    archive_media_folder = tweet_media_folder_names[0]
    os.makedirs(output_media_folder_name, exist_ok = True)

    # Parse the tweets
    username = extract_username(account_js_filename)
    tweets_markdown = []
    for tweets_js_filename in input_filenames:
        print(f'Parsing {tweets_js_filename}...')
        json = read_json_from_js_file(tweets_js_filename)
        tweets_markdown += [tweet_json_to_markdown(tweet, username, archive_media_folder, output_media_folder_name) for tweet in json]
    print(f'Parsed {len(tweets_markdown)} tweets and replies by {username}.')

    # Sort tweets with oldest first
    tweets_markdown.sort(key=lambda tup: tup[0])

    # Split tweets by month
    tweets_by_month = defaultdict(str)
    for timestamp, md in tweets_markdown:
        dt = datetime.datetime.fromtimestamp(timestamp)
        filename = f'tweets_{dt.year}-{dt.month:02}.md'
        tweets_by_month[filename] += md + '\n\n----\n\n'

    # Write into files
    for filename, md in tweets_by_month.items():
        with open(filename, 'w', encoding='utf-8') as f:
            f.write(md)
    print(f'Wrote to tweets_YYYY-MM.md, with images and video embedded from {output_media_folder_name}')


if __name__ == "__main__":
    main()
