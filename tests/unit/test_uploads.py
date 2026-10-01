"""Upload checks run on the zip central directory, before anything is decompressed."""

from __future__ import annotations

from http import HTTPStatus

import pytest

from bob_killer.contracts.runs import UploadLimits
from bob_killer.service.uploads import UploadRejected, inspect_upload
from tests.conftest import bomb, make_zip, workbook_like

SMALL = UploadLimits(
    max_compressed_bytes=64_000,
    max_decompressed_bytes=1_000_000,
    max_members=10,
    max_ratio=50,
)


def test_workbook_container_accepted() -> None:
    inspect_upload(workbook_like(), SMALL)


@pytest.mark.parametrize(
    ("data", "status"),
    [
        (b"not a zip", HTTPStatus.UNSUPPORTED_MEDIA_TYPE),
        (bomb(900_000), HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        (bomb(2_000_000), HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        (make_zip({f"m{i}.xml": b"x" for i in range(11)}), HTTPStatus.REQUEST_ENTITY_TOO_LARGE),
        (
            make_zip({"big.bin": __import__("os").urandom(70_000)}),
            HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
        ),
    ],
    ids=["not-zip", "ratio-bomb", "decompressed-total", "member-count", "compressed-size"],
)
def test_rejections(data: bytes, status: HTTPStatus) -> None:
    with pytest.raises(UploadRejected) as exc:
        inspect_upload(data, SMALL)
    assert exc.value.status == status
