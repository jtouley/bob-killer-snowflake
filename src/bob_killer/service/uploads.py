"""Upload checks on the zip central directory: nothing is decompressed to decide."""

from __future__ import annotations

import io
import zipfile
from http import HTTPStatus

from bob_killer.contracts.runs import UploadLimits


class UploadRejected(Exception):
    def __init__(self, status: HTTPStatus, detail: str) -> None:
        super().__init__(detail)
        self.status = status
        self.detail = detail


def _too_large(detail: str) -> UploadRejected:
    return UploadRejected(HTTPStatus.REQUEST_ENTITY_TOO_LARGE, detail)


def inspect_upload(data: bytes, limits: UploadLimits) -> None:
    if len(data) > limits.max_compressed_bytes:
        raise _too_large(f"upload is {len(data)} bytes; limit {limits.max_compressed_bytes}")
    try:
        members = zipfile.ZipFile(io.BytesIO(data)).infolist()
    except zipfile.BadZipFile:
        raise UploadRejected(
            HTTPStatus.UNSUPPORTED_MEDIA_TYPE,
            "not an .xlsx/.xlsm zip container (.xls must be converted by the oracle first)",
        ) from None
    if len(members) > limits.max_members:
        raise _too_large(f"{len(members)} zip members; limit {limits.max_members}")
    total = sum(m.file_size for m in members)
    if total > limits.max_decompressed_bytes:
        raise _too_large(f"{total} bytes decompressed; limit {limits.max_decompressed_bytes}")
    for m in members:
        if m.file_size > limits.max_ratio * max(m.compress_size, 1):
            raise _too_large(f"member {m.filename} compression ratio exceeds {limits.max_ratio}")
