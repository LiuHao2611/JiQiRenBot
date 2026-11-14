# -*- coding: utf-8 -*-
"""回归：成片体积闸必须「说话」，不能静默丢片（2026-11-14 实况）。

事故：用户转发 B站视频，`video_parse` 解析成功、下载成功（78.8MB），但被硬编码
的 50MB 上限拦住，只写一行 `video_too_large_skip` 就结束 —— 用户侧表现是
「视频没解析出来」（其实卡片发了，视频没了）。协议端实测 79MB 可正常发送，
故上限改为配置项 `VIDEO_PARSE_MAX_MB`（默认 200）。

本测试锁三件事：
  1. 超限 → 发一句「超过上限」，且**不发**视频段；
  2. 未超限 → 发视频段（走 _stage_for_protocol 后的协议端路径）；
  3. 大文件（>30MB）→ 先发一句「上传要一两分钟」再发视频。
"""
import asyncio
import json
import os

import pytest

from src.plugins.qq_bridge import video_parse as vp
from src.plugins.qq_bridge.video_parse.base import VideoParseResult

CARD = {
    "app": "com.tencent.miniapp_01",
    "meta": {"detail_1": {"appid": "1109937557", "qqdocurl": "https://b23.tv/zzz"}},
}


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
        self.last_kwargs = kwargs
        return {"message_id": len(self.sent)}

    async def delete_msg(self, message_id):
        self.deleted.append(int(message_id))
        return None


@pytest.fixture
def env(tmp_path, monkeypatch):
    """把外部依赖全部替换：解析、下载、历史落盘、AI 模式、落地目录。"""
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_ENABLED", True, raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_GROUP_AUTO", False, raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_OWNERS", [], raising=False)
    monkeypatch.setattr(vp.ai_mode_store, "is_on", lambda scope: False)
    monkeypatch.setattr(vp, "event_scope", lambda ev: "u:1")

    async def _noop(*a, **k):
        return None

    monkeypatch.setattr(vp, "_record_out", _noop)

    async def _fake_parse(url):
        return VideoParseResult(
            platform="bilibili", platform_display="B站", title="t", text="d",
            url="https://www.bilibili.com/video/BV1", extra={"bvid": "BV1"},
        )

    monkeypatch.setattr(vp, "_try_parse_one", _fake_parse)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_DIR", str(tmp_path / "pm"), raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_SEEN", "/app/data/media", raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_TTL", 7200, raising=False)
    return tmp_path


def _fake_download_with(path, size, monkeypatch):
    def _make(_self, _result):
        if size is None:
            return path  # 已存在文件按真实大小
        with open(path, "wb") as f:
            f.write(b"\x00" * size)
        return path

    async def _dl(self, result):
        return _make(self, result)

    monkeypatch.setattr(vp.BilibiliParser, "download_video", _dl)
    return path


def test_over_limit_says_so_and_skips_video(env, monkeypatch):
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_MAX_MB", 1, raising=False)
    p = env / "big.mp4"
    _fake_download_with(p, 2 * 1024 * 1024, monkeypatch)
    bot = _Bot()

    asyncio.run(vp._handle(bot, _Ev()))

    assert any("上限" in s for s in bot.sent), bot.sent
    assert not any("[CQ:video" in s for s in bot.sent), bot.sent


def test_within_limit_sends_video(env, monkeypatch):
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_MAX_MB", 200, raising=False)
    p = env / "ok.mp4"
    _fake_download_with(p, 1024 * 1024, monkeypatch)
    bot = _Bot()

    asyncio.run(vp._handle(bot, _Ev()))

    vids = [s for s in bot.sent if "[CQ:video" in s]
    assert len(vids) == 1, bot.sent
    assert "/app/data/media/" in vids[0], vids  # 协议端视角路径


def test_big_video_announces_upload_first(env, monkeypatch):
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_MAX_MB", 200, raising=False)
    p = env / "huge.mp4"
    _fake_download_with(p, 31 * 1024 * 1024, monkeypatch)
    bot = _Bot()

    asyncio.run(vp._handle(bot, _Ev()))

    texts = [s for s in bot.sent if "[CQ:" not in s]
    assert any("上传" in s for s in texts), bot.sent
    ids = [i for i, s in enumerate(bot.sent) if "[CQ:video" in s]
    assert ids and any(bot.sent.index(t) < ids[0] for t in texts), bot.sent
    # 「正在上传」发完必须被撤回，不留废话（用户 2026-11-14 要求）
    notice_id = bot.sent.index(next(t for t in texts if "上传" in t)) + 1  # send 返回的 message_id 从 1 递增
    assert notice_id in bot.deleted, (notice_id, bot.deleted)


def test_video_send_uses_long_timeout(env, monkeypatch):
    """22MB 上传就要 30s+，nonebot 默认 30s 会误判 timeout（实测已发成功却报失败）。"""
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_MAX_MB", 200, raising=False)
    p = env / "mid.mp4"
    _fake_download_with(p, 1024 * 1024, monkeypatch)
    bot = _Bot()

    asyncio.run(vp._handle(bot, _Ev()))

    assert bot.last_kwargs.get("_timeout", 0) >= 300, bot.last_kwargs
