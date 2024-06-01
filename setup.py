
from setuptools import setup

version = "0.8.3"
filename = "0.8.3-20120108"

setup(
    name="py_blend_scxml",
    version=filename,
    description="A pure Python SCXML parser/interpreter for Blender",
    long_description="Use PyBlendSCXML to parse and execute an SCXML document in Blender. PySCXML aims for full compliance with the W3C standard.",
    author="Johan Roxendal, Alex Zhornyak, Patrick K. O'Brien and Louie contributors",
    author_email="johan@roxendal.com alexander.zhornyak@gmail.com",
    url="https://github.com/alexzhornyak/PyBlendSCXML",
    download_url="https://github.com/alexzhornyak/PyBlendSCXML",
    packages=["blend_scxml"],
    package_dir={"": "src"},
    license="LGPLv3",
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Environment :: Web Environment',
        'Intended Audience :: Developers',
        'License :: OSI Approved :: GNU Library or Lesser General Public License (LGPL)',
        'Operating System :: OS Independent',
        'Programming Language :: Python',
        'Topic :: Communications :: Telephony',
        'Topic :: Internet :: WWW/HTTP',
        'Topic :: Internet :: WWW/HTTP :: WSGI',
        'Topic :: Software Development :: Interpreters',
        'Topic :: Software Development :: Libraries :: Python Modules',
        'Topic :: Text Processing :: Markup :: XML'
    ],
    install_requires=["bpy"]
)
