# -*- coding: utf-8 -*-
"""B站分享卡片回呈验收测试（2026-11-15）。

验收标准：
  1) dispatcher._extract 通用抽取 json/xml 卡片段到 QQEvent.cards
  2) video_parse.bili_card_info 识别 B站视频/直播卡片（json 与 xml 形式），
     排除抖音卡片与纯文本段
  3) _handle_bilibili_card 原样回呈为卡片（调用 send_card 发 json/xml 段），
     不扒链接、不下载视频，并附一句简短说明
  4) video_parse._handle 对 B站卡片跳过（不触发下载分支）
"""
import asyncio
import json

import pytest

from src.plugins.qq_bridge import dispatcher as disp
from src.plugins.qq_bridge import video_parse as vp
from src.plugins.qq_bridge import config as cfg
from src.plugins.qq_bridge.video_parse import bili_card_info, _is_bili_card_seg


class Seg:
    def __init__(self, type_, data):
        self.type = type_
        self.data = data


BILI_VIDEO_CARD = {
    "app": "com.tencent.miniapp",
    "prompt": "[视频]分享了一个视频：【4K】年度最佳混剪",
    "meta": {
        "detail_1": {
            "appid": "100951776",
            "title": "【4K】年度最佳混剪",
            "desc": "UP主：影视飓风",
            "qqdocurl": "https://b23.tv/AbC123Xy",
            "host": "bilibili.com",
        }
    },
}
BILI_LIVE_CARD = {
    "app": "com.tencent.miniapp",
    "prompt": "正在直播：英雄联盟S赛",
    "meta": {
        "detail_1": {
            "title": "英雄联盟S赛 决赛日",
            "qqdocurl": "https://live.bilibili.com/123456",
            "host": "live.bilibili.com",
        }
    },
}
DOUYIN_CARD = {
    "app": "com.tencent.miniapp",
    "prompt": "分享了一个抖音视频",
    "meta": {"detail_1": {"title": "搞笑日常", "qqdocurl": "https://v.douyin.com/abc/"}},
}


# ---- 1) dispatcher 通用抽取 ----
def test_extract_collects_json_card():
    segs = [Seg("text", {"text": "看看这个"}), Seg("json", {"data": json.dumps(BILI_VIDEO_CARD)})]
    text, _at, _imgs, _atqq, _files, _voices, cards = disp._extract(segs)
    assert text == "看看这个"
    assert len(cards) == 1 and cards[0]["type"] == "json"


def test_extract_collects_xml_card():
    _t, _a, _i, _q, _f, _v, cards = disp._extract([Seg("xml", {"data": "<msg/>"})])
    assert len(cards) == 1 and cards[0]["type"] == "xml"


def test_extract_no_card_for_text_image():
    _t, _a, _i, _q, _f, _v, cards = disp._extract([Seg("text", {"text": "hi"}), Seg("image", {"url": "x"})])
    assert cards == []


# ---- 2) bili_card_info 识别 ----
def test_bili_video_detected():
    ok, kind, title = bili_card_info("json", json.dumps(BILI_VIDEO_CARD))
    assert ok is True and kind == "video" and title == "【4K】年度最佳混剪"


def test_bili_live_detected():
    ok, kind, _ = bili_card_info("json", json.dumps(BILI_LIVE_CARD))
    assert ok is True and kind == "live"


def test_bili_xml_detected():
    ok, _, _ = bili_card_info("xml", "<msg><qqdocurl>https://b23.tv/x</qqdocurl></msg>")
    assert ok is True


def test_douyin_not_bili():
    ok, _, _ = bili_card_info("json", json.dumps(DOUYIN_CARD))
    assert ok is False


def test_text_not_card():
    ok, _, _ = bili_card_info("text", {"text": "hello"})
    assert ok is False


def test_bili_card_dict_input():
    ok, _, _ = bili_card_info("json", BILI_VIDEO_CARD)
    assert ok is True


def test_seg_helpers():
    assert _is_bili_card_seg(Seg("json", {"data": json.dumps(BILI_VIDEO_CARD)})) is True
    assert _is_bili_card_seg(Seg("json", {"data": json.dumps(DOUYIN_CARD)})) is False


# ---- 3) _handle_bilibili_card 原样回卡片、不下载 ----
def test_handle_bili_card_echo():
    sent = []
    replies = []

    async def fake_send_card(ctx, seg_type, data, at_user=False):
        sent.append((seg_type, data, at_user))

    async def fake_reply(ctx, sess, text, title=None):
        replies.append((text, title))

    import src.plugins.qq_bridge as m
    m.send_card = fake_send_card
    m._reply = fake_reply
    ev = type("EV", (), {"user_id": 123, "group_id": 0, "is_group": False, "raw_text": ""})()
    asyncio.run(m._handle_bilibili_card(ev, {"type": "json", "data": json.dumps(BILI_VIDEO_CARD)}, "t1"))

    assert len(sent) == 1 and sent[0][0] == "json"
    assert json.loads(sent[0][1])["meta"]["detail_1"]["appid"] == "100951776"
    assert len(replies) == 1 and "收到 B站分享视频" in replies[0][0]


def test_handle_live_caption():
    replies = []

    async def fake_send_card(ctx, seg_type, data, at_user=False):
        pass

    async def fake_reply(ctx, sess, text, title=None):
        replies.append((text, title))

    import src.plugins.qq_bridge as m
    m.send_card = fake_send_card
    m._reply = fake_reply
    ev = type("EV", (), {"user_id": 123, "group_id": 0, "is_group": False, "raw_text": ""})()
    asyncio.run(m._handle_bilibili_card(ev, {"type": "json", "data": json.dumps(BILI_LIVE_CARD)}, "t2"))
    assert replies and "直播" in replies[0][0]


# ---- 4) video_parse 对 B站卡片跳过下载 ----
def test_video_parse_skips_bili_download(monkeypatch):
    dl = []
    monkeypatch.setattr(vp.bilibili.BilibiliParser, "download_video", lambda self, r: dl.append(1) or None)
    monkeypatch.setattr(cfg, "VIDEO_PARSE_ENABLED", True)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_ENABLED", True)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_GROUP_AUTO", True)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_OWNERS", [])
    monkeypatch.setattr(vp.ai_mode_store, "is_on", lambda scope: False)

    class FakeEvent:
        message_type = "private"
        user_id = 123
        group_id = 0

        def __init__(self, segs):
            self.message = segs

        def get_plaintext(self):
            return ""

    class FakeBot:
        async def send(self, event, message):
            return {"message_id": 1}

    asyncio.run(vp._handle(FakeBot(), FakeEvent([Seg("json", {"data": json.dumps(BILI_VIDEO_CARD)})])))
    assert dl == [], "B站卡片不应触发下载"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
