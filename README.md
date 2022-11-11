## How do I use it?
1. [Download your Twitter archive](https://twitter.com/settings/download_your_data) (Settings > Your account > Download an archive of your data).
2. Unzip to a folder.
3. Copy [parser.py](https://raw.githubusercontent.com/timhutton/twitter-archive-parser/main/parser.py) into the same folder. (e.g. Right-click, Save Link As...)
4. Run the script with [Python3](https://realpython.com/installing-python/): `python parser.py` from a command prompt.

If you are having problems, the discussion here might be useful: https://mathstodon.xyz/@timhutton/109316834651128246

## What does it do?
The Twitter archive gives you a bunch of data and an HTML file (`Your archive.html`). Open that file to take a look! It lets you view your tweets in a nice interface. It has some flaws but maybe that's all you need. If so then stop here, you don't need our script.

Flaws of the Twitter archive:
- It shows you tweets you posted with images, but if you click on one of the images to expand it then it takes you to the Twitter website. If you are offline or have deleted your account or twitter.com is down then that won't work.
- The tweets are stored in a complex JSON structure so you can't just copy them into your blog for example.
- The images they give you are smaller than the ones you uploaded. I don't know why they would do this to us.

Our script does the following:
- Converts the tweets to [markdown](https://en.wikipedia.org/wiki/Markdown) with embedded images and links. Currently it outputs a single monolithic markdown file but that can change.
- Replaces t.co URLs with their original versions
- Copies used images to an output folder, to allow them to be moved to a new home

## TODO:
- Output as separate Jekyll markdown files.
- Output as HTML files?
- Embed videos as HTML snippets in the markdown (currently just the thumbnail is shown).
- Provide a way to download the full-size images. ([Issue #16](https://github.com/timhutton/twitter-archive-parser/issues/16))

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
