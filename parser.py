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
import re
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

def convert_tweet(tweet, username, archive_media_folder, output_media_folder_name,
                           tweet_icon_path, media_sources):
    """Converts a JSON-format tweet. Returns tuple of timestamp, markdown and HTML."""
    tweet = tweet['tweet']
    timestamp_str = tweet['created_at']
    timestamp = int(round(datetime.datetime.strptime(timestamp_str, '%a %b %d %X %z %Y').timestamp())) # Example: Tue Mar 19 14:05:17 +0000 2019
    body_markdown = tweet['full_text']
    body_html = tweet['full_text']
    tweet_id_str = tweet['id_str']
    # replace t.co URLs with their original versions
    if 'entities' in tweet and 'urls' in tweet['entities']:
        for url in tweet['entities']['urls']:
            if 'url' in url and 'expanded_url' in url:
                expanded_url = url['expanded_url']
                body_markdown = body_markdown.replace(url['url'], expanded_url)
                expanded_url_html = f'<a href="{expanded_url}">{expanded_url}</a>'
                body_html = body_html.replace(url['url'], expanded_url_html)
    # if the tweet is a reply, construct a header that links the names of the accounts being replied to the tweet being replied to
    header_markdown = ''
    header_html = ''
    if 'in_reply_to_status_id' in tweet:
        # match and remove all occurences of '@username ' at the start of the body
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
    if 'entities' in tweet and 'media' in tweet['entities'] and 'extended_entities' in tweet and 'media' in tweet['extended_entities']:
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
                if os.path.isfile(archive_media_path):
                    # Found a matching image, use this one
                    if not os.path.isfile(new_url):
                        shutil.copy(archive_media_path, new_url)
                    markdown += f'![]({new_url})'
                    html += f'<img src="{new_url}"/>'
                    # Save the online location of the best-quality version of this file, for later upgrading if wanted
                    best_quality_url = f'https://pbs.twimg.com/media/{original_filename}:orig'
                    media_sources.write(' '.join([archive_media_filename, best_quality_url]) + '\n')
                else:
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
                                    media_sources.write(' '.join([archive_media_filename, best_quality_url]) + '\n')
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
    return timestamp, body_markdown, body_html

def main():

    input_folder = '.'
    output_media_folder_name = 'media/'
    tweet_icon_path = f'{output_media_folder_name}tweet.ico'
    media_sources_filename = 'media_sources.txt'
    output_html_filename = 'TweetArchive.html'

    HTML = """\
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

    if not os.path.isfile(tweet_icon_path):
        shutil.copy('assets/images/favicon.ico', tweet_icon_path);

    username = extract_username(account_js_filename)

    # Parse the tweets
    tweets = []
    with open(os.path.join(output_media_folder_name, media_sources_filename), 'w') as media_sources:
        for tweets_js_filename in input_filenames:
            print(f'Parsing {tweets_js_filename}...')
            json = read_json_from_js_file(tweets_js_filename)
            for tweet in json:
                tweets.append(convert_tweet(tweet, username, archive_media_folder,
                                            output_media_folder_name, tweet_icon_path,
                                            media_sources))
    print(f'Parsed {len(tweets)} tweets and replies by {username}.')

    # Sort tweets with oldest first
    tweets.sort(key=lambda tup: tup[0])

    # Group tweets by month (for markdown)
    grouped_tweets_markdown = defaultdict(list)
    for timestamp, md, html in tweets:
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
    all_html_string = '<hr>\n'.join(html for _, _, html in tweets)
    with open(output_html_filename, 'w', encoding='utf-8') as f:
        f.write(HTML.format(all_html_string))

    print(f'Wrote tweets to *.md and *.html, with images and video embedded from {output_media_folder_name}')

    # Tell the user that it is possible to download better-quality media
    print("\nThe archive doesn't contain the original-size images. If you are interested in retrieving the original images")
    print("from Twitter then please run the script download_better_images.py")


if __name__ == "__main__":
    main()
