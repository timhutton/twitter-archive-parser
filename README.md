### Features:
- Outputs as markdown with embedded images and links
- Replaces t.co URLs with their original versions
- Downloads full sized versions of images
- Copies used images to an output folder, to allow them to be moved to a new home

### TODO:
- Output as Jekyll markdown files
- Output as HTML files
- Embed videos as HTML snippets in the markdown (currently just the thumbnail is shown)

### Pre-requisites:

- [python 3](https://www.python.org)
  Note that macOS does _not_ ship with python 3 installed.
- the `requests` package
  install with `pip install requests`

### Usage:

1. [Download your Twitter archive](https://twitter.com/settings/download_your_data) (Settings > Your account > Download an archive of your data)
2. Unzip to a folder
3. Open a command-prompt in that folder
4. `python path/to/parser.py`
  note: depending on how python was installed on your system this may be `python3 path/to/parser.py`
