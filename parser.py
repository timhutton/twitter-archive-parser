import json
import os

def read_twitter_archive(folder):
    with open(os.path.join(folder, 'data', 'tweet.js'), 'r', encoding='utf8') as f:
        data = f.readlines()
        # convert js file to JSON: replace first line with just '[', squash lines into a single string
        data = '[' + ''.join(data[1:])
        # parse the resulting JSON
        return json.loads(data)

def extract_tweet(tweet, username):
    tweet = tweet['tweet']
    timestamp = tweet['created_at']
    body = tweet['full_text']
    tweet_id_str = tweet['id_str']
    # replace t.co URLs with their original versions
    for url in tweet['entities']['urls']:
        body = body.replace(url['url'], url['expanded_url'])
    # replace image URLs with markdown image links to local files
    if 'media' in tweet['entities']:
        for media in tweet['entities']['media']:
            original_url = media['url']
            original_filename = os.path.split(media['media_url'])[1]
            new_filename = 'tweet_media/' + tweet_id_str + '-' + original_filename
            markdown = f'![]({new_filename})'
            body = body.replace(original_url, markdown)
    # append the original Twitter URL as a link
    body += f'\n\nOriginally on Twitter: [{timestamp}](https://twitter.com/{username}/status/{tweet_id_str})'
    return body

def main():

    input_folder = '.'
    username = '_tim_hutton_'
    output_filename = 'output.txt'

    json = read_twitter_archive(input_folder)
    tweets_text = [extract_tweet(tweet, username) for tweet in json]
    all_tweets = '\n--\n'.join(tweets_text)
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(all_tweets)
    print(f'Parsed {len(json)} tweets. Wrote to', output_filename)

if __name__ == "__main__":
    main()
