import os
import re
from datetime import datetime

base_dir = os.path.dirname(__file__)

version_file = os.path.join(base_dir, "../src/blend_scxml/version.py")
print('Start reading:', version_file, '...')

fin = open(version_file, 'rt', encoding='utf-8')
data = fin.readlines()
fin.close()

s_version = ""

fout = open(version_file, 'wt', encoding='utf-8')
for line in data:
    res = re.match(r'^VERSION = "((\d+).\s*(\d+).\s*(\d+)(.\s*(\d+))*)"\s*$', line)
    if res:
        was_version = line.strip()
        s_version = re.sub(r'(\d+)(?!.+\d)', lambda x: str(int(x.group(0)) + 1), res.group(1))
        line = f'VERSION = "{s_version}"\n'
        print(was_version, '->', line)
    fout.write(line)
fout.close()

setup_file = os.path.join(base_dir, "../setup.py")
print('Start reading:', setup_file, '...')

fin = open(setup_file, 'rt', encoding='utf-8')
data = fin.readlines()
fin.close()

fout = open(setup_file, 'wt', encoding='utf-8')
for line in data:
    if line.startswith("version ="):
        line = f'version = "{s_version}"\n'
    elif line.startswith("filename ="):
        s_date = datetime.today().strftime("%Y%m%d")
        line = f'filename = "{s_version}-{s_date}"\n'
        print("Setting:", line)
    fout.write(line)
fout.close()
