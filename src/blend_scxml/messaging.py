'''
Created on Nov 4, 2010

@author: johan
'''

# NOTE: modified by Alex Zhornyak, alexander.zhornyak@gmail.com

import os
import urllib
from urllib.parse import unquote, urlparse
from pathlib import Path

from dataclasses import dataclass


@dataclass
class ContentDocument:
    filepath: str = ""
    filedir: str = ""
    filename: str = ""
    content: str = ""


def get_document(url, file_dir) -> ContentDocument:
    url_parsed = urlparse(url)
    filepath = unquote(url_parsed.path)

    b_is_os = False

    if url_parsed.scheme:
        if url_parsed.scheme not in {'http', 'https'}:
            if url_parsed.scheme != 'file':
                filepath = os.path.join(url_parsed.scheme + ":", filepath)
            b_is_os = True
    else:
        # NOTE: if only netloc contains info
        if url_parsed.netloc:
            if filepath:
                filepath = os.path.join(url_parsed.netloc, filepath)
            else:
                filepath = url_parsed.netloc
        b_is_os = True

    if b_is_os:
        if not os.path.exists(filepath) and file_dir:
            filepath = os.path.join(file_dir, filepath)

        url = Path(os.path.abspath(filepath)).as_uri()

    file_dir, filename = os.path.split(os.path.abspath(filepath))

    return ContentDocument(
        filepath, file_dir, filename,
        urllib.request.urlopen(url).read().decode(encoding="utf-8"))
