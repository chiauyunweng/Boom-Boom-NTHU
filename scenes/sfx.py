"""音效：優先播放 assets/sfx/<名稱>.wav/.ogg/.mp3，沒有檔案時用程式合成的 8-bit 音效代替。

用法：
    from scenes import sfx
    sfx.play("pickup")

可用名稱見 SYNTH。想換成自己的音效，只要把檔案放到 assets/sfx/ 並取同樣的名字（例如 wrong.wav）。
"""
import array
import math
import random
from pathlib import Path

import pygame

SFX_DIR = Path(__file__).resolve().parent.parent / "assets" / "sfx"
VOLUME = 0.5                  # 全部音效的總音量 0~1

# 合成音效：每段為 (波形, 起始頻率, 結束頻率, 長度 ms, 音量)；波形 square / sine / noise / rest
# noise 的頻率代表雜訊取樣率（低 = 低沉轟隆，高 = 沙沙聲；0 = 預設 8000），且音量會漸弱
SYNTH = {
    # --- 通用 ---
    "advance": [("square", 880, 880, 25, 0.14), ("square", 1320, 1320, 35, 0.12)],  # 對話點擊/換句
    "paper":   [("noise", 0, 0, 130, 0.18)],                              # 紙張、說明書
    "success": [("square", 523, 523, 90, 0.25), ("square", 659, 659, 90, 0.25),
                ("square", 784, 784, 90, 0.25), ("square", 1047, 1047, 300, 0.25)],  # 成功
    "fail_jingle": [("square", 392, 392, 180, 0.22), ("square", 370, 370, 180, 0.22),
                    ("square", 349, 349, 180, 0.22), ("square", 330, 290, 650, 0.22)],  # 失敗
    "buzz":    [("square", 150, 150, 250, 0.22)],                         # 答錯
    # --- 劇情 ---
    "explosion": [("noise", 4000, 150, 1500, 0.6)],                       # 爆炸、劇烈震動
    "siren":   [("sine", 650, 950, 450, 0.25), ("sine", 950, 650, 450, 0.25)] * 2,  # 消防車/警車
    "door":    [("square", 140, 220, 300, 0.1), ("noise", 900, 300, 150, 0.35)],  # 開門
    "footsteps": [("noise", 1200, 600, 50, 0.3), ("rest", 0, 0, 220, 0)] * 4,  # 腳步聲
    "bark":    [("square", 700, 350, 90, 0.25), ("rest", 0, 0, 70, 0),
                ("square", 750, 380, 110, 0.25)],                         # 狗叫
    "sparkle": [("sine", f, f, 45, 0.18) for f in (2093, 2637, 3136, 2637, 3520, 4186)],  # 閃光
    "whistle": [("sine", 2100, 2300, 50, 0.2), ("sine", 2300, 2100, 50, 0.2)] * 6,  # 警哨
    "machine": [("square", 70, 70, 350, 0.18), ("square", 1200, 1200, 60, 0.15),
                ("rest", 0, 0, 60, 0), ("square", 1600, 1600, 80, 0.15)],  # 實驗裝置
    # --- 釣魚 ---
    "cast":    [("noise", 1500, 7000, 220, 0.18), ("noise", 5000, 1200, 280, 0.25)],  # 甩竿入水
    "reel":    [("square", 1100, 1100, 12, 0.12), ("rest", 0, 0, 48, 0)] * 10,  # 收線
    "catch":   [("square", 784, 784, 80, 0.22), ("square", 988, 988, 80, 0.22),
                ("square", 1175, 1175, 80, 0.22), ("square", 1568, 1568, 320, 0.22)],  # 釣到東西
    "miss":    [("noise", 4000, 1000, 200, 0.2), ("square", 392, 196, 400, 0.18)],  # 沒釣到
    # --- 化學館 ---
    "pickup":  [("square", 660, 990, 60, 0.25)],                          # 拿起物品
    "cancel":  [("sine", 440, 300, 90, 0.35)],                            # 沒放進裝置、物品退回
    "drop":    [("square", 988, 988, 60, 0.25), ("square", 1319, 1319, 110, 0.25)],  # 放對
    "alarm":   [("square", 600, 1100, 400, 0.22), ("square", 1100, 600, 400, 0.22)] * 3,  # 警報聲（放錯）
    "tick":    [("square", 1200, 1200, 35, 0.15)],                        # 最後 10 秒倒數
    "timeout": [("square", 440, 110, 700, 0.3)],                          # 時間到
}

_cache = {}
_disabled = False


def _ready():
    """確認 mixer 可用；沒有音效裝置時安靜地停用音效。"""
    global _disabled
    if _disabled:
        return False
    if not pygame.mixer.get_init():
        try:
            pygame.mixer.init()
        except pygame.error as e:
            print(f"[sfx] 無法初始化音效，將不播放音效：{e}")
            _disabled = True
            return False
    return True


def _synth(segments):
    freq, fmt, channels = pygame.mixer.get_init()
    if fmt not in (-16, 16):     # 只合成 16-bit；其他格式就不播
        return None
    buf = array.array("h")
    phase = 0.0
    for wave, f0, f1, ms, vol in segments:
        n = max(1, int(freq * ms / 1000))
        attack = max(1, int(freq * 0.005))
        release = max(1, int(n * 0.3))
        noise_val, noise_acc = 0.0, 1.0
        for i in range(n):
            t = i / n
            f = f0 + (f1 - f0) * t
            phase = (phase + f / freq) % 1.0
            if wave == "square":
                v = 1.0 if phase < 0.5 else -1.0
            elif wave == "sine":
                v = math.sin(2 * math.pi * phase)
            elif wave == "noise":
                noise_acc += (f or 8000) / freq          # 降低取樣率讓雜訊更有 8-bit 顆粒感
                if noise_acc >= 1.0:
                    noise_acc -= 1.0
                    noise_val = random.uniform(-1, 1)
                v = noise_val * (1 - t)                 # 雜訊漸弱
            else:
                v = 0.0
            env = min(1.0, i / attack, (n - i) / release)
            s = int(32767 * VOLUME * vol * env * v)
            buf.extend([s] * channels)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _load(name):
    for ext in (".wav", ".ogg", ".mp3"):
        path = SFX_DIR / f"{name}{ext}"
        if path.exists():
            try:
                snd = pygame.mixer.Sound(str(path))
                snd.set_volume(VOLUME)
                return snd
            except pygame.error as e:
                print(f"[sfx] 讀不到 {path}：{e}")
    if name in SYNTH:
        return _synth(SYNTH[name])
    print(f"[sfx] 沒有這個音效：{name}")
    return None


def play(name):
    """播放音效；同一個音效若還在播，先停掉再重播（避免重疊）。"""
    if not _ready():
        return
    if name not in _cache:
        _cache[name] = _load(name)
    if _cache[name]:
        _cache[name].stop()
        _cache[name].play()


def stop(name):
    snd = _cache.get(name)
    if snd and pygame.mixer.get_init():
        snd.stop()


def preload():
    """遊戲開始時先把所有音效準備好，避免第一次播放時卡頓。"""
    if not _ready():
        return
    for name in SYNTH:
        if name not in _cache:
            _cache[name] = _load(name)
