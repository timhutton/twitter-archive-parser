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
        start_char = int(url['indices'][0])
        end_char = int(url['indices'][1])
        body = body[:start_char] + url['expanded_url'] + body[end_char:]
    return body

def main():
    json = read_twitter_archive('.')
    tweets_text = [extract_tweet(tweet) for tweet in json]
    all_tweets = '\n\n'.join(tweets_text)
    with open('output.txt', 'w', encoding='utf-8') as f:
        f.write(all_tweets)


if __name__ == "__main__":
    main()