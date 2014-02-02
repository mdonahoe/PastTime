import os

from collections import Counter

types = Counter()

with file('skipped.txt') as skips:
    for line in skips:
        path = line.strip()
        _, ext = os.path.splitext(path)
        types[ext] += 1

print '\n'.join("%s:%s" % (c[1], c[0]) for c in sorted((v,k) for k,v in types.iteritems()))
