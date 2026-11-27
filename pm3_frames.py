"""Proxmark3 NG frame parser, shared by the Saleae HLA (pm3_hla.py) and the
offline decoder (capture-tools/spi_decode.py). Layout per proxmark3
include/pm3_cmd.h (all little-endian):

  Command  (MOSI, Flipper->PM5): magic(4)=PM3a + len:15/ng:1(2) + cmd(2)
                                 + data[len] + crc(2)
  Response (MISO, PM5->Flipper): magic(4)=PM3b + len:15/ng:1(2) + status(1)
                                 + reason(1) + cmd(2) + data[len] + crc(2)
"""
import struct

CMD_MAGIC = 0x61334D50   # "PM3a" command preamble
RESP_MAGIC = 0x62334D50  # "PM3b" response preamble
CMD_MAGIC_LE = b"\x50\x4d\x33\x61"
RESP_MAGIC_LE = b"\x50\x4d\x33\x62"

CMD_NAMES = {
    0x00FF: "ACK",
    0x0100: "DBG_STR",
    0x0101: "DBG_INT",
    0x0107: "VERSION",
    0x0108: "STATUS",
    0x0109: "PING",
    0x010C: "MAIN_CHIP_UNIQUEID",
    0x0112: "CAPABILITIES",
    0x0118: "BREAK_LOOP",
    0x0125: "FLASHMEM_GET_ID",
    0x0148: "FLASHMEM_GET_INFO",
    0x0185: "CEP_STATUS",
    0x0372: "LF_HITAG_READER",
    0x0385: "HF_14A_READER",
    0xFFFF: "UNKNOWN",
}

def cmd_name(cmd):
    return CMD_NAMES.get(cmd, "0x%04X" % cmd)


def parse_preamble(buf, off, is_response):
    """Parse one frame whose preamble starts at buf[off]. Returns (frame, total)
    or (None, 0) if the magic doesn't match / the buffer is too short."""
    hdr = 10 if is_response else 8
    if off + hdr > len(buf):
        return None, 0
    magic = struct.unpack_from("<I", buf, off)[0]
    if magic != (RESP_MAGIC if is_response else CMD_MAGIC):
        return None, 0
    lenng = struct.unpack_from("<H", buf, off + 4)[0]
    length = lenng & 0x7FFF
    ng = (lenng >> 15) & 1
    if is_response:
        status, reason = struct.unpack_from("<bb", buf, off + 6)
        cmd = struct.unpack_from("<H", buf, off + 8)[0]
    else:
        status = reason = None
        cmd = struct.unpack_from("<H", buf, off + 6)[0]
    total = hdr + length + 2  # + 2-byte postamble CRC
    crc = None
    if off + total <= len(buf):
        crc = struct.unpack_from("<H", buf, off + hdr + length)[0]
    return {
        "off": off,
        "cmd": cmd,
        "name": cmd_name(cmd),
        "length": length,
        "ng": ng,
        "status": status,
        "reason": reason,
        "crc": crc,
        "total": total,
        "complete": crc is not None,
        "is_response": is_response,
    }, total


def scan_frames(buf, is_response):
    """Scan a byte buffer for every PM3 frame of the given direction, by
    searching for the preamble magic (robust to inter-frame padding/noise)."""
    magic = RESP_MAGIC_LE if is_response else CMD_MAGIC_LE
    frames = []
    i = 0
    while i < len(buf):
        j = buf.find(magic, i)
        if j < 0:
            break
        frame, total = parse_preamble(buf, j, is_response)
        if frame is None:
            i = j + 1
            continue
        frames.append(frame)
        i = j + (total if total > 4 else 4)
    return frames


# Self-test: build one of each frame and round-trip it through the parser.
if __name__ == "__main__":
    cmd = struct.pack("<IHH", CMD_MAGIC, 0, 0x010C) + struct.pack("<H", 0x3361)
    resp = (struct.pack("<I", RESP_MAGIC) + struct.pack("<H", 4)
            + struct.pack("<bbH", -21, -1, 0x010C) + b"\x02\x4e\x02\x20"
            + struct.pack("<H", 0x3362))
    cf = scan_frames(cmd, False)
    rf = scan_frames(resp, True)
    assert cf and cf[0]["cmd"] == 0x010C and cf[0]["name"] == "MAIN_CHIP_UNIQUEID", cf
    assert rf and rf[0]["cmd"] == 0x010C and rf[0]["status"] == -21 and rf[0]["length"] == 4, rf
    print("pm3_frames self-test OK:", cf[0]["name"], "/ resp status", rf[0]["status"])
