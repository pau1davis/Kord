import pytest

from kord.tab.events import NoteEvent
from kord.tab.store import PARTS, TabStore


def test_events_survive_a_round_trip(tmp_path):
    store = TabStore(tmp_path)
    events = [NoteEvent(0.0, 0.5, 45, 0.9), NoteEvent(0.5, 1.0, 47, 0.4)]
    store.save("track1", "bass", events)
    assert store.load("track1", "bass") == events


def test_a_part_never_transcribed_loads_as_empty(tmp_path):
    assert TabStore(tmp_path).load("track1", "bass") == []


def test_only_known_parts_can_be_addressed(tmp_path):
    """The part name reaches this from a URL path segment, so a traversal
    attempt must not become a filesystem path. Same defence as stem_store."""
    store = TabStore(tmp_path)
    with pytest.raises(ValueError):
        store.path_for("track1", "../../etc/passwd")


def test_parts_lists_what_has_actually_been_transcribed(tmp_path):
    store = TabStore(tmp_path)
    store.save("track1", "bass", [NoteEvent(0.0, 0.5, 45, 0.9)])
    assert store.parts("track1") == ["bass"]


def test_parts_are_listed_in_a_stable_order(tmp_path):
    store = TabStore(tmp_path)
    for part in ("guitar (right)", "bass", "guitar (left)"):
        store.save("t1", part, [NoteEvent(0.0, 0.5, 45, 0.9)])
    assert store.parts("t1") == ["bass", "guitar (left)", "guitar (right)"]


def test_the_part_names_are_the_instruments_tab_is_for(tmp_path):
    assert set(PARTS) == {"bass", "guitar", "guitar (left)", "guitar (right)"}


def test_a_part_name_with_a_slash_is_refused_even_though_it_looks_harmless(tmp_path):
    with pytest.raises(ValueError):
        TabStore(tmp_path).path_for("t1", "guitar/left")


def test_saving_twice_replaces_rather_than_appends(tmp_path):
    store = TabStore(tmp_path)
    store.save("t1", "bass", [NoteEvent(0.0, 0.5, 45, 0.9)])
    store.save("t1", "bass", [NoteEvent(1.0, 1.5, 47, 0.8)])
    assert [e.midi for e in store.load("t1", "bass")] == [47]


def test_an_empty_transcription_is_stored_and_not_mistaken_for_absent(tmp_path):
    """A part that genuinely has no notes must not read as "never
    transcribed" — otherwise it is retranscribed forever."""
    store = TabStore(tmp_path)
    store.save("t1", "bass", [])
    assert store.parts("t1") == ["bass"]
    assert store.load("t1", "bass") == []
