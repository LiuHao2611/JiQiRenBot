# -*- coding: utf-8 -*-
"""B站视频「分享卡片」（bot → 用户）验收测试（2026-11-15）。

验收标准：
  1) send_bili_share_card 调协议端 get_mini_app_ark，jumpUrl 必须是**小程序页面路径**
     `/pages/video/video?bvid=BV...`（填成 http 网址点开会落 B站首页）；
  2) 发出的是 json 段（Message 段数组），ark 完整；
  3) _share_bili_card 解析后发送并记录历史；
  4) _handle 在 VIDEO_PARSE_ENABLED=False（下载关闭）时仍会发卡片；
  5) 非 B站视频链接不触发。

同步风格（asyncio.run）—— 项目用 anyio，裸 async test 不会被执行。
"""
import asyncio
import json

import src.plugins.qq_bridge.media as media_mod
import src.plugins.qq_bridge.video_parse as vp
from src.plugins.qq_bridge.video_parse.base import VideoParseResult

ARK = {"app": "com.tencent.miniapp_01",
       "view": "view_8C8E89B49BE609866298ADDFF2DBABA4",
       "config": {"token": "deadbeefdeadbeefdeadbeefdeadbeef"},
       "meta": {"detail_1": {"appid": "1109937557", "desc": "标题", "preview": "http://p"}},
       "prompt": "[QQ小程序]标题", "ver": "1.0.0.19"}


def _install_fake_connector(calls):
    async def _fake_call_action(action, params, timeout=30.0):
        calls.append((action, params))
        if action == "get_mini_app_ark":
            return {"data": ARK}
        return {"message_id": 7}
    media_mod.connector.call_action = _fake_call_action
    media_mod._delay = lambda: 0.0
    media_mod.history.record_outgoing = lambda *a, **k: None


def test_send_bili_share_card_builds_ark_and_sends_json():
    calls = []
    _install_fake_connector(calls)
    asyncio.run(media_mod.send_bili_share_card(
        {"user_id": 1, "group_id": 0}, title="标题", desc="UP",
        pic_url="http://p", bvid="BV1GJ411x7h7"))

    ark_call = next(p for a, p in calls if a == "get_mini_app_ark")
    # 必须走自定义 schema：不能带 type（带 type 走内置模板 → 内测提示/落首页）
    assert "type" not in ark_call
    assert ark_call["appId"] == "1109937557"
    assert ark_call["sdkId"] == "V1_PC_MINISDK_99.99.99_1_APP_A"
    assert ark_call["versionId"] == "cfc5f7b05b44b5956502edaecf9d2240"
    assert ark_call["withShareTicket"] == "0"
    assert ark_call["jumpUrl"] == "/pages/video/video?bvid=BV1GJ411x7h7"
    assert ark_call["title"] == "标题" and ark_call["picUrl"] == "http://p"

    send_call = next((a, p) for a, p in calls if a in ("send_private_msg", "send_group_msg"))
    msg = send_call[1]["message"]
    assert isinstance(msg, list) and len(msg) == 1  # Message 段数组，不是 CQ 字符串
    from nonebot.adapters.onebot.v11.adapter import DataclassEncoder
    ser = json.dumps(send_call[1], cls=DataclassEncoder)
    assert '"type": "json"' in ser and "com.tencent.miniapp_01" in ser


def test_share_bili_card_parses_then_sends(monkeypatch):
    async def _fake_parse(url):
        return VideoParseResult(platform="bilibili", platform_display="B站",
                                title="视频标题", author_name="UP主",
                                cover_url="http://cover", extra={"bvid": "BV1GJ411x7h7"})

    recorded = []

    async def _fake_record(event, raw, sent=None):
        recorded.append(raw)

    monkeypatch.setattr(vp, "_try_parse_one", _fake_parse)
    monkeypatch.setattr(vp, "_record_out", _fake_record)
    calls = []
    _install_fake_connector(calls)
    ev = type("EV", (), {"user_id": 1, "group_id": 0, "message_type": "private"})()
    ok = asyncio.run(vp._share_bili_card(None, ev, "https://www.bilibili.com/video/BV1GJ411x7h7"))
    assert ok is True
    assert any(a == "get_mini_app_ark" for a, _ in calls)
    assert recorded and "BV1GJ411x7h7" in recorded[0]


def test_handle_shares_even_when_download_disabled(monkeypatch):
    shared = []

    async def _fake_share(bot, event, url):
        shared.append(url)
        return True

    monkeypatch.setattr(vp, "_share_bili_card", _fake_share)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_ENABLED", False)
    monkeypatch.setattr(vp.Config, "BILI_SHARE_CARD", True)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_GROUP_AUTO", True)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_OWNERS", [])
    monkeypatch.setattr(vp.ai_mode_store, "is_on", lambda scope: False)

    class FakeEvent:
        message_type = "private"
        user_id = 1
        group_id = 0
        message = []

        def get_plaintext(self):
            return "看看 https://www.bilibili.com/video/BV1GJ411x7h7"

    asyncio.run(vp._handle(None, FakeEvent()))
    assert shared and "BV1GJ411x7h7" in shared[0]


def test_handle_ignores_non_bili(monkeypatch):
    shared = []

    async def _fake_share(bot, event, url):
        shared.append(url)
        return True

    monkeypatch.setattr(vp, "_share_bili_card", _fake_share)
    monkeypatch.setattr(vp.Config, "BILI_SHARE_CARD", True)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_GROUP_AUTO", True)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_OWNERS", [])
    monkeypatch.setattr(vp.ai_mode_store, "is_on", lambda scope: False)

    class FakeEvent:
        message_type = "private"
        user_id = 1
        group_id = 0
        message = []

        def get_plaintext(self):
            return "https://v.douyin.com/abc/"

    asyncio.run(vp._handle(None, FakeEvent()))
    assert shared == []


def test_is_bili_video_url():
    assert vp._is_bili_video_url("https://www.bilibili.com/video/BV1xx") is True
    assert vp._is_bili_video_url("https://b23.tv/abc") is True
    assert vp._is_bili_video_url("https://live.bilibili.com/1") is False
    assert vp._is_bili_video_url("https://v.douyin.com/x/") is False
