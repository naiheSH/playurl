import importlib.util
import io
import json
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlayUrlTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.netease = load("netease_playurl_test", "playurl/netease/playurl.py")
        cls.qq = load("qq_playurl_test", "playurl/qq/playurl.py")
        cls.qq_playlist = load("qq_playlist_test", "playurl/qq/playlist.py")
        cls.kugou_playlist = load("kugou_playlist_test", "playurl/kugou/playlist.py")
        cls.kugou_playurl = load("kugou_playurl_test", "playurl/kugou/playurl.py")
        cls.qishui = load("qishui_playurl_test", "playurl/qishui/playurl.py")
        cls.qishui_playlist = load("qishui_playlist_test", "playurl/qishui/playlist.py")
        cls.spotify = load("spotify_playurl_test", "playurl/spotify/playurl.py")
        cls.youtube_playurl = load("youtube_playurl_test", "playurl/youtube/playurl.py")
        cls.youtube_playlist = load("youtube_playlist_test", "playurl/youtube/playlist.py")
        cls.netease_login = load("netease_login_test", "playurl/netease/login.py")
        cls.qq_login = load("qq_login_test", "playurl/qq/login.py")
        cls.kugou_login = load("kugou_login_test", "playurl/kugou/login.py")
        cls.qishui_login = load("qishui_login_test", "playurl/qishui/login.py")

    def test_login_scripts_write_private_platform_local_cookies(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cases = [
                (self.netease_login, lambda module: module.save_cookie([
                    SimpleNamespace(name="MUSIC_U", value="netease-secret"),
                ]), "MUSIC_U="),
                (self.qq_login, lambda module: module.save_credential(SimpleNamespace(
                    musicid=123, str_musicid="", musickey="qq-secret",
                )), "qm_keyst="),
                (self.kugou_login, lambda module: module.save_cookie(
                    "123", "kugou-secret", "456", "DEVICE",
                ), "token="),
                (self.qishui_login, lambda module: module.save_cookie([
                    SimpleNamespace(name="sessionid", value="qishui-secret"),
                ]), "sessionid="),
            ]
            for index, (module, writer, expected) in enumerate(cases):
                platform_dir = root / str(index)
                platform_dir.mkdir()
                cookie_file = platform_dir / "cookie"
                with patch.object(module, "HERE", platform_dir), patch.object(module, "COOKIE_FILE", cookie_file):
                    writer(module)
                self.assertIn(expected, cookie_file.read_text(encoding="utf-8"))
                self.assertEqual(stat.S_IMODE(os.stat(cookie_file).st_mode), 0o600)

    def test_qq_playlist_search_uses_record_offset(self):
        def fake_get(_url, query, timeout=12, login=False):
            start = (query["page_no"] - 1) * query["num_per_page"]
            return {"data": {"list": [{"dissid": str(i + 1), "dissname": "p%s" % i} for i in range(start, start + query["num_per_page"])]}}

        with patch.object(self.qq_playlist, "get_json", side_effect=fake_get):
            rows = self.qq_playlist.search("x", 10, 25)
        self.assertEqual([row["name"] for row in rows], ["p%s" % i for i in range(25, 35)])

    def test_qq_private_playlist_detail_uses_login_cookie(self):
        calls = []

        def fake_get(_url, _query, timeout=12, login=False):
            calls.append(login)
            return {"cdlist": [{"dissid": "truncated", "songlist": [
                {"songmid": "song-mid", "songname": "Song", "singer": [{"name": "Artist"}]},
            ]}]}

        with patch.object(self.qq_playlist, "load_cookie", return_value="uin=1; qm_keyst=k"), \
                patch.object(self.qq_playlist, "get_json", side_effect=fake_get):
            result = self.qq_playlist.tracks("968428647", 3, 0)
        self.assertEqual(calls, [True])
        self.assertEqual(result["playlist"]["id"], "968428647")
        self.assertEqual(result["songs"][0]["id"], "song-mid")

    def test_kugou_playlist_search_uses_record_offset(self):
        def fake_get(url, timeout=12):
            from urllib.parse import parse_qs, urlparse
            query = parse_qs(urlparse(url).query)
            page = int(query["page"][0])
            size = int(query["pagesize"][0])
            start = (page - 1) * size
            return {"status": 1, "data": {"info": [{"specialid": str(i + 1), "specialname": "p%s" % i} for i in range(start, start + size)]}}

        with patch.object(self.kugou_playlist, "get_json", side_effect=fake_get):
            rows = self.kugou_playlist.search("x", 8, 17)
        self.assertEqual([row["name"] for row in rows], ["p%s" % i for i in range(17, 25)])

    def test_kugou_mine_uses_record_offset_across_pages(self):
        def fake_gateway(_path, body, timeout=12):
            start = (body["page"] - 1) * body["pagesize"]
            return {"info": {"list": [{"global_collection_id": "collection_x_x_%s_x" % i, "name": "p%s" % i} for i in range(start, start + body["pagesize"])]}}

        auth = {"userid": "1", "token": "t", "mid": "m", "dfid": "-", "ready": True}
        with patch.object(self.kugou_playlist, "load_cookie", return_value="userid=1; token=t"), \
                patch.object(self.kugou_playlist, "auth_from", return_value=auth), \
                patch.object(self.kugou_playlist, "gateway", side_effect=fake_gateway):
            rows = self.kugou_playlist.mine(10, 45)
        self.assertEqual([row["name"] for row in rows], ["p%s" % i for i in range(45, 55)])

    def test_kugou_mine_gateway_uses_android_signature(self):
        from urllib.parse import parse_qs, urlparse

        captured = {}

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_):
                return False

            def read(self):
                return b'{"status":1,"data":{"info":{"list":[]}}}'

        def fake_urlopen(request, timeout=12):
            captured["request"] = request
            return Response()

        cookie = "userid=1; token=test-token; kg_mid=123; kg_dfid=-"
        with patch.object(self.kugou_playlist, "load_cookie", return_value=cookie), \
                patch.object(self.kugou_playlist.time, "time", return_value=1700000000), \
                patch.object(self.kugou_playlist, "urlopen", side_effect=fake_urlopen):
            self.kugou_playlist.gateway("/v7/get_all_list", {"userid": 1}, timeout=3)

        request = captured["request"]
        query = {key: value[0] for key, value in parse_qs(urlparse(request.full_url).query).items()}
        self.assertEqual(query["appid"], "1005")
        self.assertEqual(query["clientver"], "20489")
        self.assertEqual(query["clienttime"], "1700000000")
        self.assertEqual(query["uuid"], "-")
        self.assertNotIn("srcappid", query)
        signature = query.pop("signature")
        body = request.data.decode()
        parts = ["%s=%s" % item for item in sorted(query.items())]
        expected = self.kugou_playlist.md5(
            self.kugou_playlist.ANDROID_SALT + "".join(parts) + body + self.kugou_playlist.ANDROID_SALT
        )
        self.assertEqual(signature, expected)
        self.assertEqual(request.headers["X-router"], "cloudlist.service.kugou.com")

    def test_kugou_standard_rejects_higher_web_result(self):
        payload = {"status": 1, "data": {"bitrate": 320000, "play_url": "https://example.test/audio"}}
        with patch.object(self.kugou_playurl, "get_json", return_value=payload):
            result = self.kugou_playurl.via_web("a" * 32, "1", 2, "", {"mid": "m", "dfid": "-", "token": "", "userid": ""}, "standard", 1)
        self.assertIsNone(result)

    def test_kugou_v6_selects_128_and_marks_partial_stream(self):
        payload = {"status": 1, "data": [
            {"quality": "320", "info": {"tracker_url": ["https://example.test/320.mp3"], "tracker_type": "full"}},
            {"quality": "128", "info": {"tracker_url": ["https://example.test/128.mp3"], "tracker_type": "part"}},
        ]}
        auth = {"userid": "1", "token": "t", "mid": "m", "dfid": "d", "ready": True}
        with patch.object(self.kugou_playurl, "post_json", return_value=payload):
            result = self.kugou_playurl.via_v6("A" * 32, 2, "userid=1; token=t", auth, "standard", 1)
        self.assertEqual(result["url"], "https://example.test/128.mp3")
        self.assertEqual(result["level"], "standard")
        self.assertTrue(result["trial"])

    def test_qishui_keeps_full_cookie(self):
        headers = self.qishui.request_headers("sessionid=s; uid_tt=u")
        self.assertEqual(headers["Cookie"], "sessionid=s; uid_tt=u")

    def test_qishui_playurl_falls_back_to_core_sessionid(self):
        payload = {"status_code": 0, "track_player": {}}
        with patch.object(
            self.qishui,
            "_fetch_track_with_cookie",
            side_effect=[self.qishui.QishuiError("rejected"), payload],
        ) as fetch:
            result = self.qishui.fetch_track(
                "123", "sessionid=s; sid_guard=expired; uid_tt=old", 3
            )
        self.assertEqual(result, payload)
        self.assertEqual(fetch.call_args_list[0].args[1], "sessionid=s; sid_guard=expired; uid_tt=old")
        self.assertEqual(fetch.call_args_list[1].args[1], "sessionid=s")

    def test_qishui_playlist_falls_back_to_core_sessionid(self):
        with patch.object(
            self.qishui_playlist,
            "get_json",
            side_effect=[RuntimeError("rejected"), {"status_code": 0}],
        ) as get_json:
            result = self.qishui_playlist.authenticated_get_json(
                "/luna/pc/me", {}, "sessionid=s; sid_guard=expired", 3
            )
        self.assertEqual(result, {"status_code": 0})
        self.assertEqual(get_json.call_args_list[0].args[2], "sessionid=s; sid_guard=expired")
        self.assertEqual(get_json.call_args_list[1].args[2], "sessionid=s")

    def test_qishui_aes_ctr_known_vector(self):
        key = bytes.fromhex("2b7e151628aed2a6abf7158809cf4f3c")
        iv = bytes.fromhex("f0f1f2f3f4f5f6f7f8f9fafbfcfdfeff")
        plain = bytes.fromhex("6bc1bee22e409f96e93d7e117393172a")
        self.assertEqual(self.qishui._aes_ctr(plain, key, iv).hex(), "874d6191b620e3261bef6864990db6ce")

    def test_qishui_nested_video_model_is_encrypted_not_direct(self):
        payload = {"data": {"track_player": {"video_model": json.dumps({"encrypt_info": {"spade_a": "a+b="}, "play": {"main_play_url": "https://example.test/a", "bitrate": 320000}})}}}
        with patch.object(self.qishui, "load_cookie", return_value="sessionid=s; uid_tt=u"), \
                patch.object(self.qishui, "fetch_track", return_value=payload), \
                patch.object(self.qishui, "ENABLE_FLAC", True):
            result = self.qishui.resolve("123")
        self.assertTrue(result["playable"])
        self.assertTrue(result["encrypted"])
        self.assertFalse(result["directPlayable"])
        self.assertIn("#auth=a%2Bb%3D", result["url"])

    def test_qishui_public_free_track_fallback_returns_target_stream(self):
        payload = {
            "seo_track": {
                "track": {
                    "id": "123",
                    "label_info": {"quality_map": {
                        "highest": {"play_detail": {"need_vip": False, "need_purchase": False}}
                    }},
                },
                "track_player": {"video_model": json.dumps({"video_list": [{
                    "main_url": "https://example.test/full.m4a",
                    "video_meta": {"quality": "highest", "bitrate": 256000},
                }]})},
            },
            "recommend": [{"main_url": "https://example.test/wrong.m4a", "bitrate": 999999}],
        }
        with patch.object(self.qishui, "load_cookie", return_value="sessionid=s"), \
                patch.object(self.qishui, "fetch_track", side_effect=self.qishui.QishuiError("empty", "empty_response")), \
                patch.object(self.qishui, "fetch_public_track", return_value=payload):
            result = self.qishui.resolve("123")
        self.assertTrue(result["playable"])
        self.assertEqual(result["url"], "https://example.test/full.m4a")
        self.assertEqual(result["level"], "highest")
        self.assertEqual(result["bitrate"], 256000)
        self.assertEqual(result["source"], "qishui-public-seo")
        self.assertEqual(result["httpHeaders"], {
            "User-Agent": "LunaPC/3.3.0(359450208)",
            "Referer": "https://www.qishui.com/",
        })

    def test_qishui_public_vip_track_is_not_exposed(self):
        payload = {"seo_track": {
            "track": {"id": "123", "label_info": {"only_vip_playable": True}},
            "track_player": {"video_model": json.dumps({"video_list": [{
                "main_url": "https://example.test/should-not-return.m4a",
                "video_meta": {"quality": "highest", "bitrate": 256000},
            }]})},
        }}
        with patch.object(self.qishui, "load_cookie", return_value="sessionid=s"), \
                patch.object(self.qishui, "fetch_track", side_effect=self.qishui.QishuiError("empty", "empty_response")), \
                patch.object(self.qishui, "fetch_public_track", return_value=payload):
            result = self.qishui.resolve("123")
        self.assertFalse(result["playable"])
        self.assertEqual(result["restriction"]["category"], "vip_required")
        self.assertEqual(result["url"], "")

    def test_qishui_public_free_track_does_not_require_cookie(self):
        payload = {"seo_track": {
            "track": {"id": "123", "duration": 60000, "label_info": {}},
            "track_player": {"video_model": json.dumps({"video_list": [{
                "main_url": "https://example.test/free.m4a",
                "video_meta": {"quality": "higher", "bitrate": 128000, "size": 960000, "vtype": "m4a"},
            }]})},
        }}
        with patch.object(self.qishui, "load_cookie", return_value=""), \
                patch.object(self.qishui, "fetch_public_track", return_value=payload):
            result = self.qishui.resolve("123")
        self.assertTrue(result["playable"])
        self.assertFalse(result["loggedIn"])
        self.assertEqual(result["duration"], 60000)
        self.assertEqual(result["size"], 960000)
        self.assertEqual(result["format"], "m4a")
        self.assertEqual(result["httpHeaders"], self.qishui.PLAYBACK_HEADERS)

    def test_qishui_default_skips_flac_and_selects_m4a(self):
        payload = {"seo_track": {
            "track": {"id": "123", "label_info": {}},
            "track_player": {"video_model": json.dumps({"video_list": [
                {"main_url": "https://example.test/lossless.flac", "format": "flac", "bitrate": 999000},
                {"main_url": "https://example.test/high.m4a", "format": "m4a", "bitrate": 256000},
            ]})},
        }}
        with patch.object(self.qishui, "load_cookie", return_value=""), \
                patch.object(self.qishui, "fetch_public_track", return_value=payload):
            result = self.qishui.resolve("123")
        self.assertEqual(result["url"], "https://example.test/high.m4a")
        self.assertEqual(result["format"], "m4a")

    def test_format_defaults_disable_flac(self):
        self.assertFalse(self.netease.ENABLE_FLAC)
        self.assertFalse(self.qq.ENABLE_FLAC)
        self.assertFalse(self.kugou_playurl.ENABLE_FLAC)
        self.assertFalse(self.qishui.ENABLE_FLAC)
        self.assertFalse(self.youtube_playurl.ENABLE_FLAC)
        names = [row["filename"] for row in self.qq.candidates("song", "", "exhigh")]
        self.assertTrue(names)
        self.assertFalse(any(name.endswith(".flac") for name in names))

    def test_qishui_json_output_is_pretty_printed(self):
        result = {
            "provider": "qishui", "id": "123", "url": "https://example.test/a.m4a",
            "playable": True, "directPlayable": True,
        }
        output = io.StringIO()
        with patch.object(self.qishui, "resolve", return_value=result), redirect_stdout(output):
            code = self.qishui.main(["playurl.py", "123", "--json"])
        self.assertEqual(code, 0)
        self.assertTrue(output.getvalue().startswith('{\n  "provider"'))
        self.assertEqual(json.loads(output.getvalue()), result)

    def test_qishui_playlist_extracts_wrapped_track(self):
        payload = {"media_resources": [{"entity": {"track_wrapper": {"track": {
            "id": "123", "name": "Song", "artists": [{"name": "Artist"}],
            "album": {"name": "Album"}, "duration": 4567,
        }}}}]}
        self.assertEqual(self.qishui_playlist.extract_tracks(payload), [{
            "provider": "qishui", "id": "123", "name": "Song",
            "artist": "Artist", "album": "Album", "duration": 4567,
        }])

    def test_qishui_primary_liked_playlist_ignores_douyin_collection(self):
        self.assertTrue(self.qishui_playlist.is_primary_liked_playlist({"title": "我喜欢的音乐"}))
        self.assertFalse(self.qishui_playlist.is_primary_liked_playlist({"title": "我在抖音收藏的音乐"}))

    def test_qishui_public_playlist_has_no_cookie(self):
        self.assertNotIn("Cookie", self.qishui_playlist.headers(""))

    def test_qishui_playlist_search_uses_q_and_record_cursor(self):
        calls = []

        def fake_get(path, params, cookie, timeout=12, user_agent=""):
            calls.append((path, params, user_agent))
            start = int(params["cursor"])
            return {"result_groups": [{
                "data": [{"entity": {"playlist": {"id": str(i), "title": "P%s" % i}}} for i in range(start, start + 20)],
                "has_more": True, "next_cursor": str(start + 20),
            }]}

        with patch.object(self.qishui_playlist, "require_session", return_value=("sessionid=s", {})), \
                patch.object(self.qishui_playlist, "get_json", side_effect=fake_get):
            rows = self.qishui_playlist.search("x", 10, 25)
        self.assertEqual([row["name"] for row in rows], ["P%s" % i for i in range(25, 35)])
        self.assertEqual(calls[0][0], "/luna/pc/search/playlist")
        self.assertEqual(calls[0][1]["q"], "x")
        self.assertEqual(calls[0][1]["cursor"], 25)
        self.assertEqual(calls[0][2], self.qishui_playlist.SEARCH_UA)

    def test_spotify_exposes_official_modes_without_audio_url(self):
        output = io.StringIO()
        with redirect_stdout(output):
            code = self.spotify.main(["playurl.py", "4uLU6hMCjMI75M1A2tKUQC", "--json"])
        payload = json.loads(output.getvalue())
        self.assertEqual(code, 1)
        self.assertFalse(payload["playable"])
        self.assertIn("spotify_web_playback_sdk", payload["supportedPlayback"])

    def test_spotify_uses_current_search_limit_and_playlist_shape(self):
        spotify_search = load("spotify_search_limit_test", "playurl/spotify/search.py")
        spotify_playlist = load("spotify_playlist_shape_test", "playurl/spotify/playlist.py")
        with patch.object(spotify_search, "config", return_value={
                "client_id": "id", "client_secret": "secret", "access_token": "token", "market": "",
        }), patch.object(spotify_search, "api_get", return_value={"tracks": {"items": []}}) as api_get:
            spotify_search.search("x", 50)
        self.assertEqual(api_get.call_args.args[1]["limit"], 10)
        row = spotify_playlist.playlist_row({
            "id": "p", "name": "P", "items": {"total": 12}, "owner": {"display_name": "U"},
        }, "mine")
        self.assertEqual(row["trackCount"], 12)

    def test_youtube_selects_audio_only_stream_and_reads_expiry(self):
        info = {
            "url": "https://example.test/video?expire=2000000000", "acodec": "opus", "vcodec": "vp9", "tbr": 500,
            "requested_downloads": [{
                "url": "https://example.test/audio?expire=2000000000", "acodec": "opus",
                "vcodec": "none", "abr": 128, "format_id": "251",
            }],
        }
        stream = self.youtube_playurl.pick_stream(info)
        self.assertEqual(stream["format_id"], "251")
        expires_at, remaining = self.youtube_playurl.expiry(stream["url"])
        self.assertEqual(expires_at, 2000000000)
        self.assertGreaterEqual(remaining, 0)

    def test_youtube_reads_gitignored_token_file(self):
        with tempfile.TemporaryDirectory() as directory:
            token = Path(directory) / "token"
            token.write_text("# local only\nraw-token\nmweb.player+player-token\n", encoding="utf-8")
            with patch.object(self.youtube_playurl, "HERE", Path(directory)):
                args = self.youtube_playurl.token_args()
        self.assertEqual(args[0], "--extractor-args")
        self.assertIn("mweb.gvs+raw-token", args[1])
        self.assertIn("mweb.player+player-token", args[1])

    def test_youtube_normalizes_video_and_playlist_urls(self):
        video_id, _ = self.youtube_playurl.normalize_video("https://youtu.be/dQw4w9WgXcQ")
        playlist_id, _ = self.youtube_playlist.normalize_playlist(
            "https://www.youtube.com/playlist?list=PL1234567890abcdef"
        )
        self.assertEqual(video_id, "dQw4w9WgXcQ")
        self.assertEqual(playlist_id, "PL1234567890abcdef")
        self.assertIsNone(self.youtube_playlist.playlist_row({
            "id": "UC1234567890abcdef", "url": "https://www.youtube.com/channel/UC1234567890abcdef",
        }))
        self.assertEqual(self.youtube_playlist.playlist_row({
            "id": "PL1234567890abcdef",
            "url": "https://www.youtube.com/playlist?list=PL1234567890abcdef",
            "title": "Playlist",
        })["name"], "Playlist")

    def test_parameter_errors_exit_two(self):
        cases = [
            ["playurl/netease/search.py", "x", "not-a-number"],
            ["playurl/qq/playlist.py", "unknown"],
            ["playurl/qishui/playurl.py", "123", "--decrypt"],
            ["playurl/qishui/playlist.py", "search"],
            ["playurl/spotify/playurl.py", "bad-id"],
            ["playurl/youtube/playurl.py", "bad-id"],
            ["playurl/youtube/playlist.py", "tracks", "bad"],
        ]
        for args in cases:
            completed = subprocess.run([sys.executable, str(ROOT / args[0]), *args[1:]], capture_output=True, text=True, check=False)
            self.assertEqual(completed.returncode, 2, (args, completed.stdout, completed.stderr))


if __name__ == "__main__":
    unittest.main()
