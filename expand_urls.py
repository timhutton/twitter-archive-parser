import configparser
import glob
import os
import re
import requests
import time
from urllib.parse import urlparse
from parser import read_json_from_js_file

class URLExpander:
    def __init__(self):
        self.config = configparser.ConfigParser(allow_no_value=True, interpolation=None, strict=False)
        self.config.optionxform = str
        self.config.read('expand_urls.ini')
        try:
            self.shorteners = self.config.options('shorteners')
        except configparser.Error:
            print('No configuration found, using default configuration')
            self.config['shorteners'] = {}
            self.config['mappings'] = {}
            self.shorteners = ['t.co', '7ax.de', 'bit.ly', 'buff.ly', 'cnn.it', 'ct.de', 'flic.kr', 'go.shr.lc', 'ift.tt', 'instagr.am', 'is.gd', 'j.mp', 'ku-rz.de', 'p.dw.com', 'pl0p.de', 'spon.de', 'sz.de', 'tiny.cc', 'tinyurl.com', 'trib.al', 'wp.me', 'www.sz.de', 'yfrog.com']
            [self.config.set('shorteners', x) for x in self.shorteners]
            with open('expand_urls.ini', 'w') as inifile:
                self.config.write(inifile)

    def get_input_filenames(self):
        input_folder = '.'

        # Identify the file and folder names - they change slightly depending on the archive size it seems
        data_folder = os.path.join(input_folder, 'data')
        tweet_js_filename_templates = ['tweet.js', 'tweets.js', 'tweets-part*.js']
        input_filenames = []
        for tweet_js_filename_template in tweet_js_filename_templates:
            input_filenames += glob.glob(os.path.join(data_folder, tweet_js_filename_template))
        if len(input_filenames)==0:
            print(f'Error: no files matching {tweet_js_filename_templates} in {data_folder}')
            exit()
        return input_filenames

    def process_tweets(self):
        for tweets_js_filename in self.get_input_filenames():
            print(f'Parsing {tweets_js_filename}...')
            json = read_json_from_js_file(tweets_js_filename)
            [self.parse_tweet(tweet) for tweet in json]

    def save_mapping(self, original_url, expanded_url):
        self.config['mappings'][original_url] = expanded_url
        with open('expand_urls.ini', 'w') as inifile:
            self.config.write(inifile)

    def mapping_exists(self, original_url):
        try:
            tmp = self.config['mappings'][original_url]
        except KeyError:    # TODO: this fails always
            return False
        return True

    def parse_tweet(self, tweet):
        tweet = tweet['tweet']
        if 'entities' in tweet and 'urls' in tweet['entities'] and len(tweet['entities']['urls']) > 0:
            for url in tweet['entities']['urls']:
                if 'url' in url and 'expanded_url' in url:
                    original_url = url['expanded_url']
                    if not self.mapping_exists(original_url):
                        expanded_url = self.expand_short_url(original_url)
                        if expanded_url != original_url:
                            self.save_mapping(original_url, expanded_url)
        else:
            # really old tweets may contain URLs as plain text in the body
            possible_urls = re.finditer(r"https?://[a-z0-9\.]+/[a-z0-9?]{10}", tweet['full_text'], re.MULTILINE | re.IGNORECASE)
            for (_, match) in enumerate(possible_urls):
                matched_url = match.group(0)
                if not self.mapping_exists(matched_url):
                    expanded_url = self.expand_short_url(matched_url)
                    if (expanded_url != matched_url):
                        self.save_mapping(matched_url, expanded_url)

    def is_short_url(self, url):
        hostname = urlparse(url).hostname
        if any(shortener == hostname for shortener in self.shorteners):
            return True
        return False

    def expand_short_url(self, url):
        if self.is_short_url(url):
            try:
                request = requests.head(url)
                time.sleep(0.75)
            except:
                pass
            if request.ok == False:
                return url
            try:
                url_from_location_header = request.headers['location']
            except KeyError:
                return url
            if not url_from_location_header.startswith('http'):
                return url
            elif ':443' in url_from_location_header or self.is_short_url(url_from_location_header):
                url_from_location_header = self.expand_short_url(url_from_location_header.replace('http:', 'https:'))
            url = url_from_location_header
        return url

if __name__ == '__main__':
    URLExpander().process_tweets()
