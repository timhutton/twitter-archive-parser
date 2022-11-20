## How do I use it?
1. [Download your Twitter archive](https://twitter.com/settings/download_your_data) (Settings > Your account > Download an archive of your data).
2. Unzip to a folder.
3. Right-click this link [parser.py](https://raw.githubusercontent.com/timhutton/twitter-archive-parser/main/parser.py) and select "Save Link as", and save into the folder where you extracted the archive.
    - Or with wget: `wget https://raw.githubusercontent.com/timhutton/twitter-archive-parser/main/parser.py` 
4. Run parser.py with [Python3](https://realpython.com/installing-python/). e.g. `python parser.py` from a command prompt opened in that folder.

If you are having problems, the discussion here might be useful: https://mathstodon.xyz/@timhutton/109316834651128246

## What does it do?
The Twitter archive gives you a bunch of data and an HTML file (`Your archive.html`). Open that file to take a look! It lets you view your tweets in a nice interface. It has some flaws but maybe that's all you need. If so then stop here, you don't need our script.

Flaws of the Twitter archive:
- It shows you tweets you posted with images, but if you click on one of the images to expand it then it takes you to the Twitter website. If you are offline or have deleted your account or twitter.com is down then that won't work.
- The tweets are stored in a complex JSON structure so you can't just copy them into your blog for example.
- The images they give you are smaller than the ones you uploaded. I don't know why they would do this to us.
- DMs are included but don't show you who they are from - many of the user handles aren't included in the archive.
- The links are all obfuscated in a short form using t.co, which hides their origin and redirects traffic to Twitter, giving them analytics. Also they will stop working if t.co goes down.

Our script does the following:
- Converts the tweets to [markdown](https://en.wikipedia.org/wiki/Markdown) and also HTML, with embedded images, videos and links.
- Replaces t.co URLs with their original versions (the ones that can be found in the archive).
- Copies used images to an output folder, to allow them to be moved to a new home.
- Will query Twitter for the missing user handles (checks with you first).
- Converts DMs to markdown. Basic functionality for now, pending improvements.
- Outputs lists of followers and following.
- Downloads the original size images (checks with you first).

### For advanced users:

Some of the functionality requires the `requests` and `imagesize` modules. `parser.py` will offer to install these for you using pip. To avoid that you can install them before running the script.

## TODO:
- DM improvements ([#80](https://github.com/timhutton/twitter-archive-parser/issues/80))
- Likes ([#22](https://github.com/timhutton/twitter-archive-parser/issues/22)), ALT-text ([#20](https://github.com/timhutton/twitter-archive-parser/issues/20))
- Expand all URL shorteners ([#42](https://github.com/timhutton/twitter-archive-parser/pull/42)): bit.ly, goo.gl etc.
- Handle reply-to-self threads ([#23](https://github.com/timhutton/twitter-archive-parser/pull/23))

## Related tools:
If our script doesn't do what you want then maybe a different tool will help:
- https://github.com/selfawaresoup/twitter-tools
- https://github.com/roobottom/twitter-archive-to-markdown-files
- https://gist.github.com/divyajyotiuk/9fb29c046e1dfcc8d5683684d7068efe#file-get_twitter_bookmarks_v3-py
- https://archive.alt-text.org/
- https://observablehq.com/@enjalot/twitter-archive-tweets
- https://github.com/woluxwolu/twint
- https://github.com/jarulsamy/Twitter-Archive
- https://sk22.github.io/twitter-archive-browser/
- https://pypi.org/project/pleroma-bot/
- https://github.com/mshea/Parse-Twitter-Archive
- https://github.com/dangoldin/twitter-archive-analysis
- https://fedi.doom.solutions/tumelune/
