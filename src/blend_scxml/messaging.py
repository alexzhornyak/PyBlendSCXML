'''
Created on Nov 4, 2010

@author: johan
'''

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


def get_path2(local_path, additional_paths=""):
    # prefix = additional_paths + ":" if additional_paths else ""
    prefix = os.path.abspath(additional_paths) if additional_paths else ""
    search_path = (prefix + os.getcwd() + ":" + os.environ.get("PYSCXMLPATH", "").strip(":")).split(":")
    paths = [os.path.join(folder, local_path) for folder in search_path]
    for path in paths:
        if os.path.isfile(path):
            return (path, search_path)
    return (None, search_path)


def get_document(url, file_dir) -> ContentDocument:
    url_parsed = urlparse(url)
    filepath = unquote(url_parsed.path)

    if url_parsed.scheme not in {'http', 'https'}:
        if url_parsed.scheme and url_parsed.scheme != 'file':
            filepath = os.path.join(url_parsed.scheme + ":", filepath)

        if not os.path.exists(filepath) and file_dir:
            filepath = os.path.join(file_dir, filepath)

        url = Path(filepath).as_uri()

    file_dir, filename = os.path.split(os.path.abspath(filepath))

    return ContentDocument(
        filepath, file_dir, filename,
        urllib.request.urlopen(url).read().decode(encoding="utf-8"))
