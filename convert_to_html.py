#!/usr/bin/env python3
"""
    twitter-archive-parser - Python code to parse a Twitter archive and output in various ways
    Copyright (C) 2022  Tim Hutton

    This program is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    This program is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with this program.  If not, see <https://www.gnu.org/licenses/>.
"""

import glob
import subprocess
import sys
try:
    import markdown
except ImportError:
    print(
        '\nError: This script uses the "markdown" module which is not '
        'installed.\n'
    )
    user_input = input('OK to install using pip? [y/n]')
    if not user_input.lower() in ('y', 'yes'):
        exit()
    subprocess.run(
        [sys.executable, '-m', 'pip', 'install', 'markdown'],
        check=True
    )
    import markdown

HTML = """\
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <link rel="stylesheet"
          href="https://unpkg.com/@picocss/pico@latest/css/pico.min.css">
    <title>Your Twitter archive!</title>
</head>
<body>
    <h1>Your twitter archive</h1>
    <main class="container">
    {}
    </main>
</body>
</html>"""


def convert_to_html():
    md_filenames = sorted(glob.glob('*.md'))

    output = []
    for filename in md_filenames:
        with open(filename, 'r') as f:
            text = f.read()
            output.append(markdown.markdown(text))

    content = ''.join(output)
    result = HTML.format(content)

    with open('TwitterArchive.html', 'w') as f:
        f.write(result)


if __name__ == "__main__":
    convert_to_html()
