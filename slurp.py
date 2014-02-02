"""
slurp.py

Copy all the unique media into the library


usage:
python slurp.py <library path> [<directory path to import>]

# copy all photos from my trip
python slurp.py ~/Pictures ~/Downloads/new_trip_photos

# dedup folders from my old laptop
python slurp.py ~/Pictures ~/Desktop/old_laptop_backup/

# just create cache file and print stats
python slurp.py ~/Pictures

Item => a picture or movie in the library
Library => a simple folder containing items, or other folders with items

When copying from a different source folder,
the path structure relative to that folder is maintained


todo:
[ ] better command-line support (aka, use argparse)
[ ] error-checking logic
[ ] standardize output names?
[ ] rebuild cache file
[x] verify it actually works on real media
[x] info logging
[x] create cache file for faster deduping
[x] load cache file
[x] compare times with and without cache file


"""

import collections
import errno
import hashlib
import itertools
import logging
import os
import shutil
import stat
import sys
import time

logger = logging.getLogger('foo')
logger.setLevel(logging.INFO)
logger.addHandler(logging.StreamHandler())


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
ITEMTYPES = VIDEO | IMAGE


class Item(object):
    def __init__(self, path, root=''):
        self.path = path
        self._root = root
        self._size = None
        self._quickhash = None
        self._fullhash = None

    @classmethod
    def from_cacheline(cls, cacheline):
        stats, path = cacheline.strip().split(':', 1)
        item = Item(path)

        # use cache instead of reading stats later on filedate
        size, quick, full = stats.split('-')
        item._size = int(size)
        item._quickhash = quick.decode('hex')
        item._fullhash = full.decode('hex')

        return item

    @property
    def filename(self):
        return os.path.basename(self.path)

    def equals(self, other):
        if self.size != other.size:
            return False

        if self.quickhash != other.quickhash:
            return False

        return self.fullhash == other.fullhash

    def copy_to(self, new_path):
        logger.info('copying %s -> %s', self.path, new_path)
        make_sure_path_exists(os.path.dirname(new_path))
        shutil.copy(self.path, new_path)
        self.path = new_path

    def rename_as(self, new_path):
        logger.info('renaming %s -> %s', self.path, new_path)
        make_sure_path_exists(os.path.dirname(new_path))
        os.rename(self.path, new_path)
        self.path = new_path

    @property
    def size(self):
        if self._size is None:
            self._size = os.stat(self.path)[stat.ST_SIZE]
        return self._size

    @property
    def quickhash(self):
        if self._quickhash is None:
            logger.info('quick hash needed for %s', self.path)
            with file(self.path) as f:
                self._quickhash = hashlib.md5(f.read(1024)).digest()
        return self._quickhash

    @property
    def fullhash(self):
        if self._fullhash is None:
            logger.info('full hash needed for %s', self.path)
            with file(self.path) as f:
                self._fullhash = compute_file_hash(f)
        return self._fullhash

    def __repr__(self):
        return 'Item("%s")' % self.path

    def __str__(self):
        return repr(self)

    def cacheline(self):
        key = '-'.join((str(self.size),
                        self.quickhash.encode('hex'),
                        self.fullhash.encode('hex')))
        return ':'.join((key, self.path))

    def summary(self):
        return """
{path}
size: {size}
quick: {quick}
full: {full}
""".format(path=self.path, size=self.size, quick=self._quickhash, full=self._fullhash)


class Library(object):
    def __init__(self, directory=None):
        self.directory = directory
        self._sizeMap = collections.defaultdict(list)
        self.dupes = []
        self.skips = []

        # check for cache file

        if not os.path.exists(self.cachePath):
            logger.warn('no cache file found at "%s"!', cachePath)
            # re need to build a cache of the library
            self._scan(directory)
            return

        logger.info('loading from cache, may create duplicates')
        # self.parse_cache_file(path)
        with file(self.cachePath) as cache:
            for line in cache:
                if not line:
                    logger.warn('empty line')
                    continue
                item = Item.from_cacheline(line)
                self._add_item(item)


    @property
    def cachePath(self):
        return os.path.join(self.directory, 'cache.txt')

    @property
    def items(self):
        return itertools.chain.from_iterable(self._sizeMap.itervalues())

    @property
    def itemcount(self):
        return sum(1 for _ in self.items)

    def _add_path(self, path, root):
        _, ext = os.path.splitext(path)
        if ext.lower()[1:] not in ITEMTYPES:
            self.skips.append(path)
            return
        self._add_item(Item(path, root))

    def _add_item(self, new):
        logger.info('adding item %s', new)
        existing = self._sizeMap[new.size]
        for item in existing:
            if not item.equals(new):
                continue
            logger.warn('duplicate found ("%s" same as "%s")',
                        new.path, item.path)
            self.dupes.append(new)
            self._merge_items(item, new)
            return
        existing.append(new)

    def _merge_items(self, item, dupe):
        # item is already in the library
        # dupe has the same data, but might have newer filename or stats
        if item.filename == dupe.filename:
            # v1, give up
            logger.info('item == dupe')
            return

        if 'IMG' not in item.filename:
            # original name is fine, abort
            logger.info('no IMG in item')
            return

        if 'IMG' in dupe.filename:
            # new name sucks too, abort
            logger.info('IMG in new')
            return

        # compute new path
        rel_path = os.path.relpath(dupe.path, dupe._root)  # ICK, TODO
        new_path = os.path.join(self.directory, rel_path)

        # alter the ORIGINAL item, leave the dupe
        item.rename_as(new_path)

    def _scan(self, directory):
        skip_hidden = lambda d: d[0] != '.'
        for cur, dirs, files in os.walk(directory):
            logger.info('walking: "%s"', cur)
            # we modify in-place to avoid future traveral
            dirs[:] = filter(skip_hidden, dirs)

            for f in files:
                path = os.path.join(cur, f)
                self._add_path(path, directory)


    def save_cache_file(self, path=None):
        "create a sorted cache of items <size-quickhash-fullhash:path>"
        if path is None:
            path = self.cachePath
        lines = [item.cacheline() for item in self.items]
        lines.sort()
        with open(path, 'w') as cache:
            cache.write('\n'.join(lines))

    def copy(self, directory):
        "import media from path into the library, moving the items too"
        self._scan(directory)
        # now figure out the new ones, ugh, and copy them
        for item in self.items:
            if os.path.commonprefix([directory, item.path]) != directory:
                # already in library, not new
                logger.debug('not copying "%s" because not from "%s"',
                            item.path, directory)
                continue
            if os.path.commonprefix([self.directory, item.path]) == self.directory:
                # weird.. new file already in the right spot
                logger.warn('already copied "%s"', item.path)
                continue

            # compute new path
            rel_path = os.path.relpath(item.path, directory)
            new_path = os.path.join(self.directory, rel_path)

            # copy the file, update the item
            item.copy_to(new_path)
            # dangerous!

    def print_stats(self):
        print 'sizes:', len(self._sizeMap)
        print ''
        print 'dupes:', len(self.dupes)
        print '\n'.join(item.path for item in L.dupes)
        print ''
        print 'skips:', len(self.skips)
        # breakdown of skipped file-extensions?


class StopWatch(object):
    def __init__(self):
        self._t = time.time()

    def lap(self):
        old, self._t = self._t, time.time()
        return self._t - old


logger.info('starting to slurp...')
stopwatch = StopWatch()

L = Library(sys.argv[1])
logger.info('scan time =  %s', stopwatch.lap())

if len(sys.argv) > 2:
    L.copy(sys.argv[2])
    logger.info('copy time =  %s', stopwatch.lap())

L.print_stats()
logger.info('stats time =  %s', stopwatch.lap())

L.save_cache_file()
logger.info('save time =  %s', stopwatch.lap())
