"""Self-test for scratch/rcon.py against a mock Valve-RCON server.

Runs a fake server (auth + exec + multi-packet + drop), exercises the
client's framing, auth accept/reject, command roundtrip and timeout
paths. The one runnable check on the non-trivial new logic: packet
handling must be exact or every live run corrupts silently.
"""
import socket
import struct
import sys
import threading
import time

sys.path.insert(0, 'D:\\redstone-mini\\scratch')
from rcon import Rcon, RconError


def rd_exact(c, n):
    b = b''
    while len(b) < n:
        ch = c.recv(n - len(b))
        if not ch:
            raise ConnectionError('closed')
        b += ch
    return b


def serve(port, password, log):
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(('127.0.0.1', port))
    srv.listen(5)
    srv.settimeout(20)
    try:
        while True:
            try:
                c, _ = srv.accept()
            except socket.timeout:
                return
            c.settimeout(10)
            try:
                while True:
                    (ln,) = struct.unpack('<i', rd_exact(c, 4))
                    raw = rd_exact(c, ln)
                    rid, typ = struct.unpack('<ii', raw[:8])
                    body = raw[8:-2].decode()
                    log.append((typ, body))
                    if typ == 3:  # auth
                        if body == password:
                            out = [(rid, 2, ''), (0, 2, '')]
                        else:
                            out = [(-1, 2, '')]
                    elif typ == 2:  # exec
                        if body == 'twopart':
                            out = [(rid, 0, 'part1-'), (rid, 0, 'part2')]
                        elif body == 'silent':
                            out = []  # no reply: client must time out loud
                        else:
                            out = [(rid, 0, 'ok:' + body)]
                    else:
                        out = []
                    for r, t, bb in out:
                        d = bb.encode() + b'\x00\x00'
                        c.sendall(struct.pack('<iii', 8 + len(d), r, t)
                                  + d)
            except (ConnectionError, socket.timeout, OSError):
                try:
                    c.close()
                except Exception:
                    pass
    finally:
        srv.close()


def main():
    port = 29575
    log = []
    th = threading.Thread(target=serve, args=(port, 's3cret', log),
                          daemon=True)
    th.start()
    time.sleep(0.3)
    # 1. auth ok + exec roundtrip
    rc = Rcon('127.0.0.1', port, 's3cret', timeout=5)
    assert rc.exec('hello') == 'ok:hello', rc.exec('hello')
    # 2. multi-packet concat
    assert rc.exec('twopart') == 'part1-\npart2', rc.exec('twopart')
    rc.close()
    # 3. auth reject fails loud
    try:
        Rcon('127.0.0.1', port, 'wrong', timeout=5)
    except RconError:
        pass
    else:
        raise AssertionError('bad password accepted!')
    # 4. silent server -> loud timeout (never hangs: bounded by timeout)
    rc2 = Rcon('127.0.0.1', port, 's3cret', timeout=5)
    t0 = time.monotonic()
    try:
        rc2.exec('silent')
    except RconError:
        pass
    else:
        raise AssertionError('silent server did not time out!')
    dt = time.monotonic() - t0
    assert dt < 8, dt
    rc2.close()
    print('rcon selftest ok: auth/roundtrip/multipart/reject/timeout '
          '(%.1fs server-silence bounded)' % dt)


if __name__ == '__main__':
    main()
