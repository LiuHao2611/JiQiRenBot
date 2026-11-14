# -*- coding: utf-8 -*-
"""回归：视频解析成片必须落到协议端读得到的路径（2026-11-14 实测事故）。

事故：SnowLuma 协议端和 bridge 是**两个容器、不共享文件系统**。原实现把
`download_video()` 返回的 bridge 本地绝对路径（/tmp/bili_xxx/BV.mp4）直接塞给
视频段，协议端 realpath 直接报：

    ENOENT: no such file or directory, realpath '/app/tmp/test_video.mp4'

结果卡片有、视频永远收不到（用户侧表现「只发了文字/什么都没收到」）。

修法：约定一个双方都看得见的目录（bridge 写 PROTO_MEDIA_DIR，协议端在同一份
宿主目录上看到 PROTO_MEDIA_SEEN），发片前把成片拷过去，视频段填协议端视角路径。
同机部署两个变量都留空 = 原行为。只设一半属配置错误，必须显式报错而非猜。
"""
import os

import pytest

from src.plugins.qq_bridge import video_parse as vp


@pytest.fixture
def media_dirs(tmp_path, monkeypatch):
    """bridge 侧可写目录 + 协议端视角前缀，成对注入。"""
    src = tmp_path / "proto-media"
    seen = "/app/data/media"
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_DIR", str(src), raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_SEEN", seen, raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_TTL", 7200, raising=False)
    return src, seen


def test_stages_copy_and_returns_protocol_path(tmp_path, media_dirs):
    src, seen = media_dirs
    local = tmp_path / "BV1xx.mp4"
    local.write_bytes(b"\x00" * 2048)

    got = vp._stage_for_protocol(str(local))

    assert got.startswith(seen + "/"), got
    landed = os.path.join(str(src), os.path.basename(got))
    assert os.path.isfile(landed)
    assert os.path.getsize(landed) == 2048
    # 协议端是另一个容器的另一个用户 → 必须可读
    assert os.stat(landed).st_mode & 0o444


def test_same_host_mode_passes_path_through(tmp_path, monkeypatch):
    """两个变量都留空 = 同机部署（NapCat 时代）：原样返回，不拷贝。"""
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_DIR", "", raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_SEEN", "", raising=False)
    local = tmp_path / "a.mp4"
    local.write_bytes(b"x")

    assert vp._stage_for_protocol(str(local)) == str(local)


def test_half_configured_raises(tmp_path, monkeypatch):
    """只设一半是配置错误：显式 raise，不静默降级成本地路径。"""
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_DIR", str(tmp_path), raising=False)
    monkeypatch.setattr(vp.Config, "VIDEO_PARSE_PROTO_MEDIA_SEEN", "", raising=False)
    local = tmp_path / "a.mp4"
    local.write_bytes(b"x")

    with pytest.raises(RuntimeError, match="必须同时设置"):
        vp._stage_for_protocol(str(local))


def test_sweep_removes_expired_only(tmp_path):
    """落地目录只清过期文件，新片保留。"""
    old = tmp_path / "old.mp4"
    new = tmp_path / "new.mp4"
    old.write_bytes(b"o")
    new.write_bytes(b"n")
    os.utime(old, (0, 0))

    vp._sweep_media(str(tmp_path), ttl=60)

    assert not old.exists()
    assert new.exists()
