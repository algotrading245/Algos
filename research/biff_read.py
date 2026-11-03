"""Minimal BIFF8 .xls reader (no xlrd): returns {sheet: {(row,col): value}}."""
import struct
import olefile


def rk(v):
    if v & 2:
        x = float(struct.unpack('<i', struct.pack('<I', v))[0] >> 2)
    else:
        x = struct.unpack('<d', struct.pack('<Q', (v & 0xFFFFFFFC) << 32))[0]
    return x / 100 if v & 1 else x


def read(path):
    ole = olefile.OleFileIO(path)
    d = ole.openstream('Workbook').read()
    recs = []
    p = 0
    while p + 4 <= len(d):
        t, n = struct.unpack('<HH', d[p:p + 4])
        recs.append((t, d[p + 4:p + 4 + n]))
        p += 4 + n
    # SST with continues: join chunks, remember boundaries
    sst = []
    i = 0
    sheets = []
    while i < len(recs):
        t, b = recs[i]
        if t == 0xFC:
            chunks = [b]
            j = i + 1
            while j < len(recs) and recs[j][0] == 0x3C:
                chunks.append(recs[j][1])
                j += 1
            sst = parse_sst(chunks)
        i += 1
    out = {}
    cur = None
    names = []
    for t, b in recs:
        if t == 0x85:
            names.append(b)
    si = -1
    for t, b in recs:
        if t == 0x809:  # BOF
            ver, typ = struct.unpack('<HH', b[:4])
            if typ == 0x10:
                si += 1
                cur = si
                out[cur] = {}
        elif cur is None:
            continue
        elif t == 0xFD:
            r, c, x, k = struct.unpack('<HHHI', b[:10])
            out[cur][(r, c)] = sst[k]
        elif t == 0x203:
            r, c, x = struct.unpack('<HHH', b[:6])
            out[cur][(r, c)] = struct.unpack('<d', b[6:14])[0]
        elif t == 0x27E:
            r, c, x, v = struct.unpack('<HHHI', b[:10])
            out[cur][(r, c)] = rk(v)
        elif t == 0xBD:
            r, c0 = struct.unpack('<HH', b[:4])
            n = (len(b) - 6) // 6
            for k in range(n):
                v = struct.unpack('<I', b[4 + 6 * k + 2:4 + 6 * k + 6])[0]
                out[cur][(r, c0 + k)] = rk(v)
    return out


def parse_sst(chunks):
    # flatten with record boundary tracking
    data = b''.join(chunks)
    bounds = []
    s = 0
    for c in chunks:
        s += len(c)
        bounds.append(s)
    total, uniq = struct.unpack('<II', data[:8])
    p = 8
    res = []

    def next_bound(pos):
        for bd in bounds:
            if bd > pos:
                return bd
        return len(data)

    for _ in range(uniq):
        if p >= len(data):
            break
        cch, flags = struct.unpack('<HB', data[p:p + 3])
        p += 3
        rich = flags & 8
        ext = flags & 4
        nr = ne = 0
        if rich:
            nr = struct.unpack('<H', data[p:p + 2])[0]
            p += 2
        if ext:
            ne = struct.unpack('<I', data[p:p + 4])[0]
            p += 4
        wide = flags & 1
        s = ''
        left = cch
        while left > 0:
            bd = next_bound(p)
            w = 2 if wide else 1
            avail = (bd - p) // w
            take = min(avail, left)
            raw = data[p:p + take * w]
            s += raw.decode('utf-16-le' if wide else 'latin-1')
            p += take * w
            left -= take
            if left > 0:
                # continuation: first byte is new flags
                wide = data[p] & 1
                p += 1
        p += 4 * nr + ne
        res.append(s)
    return res


if __name__ == '__main__':
    import sys
    o = read(sys.argv[1])
    for k, v in o.items():
        rows = sorted(set(r for r, c in v))
        print('sheet', k, 'rows', len(rows))
        for r in rows[:8] + rows[-3:]:
            print(r, [v.get((r, c)) for c in range(0, 12)])
