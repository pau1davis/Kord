from kord.audio.stem_store import StemStore


def test_reports_no_stems_before_separation(tmp_path):
    assert StemStore(tmp_path).has_stems("t1") is False
    assert StemStore(tmp_path).path_for("t1", "guitar") is None


def test_finds_a_written_stem(tmp_path):
    store = StemStore(tmp_path)
    d = store.dir_for("t1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "guitar.m4a").write_bytes(b"x" * 10)
    assert store.has_stems("t1") is True
    assert store.path_for("t1", "guitar").name == "guitar.m4a"


def test_unknown_stem_name_is_none_not_an_error(tmp_path):
    store = StemStore(tmp_path)
    store.dir_for("t1").mkdir(parents=True, exist_ok=True)
    assert store.path_for("t1", "trombone") is None


def test_a_stem_name_cannot_escape_the_store(tmp_path):
    """The stem name arrives from a URL path segment."""
    store = StemStore(tmp_path)
    store.dir_for("t1").mkdir(parents=True, exist_ok=True)
    assert store.path_for("t1", "../../etc/passwd") is None


def test_total_bytes_counts_every_stem(tmp_path):
    store = StemStore(tmp_path)
    d = store.dir_for("t1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "guitar.m4a").write_bytes(b"x" * 10)
    (d / "bass.m4a").write_bytes(b"y" * 5)
    assert store.total_bytes() == 15


def test_remove_deletes_the_whole_song(tmp_path):
    store = StemStore(tmp_path)
    d = store.dir_for("t1")
    d.mkdir(parents=True, exist_ok=True)
    (d / "guitar.m4a").write_bytes(b"x")
    store.remove("t1")
    assert store.has_stems("t1") is False
