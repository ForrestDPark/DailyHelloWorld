from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "mp3_player_web"


def test_lyrics_are_not_visually_truncated():
    html = (PLAYER / "index.html").read_text(encoding="utf-8")
    assert "-webkit-line-clamp" not in html
    assert ".lyrics .lyric-line span{display:block" in html
    assert "overflow-wrap:anywhere" in html


def test_translation_stays_inside_player():
    html = (PLAYER / "index.html").read_text(encoding="utf-8")
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    assert 'id="lyrics-translation"' in html
    assert 'id="lyrics-translation-result"' in html
    assert 'id="lyrics-study-progress"' in html
    assert 'id="lyrics-study-eta"' in html
    assert "pollLyricsStudyResult" in script
    assert "/api/mp3/lyrics-study/status" in script
    assert "renderLyricsStudyResult" in script
    assert 'document.createElement("ruby")' in script
    assert 'document.createElement("rt")' in script
    assert ".lyrics-translation-result rt" in html
    assert "location.href = `/#room=" not in script


def test_message_creation_returns_source_id_for_translation_polling():
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert '"source_message_id": source_message_id' in source


def test_translation_status_uses_turn_result_and_worker_links_reply():
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/api/mp3/lyrics-study/status")' in source
    assert '"result": turn["reply"]' in source
    assert 'suppress_shift_alarm, reply_message_id' in source


def test_shuffle_previous_uses_play_history_instead_of_new_random_track():
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    assert "let shuffleHistory = []" in script
    assert "shuffleHistoryCursor - 1" in script
    assert "shuffleHistoryCursor + 1" in script
    assert "shuffleHistory: shuffleHistory.slice(-300)" in script


def test_japanese_music_recommendations_are_wired_to_player_and_download_queue():
    html = (PLAYER / "index.html").read_text(encoding="utf-8")
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert 'id="recommendations"' in html
    assert 'id="recommendation-preferences"' in html
    assert "/api/mp3-recommendations/preferences" in script
    assert "/api/shift-alarm/youtube-mp3" in script
    assert 'destination: "favorites"' in script
    assert "/api/mp3-player/favorites-library" in script
    assert "syncFavoritesPlaylist" in script
    assert "recommended_japanese" in script
    assert "www.youtube-nocookie.com/embed/" in script
    assert 'preview.textContent = "화면에서 재생"' in script
    assert "recommendation-player" in script
    assert 'value="popular">인기 애니송' in html
    assert 'value="season">분기별 OST' in html
    assert 'id="recommendations-more"' in html
    assert "IntersectionObserver" in script
    assert "next_cursor" in source
    assert "pollRecommendationDownload" in script
    assert 'button.textContent = "저장됨 ✓"' in script
    assert "recommendation-download-progress" in script
    assert "CREATE TABLE IF NOT EXISTS mp3_download_jobs" in (ROOT / "server" / "db.py").read_text(encoding="utf-8")
    assert "_recover_incomplete_download" in source
    assert '@app.get("/api/mp3-recommendations")' in source
    assert '"recommendations.css"' in source


def test_remote_favorite_lrc_jobs_reuse_mac_file_without_phone_upload():
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert '"favorites", "/api/mp3-player/favorites-library"' in script
    assert "await submitLrcJob(playlist[job.index])" in script
    assert "function trackFilename(track)" in script
    assert "library_kind: libraryKind" in script
    assert 'library_kind: str = "library"' in source
    assert 'source_library=body.library_kind' in source
    assert 'target_directory = MP3_FAVORITES_DIR if source_library == "favorites"' in source


def test_player_back_can_restore_recommendations_without_stopping_audio():
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    assert "RECOMMENDATIONS_RETURN_KEY" in script
    assert "async function returnToRecommendations" in script
    assert '$("player").classList.add("hidden")' in script
    assert '$("empty").classList.remove("hidden")' in script
    assert "audio.pause()" not in script[script.index("async function returnToRecommendations"):script.index("async function refreshRecommendations")]
