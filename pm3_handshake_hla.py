"""Saleae High-Level Analyzer: the PM5 CEP UART handshake (Flipper -> PM5).

Attach to an Async Serial analyzer on SIG3 (A8/B8), 2400 baud 8N1, LSB
first. Before switching to SPI, the Flipper sends STX (0x02) followed by
"iamf0rupm5"; the PM5 only listens on this line.
"""
from saleae.analyzers import HighLevelAnalyzer, AnalyzerFrame

STX = 0x02
MAGIC = b"iamf0rupm5"


class HandshakeHla(HighLevelAnalyzer):
    result_types = {
        "handshake": {"format": "HANDSHAKE {{data.text}}"},
        "bad": {"format": "BAD HANDSHAKE {{data.text}} ({{data.reason}})"},
        "byte": {"format": "{{data.text}}"},
    }

    def __init__(self):
        self._buf = None   # bytes after STX, None when not in a handshake
        self._start = None
        self._end = None

    def decode(self, frame):
        if frame.type != "data":
            return None
        byte = frame.data["data"][0]
        error = frame.data.get("error")
        out = []

        if byte == STX and not error:
            # A new STX mid-handshake means the previous attempt was cut short.
            if self._buf is not None:
                out.append(self._bad("restarted"))
            self._buf = bytearray()
            self._start = frame.start_time
            self._end = frame.end_time
            return out or None

        if self._buf is None:
            text = "0x%02X" % byte + (" " + error if error else "")
            return AnalyzerFrame("byte", frame.start_time, frame.end_time, {"text": text})

        self._buf.append(byte)
        self._end = frame.end_time
        if error:
            out.append(self._bad(error.lower() + " error"))
        elif self._buf != MAGIC[:len(self._buf)]:
            out.append(self._bad("mismatch"))
        elif len(self._buf) == len(MAGIC):
            out.append(AnalyzerFrame("handshake", self._start, self._end, {"text": MAGIC.decode()}))
            self._buf = None
        return out or None

    def _bad(self, reason):
        text = self._buf.decode("ascii", "replace")
        frame = AnalyzerFrame("bad", self._start, self._end, {"text": repr(text), "reason": reason})
        self._buf = None
        return frame
