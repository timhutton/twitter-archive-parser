Usage:
1. [Download your Twitter archive](https://twitter.com/settings/download_your_data) (Settings > Your account > Download an archive of your data)
2. Unzip to a folder
3. Open a command-prompt in that folder
4. `python parser.py`

Features:
- Outputs as markdown with embedded images and links
- Replaces t.co URLs with their original versions

TODO:
- Output as Jekyll markdown files
- Output as HTML files
- Embed videos as HTML snippets in the markdown (currently just the thumbnail is shown)
