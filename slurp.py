"""
slurp.py

Copy all the unique files in a source directory
to a destination directory

usage:
python slurp.py ~/Pictures /Volumes/External/Pictures

todo:
[ ] better command-line support
[ ] error-checking logic
[ ] verify it actually works on real media
[ ] standardize output names?

"""

from collections import defaultdict
import errno
import hashlib
import logging
import os
import shutil
import stat
import sys


def compute_file_hash(f):
    h = hashlib.sha1()
    while 1:
        x = f.read(4096)
        if not len(x):
            return h.digest()
        h.update(x)


def make_sure_path_exists(path):
    try:
        os.makedirs(path)
    except OSError as exception:
        if exception.errno != errno.EEXIST:
            raise


VIDEO = {'avi', 'mov', 'mpeg', 'mpg', 'mp4'}
IMAGE = {'gif', 'jpeg', 'jpg', 'png', 'tif', 'tiff'}
MEDIA = VIDEO | IMAGE


class FileInfo(object):
    def __init__(self, path):
        self.path = path
        self._size = None
        self._quickhash = None
        self._fullhash = None

    def equals(self, other):
        if self.size != other.size:
            return False
        if self.quickhash != other.quickhash:
            return False
        return self.fullhash == other.fullhash

    def copy_to(self, new_path):
        logging.info('copying %s -> %s', self.path, new_path)
        make_sure_path_exists(os.path.dirname(new_path))
        shutil.copy(self.path, new_path)
        self.path = new_path

    @property
    def size(self):
        if self._size is None:
            self._size = os.stat(self.path)[stat.ST_SIZE]
        return self._size

    @property
    def quickhash(self):
        if self._quickhash is None:
            with file(self.path) as f:
                self._quickhash = hashlib.md5(f.read(1024)).digest()
        return self._quickhash

    @property
    def fullhash(self):
        if self._fullhash is None:
            with file(self.path) as f:
                self._fullhash = compute_file_hash(f)
        return self._fullhash

    def __repr__(self):
        return 'FileInfo("%s")' % self.path

    def summary(self):
        return """
{path}
size: {size}
quick: {quick}
full: {full}
""".format(path=self.path, size=self.size, quick=self._quickhash, full=self._fullhash)


class Library(object):
    def __init__(self, path=None):
        self.path = path
        self._sizeMap = defaultdict(list)
        self.dupes = []
        self.skips = []

        # remember the media we already have
        self.scan(self.path)

    @property
    def files(self):
        files = []
        for fs in self._sizeMap.values():
            files.extend(fs)
        return files

    def add(self, paths):
        for path in paths:
            _, ext = os.path.splitext(path)
            if ext.lower()[1:] not in MEDIA:
                self.skips.append(path)
                continue
            info = FileInfo(path)
            existing = self._sizeMap[info.size]
            if any(info.equals(f) for f in existing):
                self.dupes.append(info)
                continue
            existing.append(info)

    def scan(self, directory):
        skip_hidden = lambda d: d[0] != '.'
        for cur, dirs, files in os.walk(directory):
            dirs[:] = filter(skip_hidden, dirs)
            self.add(os.path.join(cur, f) for f in files)

    def copy(self, path):
        self.scan(path)
        for info in self.files:
            if os.path.commonprefix([path, info.path]) != path:
                # not a file we need to copy
                logging.warn('not copying "%s"', info.path)
                continue
            if os.path.commonprefix([self.path, info.path]) == self.path:
                # already in the right spot
                logging.warn('already copied "%s"', info.path)
                continue

            # compute new path
            rel_path = os.path.relpath(info.path, path)
            new_path = os.path.join(self.path, rel_path)

            # copy the file, update the info
            info.copy_to(new_path)
            # dangerous!


L = Library(sys.argv[2])
L.copy(sys.argv[1])

print '\n'.join(f.summary() for f in L.files)
print L.dupes
