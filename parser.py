import json
import os

def read_twitter_archive(folder):
    with open(os.path.join(folder, 'data', 'tweet.js'), 'r', encoding='utf8') as f:
        data = f.readlines()
        # convert js file to JSON: replace first line with just '[', squash lines into a single string
        data = '[' + ''.join(data[1:])
        # parse the resulting JSON
        return json.loads(data)

def extract_tweet(tweet):
    tweet = tweet['tweet']
    body = tweet['full_text']
    # replace t.co URLs with their original versions
    for url in tweet['entities']['urls']:
        body = body.replace(url['url'], url['expanded_url'])
    return tweet['created_at'] + '\n' + body

def main():
    json = read_twitter_archive('.')
    tweets_text = [extract_tweet(tweet) for tweet in json]
    all_tweets = '\n\n'.join(tweets_text)
    output_filename = 'output.txt'
    with open(output_filename, 'w', encoding='utf-8') as f:
        f.write(all_tweets)
    print('Wrote to', output_filename)

if __name__ == "__main__":
    main()
