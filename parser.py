import json
import os

def read_json_from_js_file(filename):
    """Reads the contents of a Twitter-produced .js file into a dictionary."""
    with open(filename, 'r', encoding='utf8') as f:
        data = f.readlines()
        # convert js file to JSON: replace first line with just '[', squash lines into a single string
        data = '[' + ''.join(data[1:])
        # parse the resulting JSON and return as a dict
        return json.loads(data)

def extract_username(account_js_filename):
    """Returns the user's Twitter username from account.js."""
    account = read_json_from_js_file(account_js_filename)
    return account[0]['account']['username']

def tweet_json_to_markdown(tweet, username):
    """Converts a JSON-format tweet into markdown."""
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
            new_filename = 'data/tweet_media/' + tweet_id_str + '-' + original_filename
            markdown = f'![]({new_filename})'
            body = body.replace(original_url, markdown)
    # append the original Twitter URL as a link
    body += f'\n\n(Originally on Twitter: [{timestamp}](https://twitter.com/{username}/status/{tweet_id_str}))'
    return body

def main():

    input_folder = '.'
    output_filename = 'output.md'

    # Parse the tweets
    tweets_js_filename = os.path.join(input_folder, 'data', 'tweet.js')
    if not os.path.isfile(tweets_js_filename):
        print(f'Error: Failed to load {tweets_js_filename}. Start this script in the root folder of your Twitter archive.')
        exit()
    json = read_json_from_js_file(tweets_js_filename)
    account_js_filename = os.path.join(input_folder, 'data', 'account.js')
    username = extract_username(account_js_filename)
    tweets_markdown = [tweet_json_to_markdown(tweet, username) for tweet in json]
    print(f'Parsed {len(json)} tweets by {username}.')

    # Save as one large markdown file
    all_tweets = '\n----\n'.join(tweets_markdown)
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(all_tweets)
    print(f'Wrote to {output_filename}')

if __name__ == "__main__":
    main()
