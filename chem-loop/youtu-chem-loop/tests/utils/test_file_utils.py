import hashlib
from pathlib import Path

from utu.utils import FileUtils


def test_ext_and_url_detection() -> None:
    web_url = "https://example.com/foo/bar.mp3"
    local_path = "/tmp/bar.mp3"
    assert FileUtils.get_file_ext(web_url) == ".mp3"
    assert FileUtils.is_web_url(web_url)

    assert FileUtils.get_file_ext(local_path) == ".mp3"
    assert not FileUtils.is_web_url(local_path)


def test_md5_local_file(tmp_path: Path) -> None:
    fp = tmp_path / "x.txt"
    fp.write_bytes(b"hello")
    got = FileUtils.get_file_md5(str(fp))
    expect = hashlib.md5(b"hello").hexdigest()
    assert got == expect
