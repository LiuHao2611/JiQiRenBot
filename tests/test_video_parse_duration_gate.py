# -*- coding: utf-8 -*-
"""回归：超过 10 分钟的视频只发解析文字卡，不下载、不发视频。

用户指令（2026-11-14）：「视频超过10分钟就不发了，只发文本解析结果。」
闸门放在**下载之前**——超长片连下载都省掉（不白占带宽/落盘）；
时长拿不到时无法判定，按「不拦」处理并留痕，不瞎猜。
"""
import asyncio
import json

import pytest

from src.plugins.qq_bridge import video_parse as vp
from src.plugins.qq_bridge.video_parse.base import VideoParseResult

CARD = {"app": "com.tencent.miniapp_01",
        "meta": {"detail_1": {"appid": "1109937557", "qqdocurl": "https://b23.tv/zzz"}}}


class _Seg:
    def __init__(self, t, d):
        self.type = t
        self.data = d


class _Ev:
    message_type = "private"
    user_id = 10001
    group_id = 0
    self_id = 1

    def __init__(self):
        self.message = [_Seg("json", {"data": json.dumps(CARD)})]

    def get_plaintext(self):
        return ""


class _Bot:
    def __init__(self):
        self.sent = []
        self.deleted = []

    async def send(self, event, message, **kwargs):
        self.sent.append(str(message))
        return {"message_id": len(self.sent)}

    async def delete_msg(self, message_id):
        self.deleted.append(int(message_id))
        return None


def _run(tmp_path, monkeypatch, duration, max_minutes=10):
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_ENABLED", True, raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_GROUP_AUTO", False, raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_OWNERS", [], raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_MAX_MINUTES", max_minutes, raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_MAX_MB", 200, raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_DIR", str(tmp_path / "pm"), raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_SEEN", "/app/data/media", raising=False)
    monkeypatch.setattr(vp.ai_mode_store, "is_on", lambda scope: False)
    monkeypatch.setattr(vp, "event_scope", lambda ev: "u:1")

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(vp, "_record_out", _noop)

    async def _fake_parse(url):
        return VideoParseResult(
            platform="bilibili", platform_display="B站", title="t", text="d",
            duration=duration, url="https://www.bilibili.com/video/BV1",
            extra={"bvid": "BV1"},
        )

    monkeypatch.setattr(vp, "_try_parse_one", _fake_parse)

    calls = {"n": 0}

    async def _dl(self, result):
        calls["n"] += 1
        p = tmp_path / "v.mp4"
        p.write_bytes(b"\x00" * 1024)
        return str(p)

    monkeypatch.setattr(vp.BilibiliParser, "download_video", _dl)

    bot = _Bot()
    asyncio.run(vp._handle(bot, _Ev()))
    return bot, calls


def test_long_video_skips_download_and_send(tmp_path, monkeypatch):
    bot, calls = _run(tmp_path, monkeypatch, duration=11 * 60)
    assert calls["n"] == 0, "超长片不该下载（浪费带宽/磁盘）"
    assert not any("[CQ:video" in s for s in bot.sent), bot.sent
    # 解析文字卡仍要发
    assert any("B站" in s for s in bot.sent), bot.sent


def test_short_video_still_sends(tmp_path, monkeypatch):
    bot, calls = _run(tmp_path, monkeypatch, duration=5 * 60)
    assert calls["n"] == 1
    assert any("[CQ:video" in s for s in bot.sent), bot.sent


def test_unknown_duration_is_not_blocked(tmp_path, monkeypatch):
    """时长未知（None）时不拦——没有依据就不下判断。"""
    bot, calls = _run(tmp_path, monkeypatch, duration=None)
    assert calls["n"] == 1
    assert any("[CQ:video" in s for s in bot.sent), bot.sent


def test_gate_can_be_disabled(tmp_path, monkeypatch):
    """VIDEO_PARSE_MAX_MINUTES=0 → 不限时长。"""
    bot, calls = _run(tmp_path, monkeypatch, duration=3 * 3600, max_minutes=0)
    assert calls["n"] == 1
    assert any("[CQ:video" in s for s in bot.sent), bot.sent
