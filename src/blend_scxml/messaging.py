'''
Created on Nov 4, 2010

@author: johan
'''

import os


def get_path(local_path, additional_paths=""):
    prefix = additional_paths + ":" if additional_paths else ""
    search_path = (prefix + os.getcwd() + ":" + os.environ.get("PYSCXMLPATH", "").strip(":")).split(":")
    paths = [os.path.join(folder, local_path) for folder in search_path]
    for path in paths:
        if os.path.isfile(path):
            return (path, search_path)
    return (None, search_path)
