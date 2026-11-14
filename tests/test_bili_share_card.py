# -*- coding: utf-8 -*-
"""B站视频「分享卡片」（bot → 用户）验收测试（2026-11-15）。

背景：B站 QQ 小程序（appid 1109937557）当前处于内测状态，get_mini_app_ark 生成的
`com.tencent.miniapp_01` 卡片点开必提示「该小程序内测中」，且无法把点击引到网页。
因此改用 `com.tencent.structmsg` 的 news 卡片：点开直达 B站视频网页。

验收标准：
  1) send_bili_share_card 构造 structmsg news 卡，jumpUrl 指向视频网页，tag=哔哩哔哩；
  2) 发出的是 json 段（Message 段数组），不是 CQ 字符串；
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


def _install_fake_connector(calls):
    async def _fake_call_action(action, params, timeout=30.0):
        calls.append((action, params))
        return {"message_id": 7}
    media_mod.connector.call_action = _fake_call_action
    media_mod._delay = lambda: 0.0
    media_mod.history.record_outgoing = lambda *a, **k: None


def test_send_bili_share_card_structmsg_news():
    calls = []
    _install_fake_connector(calls)
    asyncio.run(media_mod.send_bili_share_card(
        {"user_id": 1, "group_id": 0}, title="标题", desc="UP",
        pic_url="http://p", bvid="BV1GJ411x7h7"))

    # 小程序卡已证明走不通（内测墙），不应再调 get_mini_app_ark
    assert not any(a == "get_mini_app_ark" for a, _ in calls)

    send_call = next((a, p) for a, p in calls if a in ("send_private_msg", "send_group_msg"))
    msg = send_call[1]["message"]
    assert isinstance(msg, list) and len(msg) == 1  # Message 段数组，不是 CQ 字符串

    from nonebot.adapters.onebot.v11.adapter import DataclassEncoder
    ser = json.dumps(send_call[1], cls=DataclassEncoder)
    assert '"type": "json"' in ser
    # 卡片 JSON 在 data.data 里是转义字符串 → 解对象再断言
    card = json.loads(msg[0].data["data"])
    news = card["meta"]["news"]
    assert card["app"] == "com.tencent.structmsg"
    assert card["view"] == "news"
    assert news["tag"] == "哔哩哔哩"
    assert news["jumpUrl"] == "https://www.bilibili.com/video/BV1GJ411x7h7"


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
    assert any(a in ("send_private_msg", "send_group_msg") for a, _ in calls)
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
