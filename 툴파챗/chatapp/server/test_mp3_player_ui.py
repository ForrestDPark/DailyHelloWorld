from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PLAYER = ROOT / "mp3_player_web"


def test_lyrics_are_not_visually_truncated():
    html = (PLAYER / "index.html").read_text(encoding="utf-8")
    assert "-webkit-line-clamp" not in html
    assert ".lyrics .lyric-line span{display:block" in html
    assert "overflow-wrap:anywhere" in html


def test_landscape_lyric_size_control_and_auto_fit_do_not_conflict():
    html = (PLAYER / "index.html").read_text(encoding="utf-8")
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    assert 'id="landscape-lyric-size"' in html
    assert ".lyrics .lyric-line.active{font-size:var(--active-lyric-size)}" in html
    assert ".lyrics .lyric-line.active{font-size:var(--active-lyric-size)!important}" not in html
    assert '$("landscape-lyric-size").addEventListener("click", cycleLyricSize)' in script
    assert 'node.style.removeProperty("line-height")' in script
    assert "fitVisibleLyrics();" in script[script.index("function setLyricSize"):script.index("function cycleLyricSize")]


def test_next_lyric_is_half_the_current_lyric_size_in_both_orientations():
    html = (PLAYER / "index.html").read_text(encoding="utf-8")
    assert "calc(var(--active-lyric-size) * .5)" in html
    assert "font-size:min(calc(var(--active-lyric-size) * .5),34px)" in html
    assert "calc(var(--active-lyric-size) * .78)" not in html


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


def test_landscape_playlist_translation_and_sync_controls_are_available():
    html = (PLAYER / "index.html").read_text(encoding="utf-8")
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    assert 'id="landscape-playlist"' in html
    assert 'id="landscape-translation"' in html
    assert 'id="landscape-sync"' in html
    assert 'id="translation-toggle"' in html
    assert 'id="sync-earlier"' in html and 'id="sync-later"' in html
    assert 'playlist.length < 1' in script
    assert "mapLyricTranslations" in script
    assert '$("translation-toggle").addEventListener("click", toggleLyricTranslation)' in script
    assert "LRC_SYNC_OFFSETS_KEY" in script
    assert "lyricRows[index].time + manualLyricOffset" in script


def test_message_creation_returns_source_id_for_translation_polling():
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert '"source_message_id": source_message_id' in source


def test_translation_status_uses_turn_result_and_worker_links_reply():
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert '@app.get("/api/mp3/lyrics-study/status")' in source
    assert '"result": turn["reply"]' in source
    assert 'suppress_shift_alarm, reply_message_id' in source


def test_translation_history_recovers_completed_result_after_reopening_player():
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert "/api/mp3/lyrics-study/history" in script
    assert "recoverLyricsStudyRecord(nextKey)" in script
    assert "곡 식별자: ${trackIdentity}" in script
    assert '@app.get("/api/mp3/lyrics-study/history")' in source
    assert "브라우저 저장소가 사라져도 서버 채팅 원장에서 이전 직해를 복구한다" in source
    assert 'm.sender=?' in source
    assert "legacy_youtube_matches" in source


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
    assert 'id="recommendation-sort"' in html
    assert "sortedRecommendationItems" in script
    assert 'mode === "views"' in script
    assert 'mode === "anime"' in script
    assert 'mode === "artist"' in script
    assert "collapsedRecommendationGroups" in script
    assert "initializedRecommendationGroups" in script
    assert "collapsedRecommendationGroups.add(group)" in script
    assert 'heading.setAttribute("aria-expanded"' in script
    assert 'window.addEventListener("scroll"' in script
    assert "recommendations-active" in script
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


def test_korean_track_is_not_classified_as_japanese_from_bad_lrc():
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    assert "function detectTrackLanguageHint(item)" in script
    assert "function resolveTrackLyricsLanguage(item, text)" in script
    assert 'titleLanguage === "ko" && lyricsLanguage === "ja"' in script
    assert "한국어 곡인데 기존 LRC가 일본어로 잘못 인식됐습니다" in script
    assert "def _infer_lrc_language_hint(filename: str)" in source
    assert '"-l", language_hint or "auto"' in source
    assert "한국어 곡에서 일본어 오인식이 감지되어" in source


def test_language_filter_uses_explicit_markers_and_rechecks_legacy_tracks():
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    source = (ROOT / "server" / "app.py").read_text(encoding="utf-8")
    detector = script[script.index("function detectTrackLanguageHint"):script.index("function resolveTrackLyricsLanguage")]
    resolver = script[script.index("function resolveTrackLyricsLanguage"):script.index("function compactHash")]
    assert "item?.recommended_japanese" in detector
    assert "제이팝" in detector
    assert "케이팝" in detector
    assert "hangul >= 4" not in detector
    assert 'titleLanguage !== "unknown" ? titleLanguage : lyricsLanguage' in resolver
    assert "item.languageAnalyzed !== true" in script
    assert "item.languageAnalyzed = true" in script
    assert "제이팝" in source
    assert "케이팝" in source
    assert "hangul >= 4" not in source[source.index("def _infer_lrc_language_hint"):source.index("def _lrc_script_language")]


def test_player_back_can_restore_recommendations_without_stopping_audio():
    script = (PLAYER / "app.js").read_text(encoding="utf-8")
    assert "RECOMMENDATIONS_RETURN_KEY" in script
    assert "async function returnToRecommendations" in script
    assert '$("player").classList.add("hidden")' in script
    assert '$("empty").classList.remove("hidden")' in script
    assert "audio.pause()" not in script[script.index("async function returnToRecommendations"):script.index("async function refreshRecommendations")]
