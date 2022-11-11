Usage:
1. [Download your Twitter archive](https://twitter.com/settings/download_your_data) (Settings > Your account > Download an archive of your data)
2. Unzip to a folder
3. Copy [parser.py](https://raw.githubusercontent.com/timhutton/twitter-archive-parser/main/parser.py) into the same folder. (e.g. Right-click, Save Link As...)
4. Run the script with Python3. e.g. `python parser.py`

Features:
- Outputs as markdown with embedded images and links
- Replaces t.co URLs with their original versions
- Copies used images to an output folder, to allow them to be moved to a new home

TODO:
- Output as Jekyll markdown files
- Output as HTML files
- Embed videos as HTML snippets in the markdown (currently just the thumbnail is shown)
