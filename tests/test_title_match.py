"""Reading the candidate's title, not just its length.

Duration matching alone lets live takes through whenever the live tempo happens
to land within 2% of the studio cut, and it cannot tell a music video from a
plain audio upload at all. These cases are taken from real `ytsearch` results
for songs the app has actually analysed.
"""
from kord.audio.title_match import classify_title

ARTIST, TITLE = "Nirvana", "Come As You Are"


def kind(candidate_title, artist=ARTIST, title=TITLE):
    return classify_title(candidate_title, artist, title)


def test_live_recordings_are_rejected():
    assert kind("Nirvana - Come As You Are (Live On MTV Unplugged, 1993)") == "reject"
    assert kind("Nirvana - Come As You Are (Live And Loud, Seattle / 1993)") == "reject"
    assert kind("Nirvana - Come As You Are - Live at Teatro Castello, 1991") == "reject"


def test_a_song_whose_own_title_contains_live_is_not_mistaken_for_a_concert():
    """The marker only counts in the text the uploader added around the song."""
    assert classify_title(
        "Wings - Live And Let Die (Official Music Video)",
        "Wings", "Live and Let Die") == "video"
    assert classify_title(
        "Oasis - Live Forever", "Oasis", "Live Forever") == "ok"
    # ...but a concert recording of that same song still is one.
    assert classify_title(
        "Oasis - Live Forever (Live at Knebworth 1996)",
        "Oasis", "Live Forever") == "reject"


def test_alive_is_not_live():
    assert classify_title("Pearl Jam - Alive", "Pearl Jam", "Alive") == "ok"


def test_other_peoples_versions_are_rejected():
    assert kind("Come As You Are - Nirvana (Acoustic Cover)") == "reject"
    assert kind("Come As You Are Karaoke Version") == "reject"
    assert kind("How to play Come As You Are - Guitar Lesson") == "reject"
    assert kind("Come As You Are (Nirvana) - Drum Cover") == "reject"


def test_doctored_uploads_are_rejected():
    assert kind("Nirvana - Come As You Are (sped up)") == "reject"
    assert kind("Nirvana - Come As You Are [slowed + reverb]") == "reject"
    assert kind("Nirvana - Come As You Are (8D AUDIO)") == "reject"
    assert kind("Nirvana - Come As You Are (Bass Boosted)") == "reject"
    assert kind("Marvin Gaye...Mercy Mercy Me...Extended Mix...",
                "Marvin Gaye", "Mercy Mercy Me") == "reject"


def test_music_videos_are_demoted_not_rejected():
    """They usually carry the album audio, so they are a fine last resort —
    but a plain audio upload of the same song is a safer bet."""
    assert kind("Nirvana - Come As You Are (Official Music Video)") == "video"
    assert kind("Nirvana - Come As You Are (Official Video)") == "video"


def test_plain_and_lyric_uploads_are_ordinary_candidates():
    assert kind("Nirvana - Come As You Are") == "ok"
    assert kind("Come as You Are - Nirvana") == "ok"
    assert kind("Nirvana - Come As You Are (Lyrics)") == "ok"
    assert kind("Nirvana - Come as You Are [Nevermind] [HQ Sound]") == "ok"


def test_official_audio_is_preferred():
    assert kind("Nirvana - Come As You Are (Official Audio)") == "preferred"
    assert kind("Marvin Gaye - Mercy Mercy Me (The Ecology) (Visualizer)",
                "Marvin Gaye", "Mercy Mercy Me (The Ecology)") == "preferred"


def test_topic_channels_are_preferred_whatever_the_title_says():
    """YouTube's auto-generated `- Topic` channels are the distributor's own
    master audio: the closest thing to the record itself."""
    assert classify_title(
        "Come As You Are", ARTIST, TITLE, uploader="Nirvana - Topic") == "preferred"


def test_a_topic_channel_live_album_is_still_live():
    assert classify_title(
        "Come As You Are (Live)", ARTIST, TITLE,
        uploader="Nirvana - Topic") == "reject"


def test_matching_is_case_and_punctuation_insensitive():
    assert classify_title("NIRVANA - COME AS YOU ARE (LIVE AT READING)") == "reject"
    assert classify_title(
        "Marvin Gaye - Mercy, Mercy Me (Live at Montreux 1980)",
        "Marvin Gaye", "Mercy Mercy Me") == "reject"


def test_an_empty_title_is_merely_unremarkable():
    assert kind("") == "ok"
