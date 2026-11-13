# -*- coding: utf-8 -*-
"""2026-11-14 用户指令回归：纯图静默 + 引用紫卡截图直接触发分析。

守的是用户真正感受得到的行为：
  1. 单独发图片、没配视觉模型时，机器人不再回「没配视觉模型」那张卡；
  2. 但其它真实失败（图片取不到等）仍必须如实回复，不能被一起静默掉；
  3. 「先发紫卡截图 → 回复该截图 + 紫卡分析」：按被引用消息 id 精确取回同一份
     图片字节，跨群/跨人不串图，且允许同一张图被多次引用。
"""
from __future__ import annotations

import asyncio
import importlib
from types import SimpleNamespace

import pytest

from src.plugins.qq_bridge.channel import riven_cache
from src.plugins.qq_bridge.game_tools import (
    _RIVEN_ANALYZE_RE,
    _extract_reply_id,
    _riven_reply_cache_get,
    _riven_reply_cache_put,
)
from src.plugins.qq_bridge.multimodal.vision import (
    VisionClient,
    VisionError,
    VisionNotConfigured,
)


def _seg(t: str, **data):
    return SimpleNamespace(type=t, data=data)


def _ev(segs, mid=871389237, group_id=1075851417, user_id=1743124119):
    return SimpleNamespace(original_message=list(segs), message=list(segs),
                           message_id=mid, group_id=group_id, user_id=user_id)


def test_vision_not_configured_is_typed() -> None:
    """能力没开必须是独立异常类型，不许靠文案字符串做脆弱匹配。"""
    assert issubclass(VisionNotConfigured, VisionError)
    with pytest.raises(VisionNotConfigured) as ei:
        VisionClient(model="")._resolve_model()
    assert "AI_VISION_MODEL" in str(ei.value)


@pytest.mark.parametrize("raises, expected_replies", [
    (VisionNotConfigured("没配视觉模型喵——去配置 AI_VISION_MODEL"), 0),
    (VisionError("图片取不到（本地文件不存在）"), 1),
])
def test_pure_image_only_silences_missing_capability(monkeypatch, raises,
                                                     expected_replies) -> None:
    """纯图自动看图：能力未配置静默；其它真实错误仍如实回传（禁止扩大静默面）。"""
    mod = importlib.import_module("src.plugins.qq_bridge")
    calls: list[tuple] = []

    async def fake_reply(*args, **kwargs):
        calls.append(args)

    async def fake_look(*args, **kwargs):
        raise raises

    monkeypatch.setattr(mod, "_ctx", lambda ev: {})
    monkeypatch.setattr(mod.session_store, "get", lambda uid: None)
    monkeypatch.setattr(mod, "_reply", fake_reply)
    monkeypatch.setattr(mod.media_manager, "look", fake_look)
    ev = SimpleNamespace(user_id=1743124119, scope_key="g:1075851417",
                         images=["http://127.0.0.1/x.png"])
    asyncio.run(mod._handle_image_message(ev, "trace-test"))
    assert len(calls) == expected_replies


def test_extract_reply_id() -> None:
    assert _extract_reply_id(_ev([
        _seg("reply", id=871389237), _seg("text", text="紫卡分析")])) == "871389237"
    assert _extract_reply_id(_ev([
        _seg("reply", id=" 871389237 "), _seg("text", text="紫卡分析")])) == "871389237"
    assert _extract_reply_id(_ev([_seg("text", text="紫卡分析")])) == ""
    assert _extract_reply_id(_ev([_seg("reply", id=""), _seg("text", text="紫卡分析")])) == ""


def test_reply_image_cache_is_precise_and_repeatable() -> None:
    """被引用图按 (会话, 消息 id) 精确命中；peek 不消费；跨群/错 id 一律拿不到。"""
    riven_cache.clear()
    try:
        msg_a = _ev([_seg("image", url="http://x/y.png")], mid=871389237)
        _riven_reply_cache_put(msg_a, b"REAL_RIVEN_BYTES")
        msg_b = _ev([_seg("reply", id="871389237"),
                     _seg("text", text="紫卡分析")], mid=999)
        assert _riven_reply_cache_get(msg_b, "871389237") == b"REAL_RIVEN_BYTES"
        # 同一张图可被再次引用（只读不消费）
        assert _riven_reply_cache_get(msg_b, "871389237") == b"REAL_RIVEN_BYTES"
        other_group = _ev([_seg("reply", id="871389237")], group_id=999)
        assert _riven_reply_cache_get(other_group, "871389237") is None
        assert _riven_reply_cache_get(msg_b, "000") is None
        # 空图不写缓存，不编造
        _riven_reply_cache_put(_ev([_seg("image")], mid=555), b"")
        assert _riven_reply_cache_get(msg_b, "555") is None
    finally:
        riven_cache.clear()


@pytest.mark.parametrize("text, hit", [
    ("紫卡分析", True),
    ("帮我紫卡分析一下", True),
    ("@机器人 裂罅分析", True),
    ("riven 分析", True),
    ("紫卡价格", False),
    ("签到", False),
    ("全面分析", False),  # 走 _FULL_WAIT_WORDS 分支，不被本正则吞掉
])
def test_analyze_keyword(text, hit) -> None:
    assert bool(_RIVEN_ANALYZE_RE.search(text)) is hit
