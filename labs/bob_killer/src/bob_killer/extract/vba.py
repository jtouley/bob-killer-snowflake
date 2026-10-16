"""VBA inventory (SPEC decision 6): module names and kinds, read without executing anything.

``xl/vbaProject.bin`` is an OLE compound file (MS-CFB). Its ``PROJECT`` stream is plain text
that lists every module (MS-OVBA 2.3.1). That is enough for the inventory and needs only the
standard library. Module *source* is compressed inside the ``VBA`` storage and is left to
``oletools.olevba``, which is not a dependency: each module is reported as ``needs_oletools``.
"""

from __future__ import annotations

import struct
import zipfile

from bob_killer.contracts.raw import RawUnsupported, RawVbaModule, VbaModuleKind, VbaSourceStatus

VBA_PART = "xl/vbaProject.bin"
VBA_PROJECT = "vba_project"
VBA_SOURCE = "vba_source"

_SIGNATURE = bytes.fromhex("d0cf11e0a1b11ae1")
_HEADER_DIFAT = 109
_DIR_ENTRY = 128
_NO_STREAM = 0xFFFFFFFF
_END_OF_CHAIN = 0xFFFFFFFE
_STREAM, _ROOT = 2, 5
_KINDS = {
    "Module": VbaModuleKind.STANDARD,
    "Document": VbaModuleKind.DOCUMENT,
    "Class": VbaModuleKind.CLASS,
    "BaseClass": VbaModuleKind.DESIGNER,
}


class VbaUnreadable(Exception):
    pass


class _CompoundFile:
    """Just enough of MS-CFB to read one named stream from the root storage."""

    def __init__(self, data: bytes) -> None:
        if len(data) < 512 or data[:8] != _SIGNATURE:
            raise VbaUnreadable("not an OLE compound file")
        self.data = data
        self.sector = 1 << struct.unpack_from("<H", data, 0x1E)[0]
        self.mini_sector = 1 << struct.unpack_from("<H", data, 0x20)[0]
        (first_dir,) = struct.unpack_from("<I", data, 0x30)
        self.cutoff, first_minifat = struct.unpack_from("<II", data, 0x38)
        first_difat, n_difat = struct.unpack_from("<II", data, 0x44)
        self.fat = self._fat(first_difat, n_difat)
        self.entries = self._entries(self._chain_bytes(first_dir))
        root = self.entries[0]
        self.mini_stream = self._chain_bytes(root[2])[: root[3]]
        self.minifat = (
            _u32s(self._chain_bytes(first_minifat)) if first_minifat < _END_OF_CHAIN else []
        )

    def _sector_bytes(self, n: int) -> bytes:
        start = (n + 1) * self.sector
        if start + self.sector > len(self.data):
            raise VbaUnreadable(f"sector {n} is past the end of the file")
        return self.data[start : start + self.sector]

    def _fat(self, first_difat: int, n_difat: int) -> list[int]:
        sectors = list(struct.unpack_from(f"<{_HEADER_DIFAT}I", self.data, 0x4C))
        nxt = first_difat
        for _ in range(n_difat):
            words = _u32s(self._sector_bytes(nxt))
            sectors.extend(words[:-1])
            nxt = words[-1]
        fat: list[int] = []
        for s in sectors:
            if s < _END_OF_CHAIN:
                fat.extend(_u32s(self._sector_bytes(s)))
        return fat

    def _walk(self, start: int, table: list[int]) -> list[int]:
        chain: list[int] = []
        n = start
        while n < _END_OF_CHAIN:
            if n >= len(table) or len(chain) > len(table):
                raise VbaUnreadable("broken sector chain")
            chain.append(n)
            n = table[n]
        return chain

    def _chain_bytes(self, start: int) -> bytes:
        return b"".join(self._sector_bytes(n) for n in self._walk(start, self.fat))

    @staticmethod
    def _entries(raw: bytes) -> list[tuple[str, int, int, int, int, int, int]]:
        """(name, type, start sector, size, left, right, child) per directory entry."""
        out = []
        for off in range(0, len(raw) - _DIR_ENTRY + 1, _DIR_ENTRY):
            (name_len,) = struct.unpack_from("<H", raw, off + 64)
            name = raw[off : off + max(name_len - 2, 0)].decode("utf-16-le", "replace")
            kind = raw[off + 66]
            left, right, child = struct.unpack_from("<III", raw, off + 68)
            start, size = struct.unpack_from("<IQ", raw, off + 116)
            out.append((name, kind, start, size & 0xFFFFFFFF, left, right, child))
        if not out or out[0][1] != _ROOT:
            raise VbaUnreadable("no root storage")
        return out

    def _children(self, storage: int) -> list[int]:
        found, stack, seen = [], [self.entries[storage][6]], set()
        while stack:
            i = stack.pop()
            if i == _NO_STREAM or i in seen or i >= len(self.entries):
                continue
            seen.add(i)
            found.append(i)
            stack.extend((self.entries[i][4], self.entries[i][5]))
        return found

    def root_stream(self, name: str) -> bytes:
        for i in self._children(0):
            entry_name, kind, start, size, *_ = self.entries[i]
            if entry_name == name and kind == _STREAM:
                if size < self.cutoff:
                    chain = self._walk(start, self.minifat)
                    m = self.mini_sector
                    return b"".join(self.mini_stream[n * m : (n + 1) * m] for n in chain)[:size]
                return self._chain_bytes(start)[:size]
        raise VbaUnreadable(f"no {name} stream")


def _u32s(raw: bytes) -> list[int]:
    return list(struct.unpack(f"<{len(raw) // 4}I", raw[: len(raw) // 4 * 4]))


def read_modules(data: bytes) -> list[tuple[str, VbaModuleKind]]:
    """Module names and kinds in PROJECT-stream order."""
    text = _CompoundFile(data).root_stream("PROJECT").decode("cp1252", "replace")
    modules = []
    for line in text.splitlines():
        if line.startswith("["):
            break  # [Host Extender Info] and later sections list no modules
        key, sep, value = line.partition("=")
        if sep and key in _KINDS:
            modules.append((value.split("/", 1)[0], _KINDS[key]))
    return modules


def inventory(zf: zipfile.ZipFile) -> tuple[tuple[RawVbaModule, ...], tuple[RawUnsupported, ...]]:
    if VBA_PART not in zf.namelist():
        return (), ()
    try:
        modules = read_modules(zf.read(VBA_PART))
    except VbaUnreadable as exc:
        reason = f"VBA project could not be read: {exc}"
        return (), (RawUnsupported(kind=VBA_PROJECT, origin=VBA_PART, reason=reason),)
    rows = tuple(
        RawVbaModule(name=name, kind=kind, source_status=VbaSourceStatus.NEEDS_OLETOOLS)
        for name, kind in modules
    )
    reason = "VBA source extraction needs oletools, which is not a dependency; inventoried only"
    return rows, tuple(RawUnsupported(kind=VBA_SOURCE, origin=m.name, reason=reason) for m in rows)
