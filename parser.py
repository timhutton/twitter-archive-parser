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

import datetime
import glob
import json
import os

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

def tweet_json_to_markdown(tweet, username):
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
                original_filename = os.path.split(media['media_url'])[1]
                new_filename = 'data/tweet_media/' + tweet_id_str + '-' + original_filename
                markdown = f'![]({new_filename})'
                body = body.replace(original_url, markdown)
    # append the original Twitter URL as a link
    body += f'\n\n(Originally on Twitter: [{timestamp_str}](https://twitter.com/{username}/status/{tweet_id_str}))'
    return timestamp, body

def main():

    input_folder = '.'
    output_filename = 'output.md'

    # Parse the tweets
    data_folder = os.path.join(input_folder, 'data')
    tweet_media_folder = os.path.join(data_folder, 'tweet_media')
    account_js_filename = os.path.join(data_folder, 'account.js')
    if not os.path.isfile(account_js_filename):
        print(f'Error: Failed to load {account_js_filename}. Start this script in the root folder of your Twitter archive.')
        exit()
    username = extract_username(account_js_filename)
    input_filenames = glob.glob(os.path.join(data_folder, 'tweet.js')) + \
        glob.glob(os.path.join(data_folder, 'tweets.js')) + \
        glob.glob(os.path.join(data_folder, 'tweets-part*.js'))
    tweets_markdown = []
    for tweets_js_filename in input_filenames:
        print(f'Parsing {tweets_js_filename}...')
        json = read_json_from_js_file(tweets_js_filename)
        tweets_markdown += [tweet_json_to_markdown(tweet, username) for tweet in json]
    print(f'Parsed {len(tweets_markdown)} tweets and replies by {username}.')

    # Sort tweets with oldest first
    tweets_markdown.sort(key=lambda tup: tup[0])
    tweets_markdown = [md for t,md in tweets_markdown] # discard timestamps

    # Save as one large markdown file
    all_tweets = '\n----\n'.join(tweets_markdown)
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(all_tweets)
    print(f'Wrote to {output_filename}, which embeds images from {tweet_media_folder}')

if __name__ == "__main__":
    main()
