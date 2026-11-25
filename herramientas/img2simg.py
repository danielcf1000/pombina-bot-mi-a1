"""Minimal img2simg: raw image -> Android sparse image (RAW + FILL(0) chunks)."""
import struct, sys, os

BLK = 4096
src, dst = sys.argv[1], sys.argv[2]
size = os.path.getsize(src)
assert size % BLK == 0, "size not multiple of 4096"
total_blks = size // BLK
ZERO = bytes(BLK)

chunks = []  # (type, nblocks, offset_blocks)
with open(src, 'rb') as f:
    cur_type, start, n = None, 0, 0
    for i in range(total_blks):
        b = f.read(BLK)
        t = 'fill' if b == ZERO else 'raw'
        if t == cur_type:
            n += 1
        else:
            if cur_type:
                chunks.append((cur_type, n, start))
            cur_type, start, n = t, i, 1
    chunks.append((cur_type, n, start))

with open(src, 'rb') as f, open(dst, 'wb') as o:
    o.write(struct.pack('<IHHHHIIII', 0xED26FF3A, 1, 0, 28, 12, BLK, total_blks, len(chunks), 0))
    for t, n, s in chunks:
        if t == 'raw':
            o.write(struct.pack('<HHII', 0xCAC1, 0, n, 12 + n * BLK))
            f.seek(s * BLK)
            left = n * BLK
            while left:
                d = f.read(min(left, 64 << 20))
                o.write(d)
                left -= len(d)
        else:
            o.write(struct.pack('<HHII', 0xCAC2, 0, n, 16))
            o.write(b'\0\0\0\0')
print('blocks', total_blks, 'chunks', len(chunks), 'out', os.path.getsize(dst))
