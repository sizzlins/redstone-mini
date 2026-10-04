"""Minimal Valve/Minecraft RCON client (stdlib only).

Protocol: int32LE length + int32LE id + int32LE type + utf-8 body + 0x00.
Auth type 3 (fail -> response id -1), exec type 2, response type 0.
Timeouts on everything (rule 7: never hang on a dead socket).
"""
import socket
import struct
import time

_AUTH, _EXEC = 3, 2


class RconError(RuntimeError):
    pass


class Rcon:
    def __init__(self, host, port, password, timeout=10):
        self.timeout = timeout
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        self._id = 0
        self._auth(password)

    def _packet(self, rid, typ, body):
        # ponytail: Valve framing ends in TWO nulls (body terminator +
        # empty string). One null parses on lenient readers but real
        # servers frame strictly -- the mock caught this (length 9
        # rejected), which is exactly what the selftest is for.
        data = body.encode('utf-8') + b'\x00\x00'
        return struct.pack('<iii', 4 + 4 + len(data), rid, typ) + data

    def _read_exact(self, n):
        buf = b''
        while len(buf) < n:
            chunk = self.sock.recv(n - len(buf))
            if not chunk:
                raise RconError('socket closed mid-packet')
            buf += chunk
        return buf

    def _read_packet(self):
        (length,) = struct.unpack('<i', self._read_exact(4))
        if length < 10 or length > 1 << 23:
            raise RconError('bad packet length %d' % length)
        raw = self._read_exact(length)
        rid, typ = struct.unpack('<ii', raw[:8])
        return rid, typ, raw[8:-2].decode('utf-8', 'replace')

    def _roundtrip(self, typ, body):
        self._id += 1
        rid = self._id
        self.sock.sendall(self._packet(rid, typ, body))
        # collect until 150ms quiet (multi-packet responses possible).
        out, deadline = [], time.monotonic() + self.timeout
        self.sock.settimeout(0.15)
        try:
            while True:
                try:
                    r, t, b = self._read_packet()
                except socket.timeout:
                    break
                if r == rid:
                    out.append((t, b))
                if time.monotonic() > deadline:
                    break
        finally:
            self.sock.settimeout(self.timeout)
        if not out:
            raise RconError('no response (id %d)' % rid)
        return out

    def _auth(self, password):
        try:
            got = self._roundtrip(_AUTH, password)
        except RconError as e:
            raise RconError('auth failed (no reply): %s' % e)
        if not got:
            raise RconError('auth rejected (bad password?)')

    def exec(self, command):
        """Run a command, return concatenated response bodies."""
        return '\n'.join(b for _, b in self._roundtrip(_EXEC, command))

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass
