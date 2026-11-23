"""背景音樂：循環播放 assets/bgm/<名稱>.ogg/.mp3/.wav。

用法：
    from scenes import music
    music.play("lake")     # 同一首已在播就不會重來
    music.play("none")     # 或 music.stop()：淡出停止

對話 JSON 可在整段或單句加 "bgm": "<名稱>"（"none" = 停止）。
內建曲目由 tools/make_bgm.py 產生；想換成自己的音樂，用同名檔案覆蓋即可。
"""
import pygame

from scenes import sfx

BGM_DIR = sfx.SFX_DIR.parent / "bgm"
VOLUME = 0.2                # 背景音樂預設音量 0~1（音效音量在 sfx.VOLUME；遊戲中可用左上角音量鈕調整）
FADE_IN_MS = 800
FADE_OUT_MS = 600

_current = None
_volume = VOLUME


def _find(name):
    for ext in (".ogg", ".mp3", ".wav"):
        path = BGM_DIR / f"{name}{ext}"
        if path.exists():
            return path
    return None


def play(name, fade_ms=FADE_IN_MS):
    global _current
    if not name:
        return
    if name == "none":
        stop()
        return
    if not sfx._ready():
        return
    if name == _current and pygame.mixer.music.get_busy():
        return
    path = _find(name)
    if path is None:
        print(f"[music] 找不到背景音樂：{BGM_DIR / name}.ogg/.mp3/.wav")
        return
    try:
        pygame.mixer.music.load(str(path))
        pygame.mixer.music.set_volume(_volume)
        pygame.mixer.music.play(loops=-1, fade_ms=fade_ms)
        _current = name
    except pygame.error as e:
        print(f"[music] 無法播放 {path}：{e}")


def set_volume(level):
    """調整背景音樂音量（0~1），正在播的音樂立即改變。"""
    global _volume
    _volume = min(1.0, max(0.0, level))
    if pygame.mixer.get_init():
        pygame.mixer.music.set_volume(_volume)


def stop(fade_ms=FADE_OUT_MS):
    global _current
    _current = None
    if pygame.mixer.get_init():
        pygame.mixer.music.fadeout(fade_ms)
