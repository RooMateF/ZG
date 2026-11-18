# -*- coding: utf-8 -*-
"""從遠端 zip 用 HTTP Range 只抓指定的檔案，不下載整包。
用法：python remote_unzip.py <url> <輸出資料夾> [list | 檔名1 檔名2 ...]"""
import struct
import sys
import os
import zlib
import urllib.request

url, outdir = sys.argv[1], sys.argv[2]
wanted = sys.argv[3:]


def fetch(start, end):
    req = urllib.request.Request(url, headers={"Range": f"bytes={start}-{end}", "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        assert r.status == 206, r.status
        return r.read()


def total_size():
    req = urllib.request.Request(url, headers={"Range": "bytes=0-0", "User-Agent": "curl/8"})
    with urllib.request.urlopen(req, timeout=120) as r:
        return int(r.headers["Content-Range"].split("/")[1])


size = total_size()
tail = fetch(size - 65536, size - 1)
i = tail.rfind(b"PK\x05\x06")
assert i >= 0, "EOCD not found"
_, _, _, _, n_total, cd_size, cd_off, _ = struct.unpack("<IHHHHIIH", tail[i:i + 22])
cd = fetch(cd_off, cd_off + cd_size - 1)
entries = {}
p = 0
while p < len(cd):
    assert cd[p:p + 4] == b"PK\x01\x02"
    (_, _, _, _, method, _, _, crc, csize, usize, nlen, elen, clen, _, _, _, lho) = struct.unpack("<IHHHHHHIIIHHHHHII", cd[p:p + 46])
    name = cd[p + 46:p + 46 + nlen].decode("utf-8")
    entries[name] = (method, csize, usize, lho, crc)
    p += 46 + nlen + elen + clen

if not wanted or wanted == ["list"]:
    for name, (m, cs, us, _, _) in sorted(entries.items()):
        print(f"{us/1e6:9.1f} MB  {cs/1e6:9.1f} MB  {name}")
    sys.exit(0)

os.makedirs(outdir, exist_ok=True)
for name in wanted:
    method, csize, usize, lho, crc = entries[name]
    lh = fetch(lho, lho + 29)
    nlen, elen = struct.unpack("<HH", lh[26:30])
    start = lho + 30 + nlen + elen
    out = os.path.join(outdir, os.path.basename(name))
    d = zlib.decompressobj(-15) if method == 8 else None
    got = 0
    c = 0
    CH = 8 * 1024 * 1024
    with open(out, "wb") as f:
        while got < csize:
            blk = fetch(start + got, start + min(csize, got + CH) - 1)
            got += len(blk)
            data = d.decompress(blk) if d else blk
            c = zlib.crc32(data, c)
            f.write(data)
            print(f"\r{name}: {got/1e6:.0f}/{csize/1e6:.0f} MB", end="", flush=True)
        if d:
            data = d.flush()
            c = zlib.crc32(data, c)
            f.write(data)
    print()
    assert os.path.getsize(out) == usize, (os.path.getsize(out), usize)
    assert c == crc, "CRC mismatch"
    print("ok", out, usize)
