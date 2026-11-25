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
BGM_DIR = Path(__file__).resolve().parent.parent / "assets" / "bgm"
ASSET_ROOT = Path(__file__).resolve().parent.parent / "assets"
FISHERMAN_SOUNDS = [f"fisherman_sound_{i}" for i in range(1, 5)]
FISHERMAN_VOLUME = 1.0        # 漁夫語音音量固定為 1.0（最大音量，為 BGM 0.1 的 10 倍大聲）
FISHERMAN_BGM_DUCK_VOLUME = 0.1   # 播放漁夫語音時，確保 BGM 壓在 <= 0.1（10 倍音量比）
ACHIEVEMENT_SOUND_NAME = "achievement_unlock"
VOLUME = 0.5                  # 全部音效的預設總音量 0~1（遊戲中可用左上角音量鈕調整）

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
_volume = VOLUME


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
            s = int(32767 * vol * env * v)          # 總音量用 Sound.set_volume 控制，可即時調整
            buf.extend([s] * channels)
    return pygame.mixer.Sound(buffer=buf.tobytes())


def _load(name):
    for ext in (".wav", ".ogg", ".mp3"):
        path = SFX_DIR / f"{name}{ext}"
        if path.exists():
            try:
                return pygame.mixer.Sound(str(path))
            except pygame.error as e:
                print(f"[sfx] 讀不到 {path}：{e}")
    if name in SYNTH:
        return _synth(SYNTH[name])
    print(f"[sfx] 沒有這個音效：{name}")
    return None


def _get(name):
    if name not in _cache:
        _cache[name] = _load(name)
        if _cache[name]:
            _cache[name].set_volume(_volume)
    return _cache[name]


def set_volume(level):
    """調整全部音效的總音量（0~1），正在播的也會立即改變；漁夫語音維持最大音量 1.0。"""
    global _volume
    _volume = min(1.0, max(0.0, level))
    for name, snd in _cache.items():
        if snd:
            snd.set_volume(FISHERMAN_VOLUME if name in FISHERMAN_SOUNDS else _volume)


def play(name):
    """播放音效；同一個音效若還在播，先停掉再重播（避免重疊）。"""
    if not _ready():
        return
    snd = _get(name)
    if snd:
        snd.stop()
        snd.play()


def stop(name):
    snd = _cache.get(name)
    if snd and pygame.mixer.get_init():
        snd.stop()


_fisherman_paths = {}
_fisherman_channel = None


def _load_fisherman_sounds():
    """預載 bgm/fisherman_sound_1.mp3 ~ bgm/fisherman_sound_4.mp3，加上檔案不存在防呆處理、音量設定與 Debug 訊息。"""
    if not _ready():
        print("[DEBUG][Fisherman Sound][ERROR] pygame.mixer 未初始化或音效停用，無法載入漁夫語音")
        return []
    loaded = []
    newly_loaded = []
    for name in FISHERMAN_SOUNDS:
        if name in _cache:
            if _cache[name] is not None:
                loaded.append((name, _cache[name]))
            continue
        snd = None
        found_path = None
        for directory in (BGM_DIR, SFX_DIR, ASSET_ROOT):
            for ext in (".mp3", ".wav", ".ogg"):
                path = directory / f"{name}{ext}"
                if path.exists():
                    found_path = path
                    try:
                        snd = pygame.mixer.Sound(str(path))
                        snd.set_volume(FISHERMAN_VOLUME)
                        _fisherman_paths[name] = path
                        newly_loaded.append(path)
                    except pygame.error as e:
                        print(f"[DEBUG][Fisherman Sound][ERROR] 載入失敗 {path}：{e}")
                        snd = None
                    break
            if snd is not None:
                break
        if snd is None and found_path is None:
            print(f"[DEBUG][Fisherman Sound][WARN] 找不到音檔：{name}.mp3（已搜尋 {BGM_DIR}、{SFX_DIR}、{ASSET_ROOT}）")
        _cache[name] = snd
        if snd is not None:
            loaded.append((name, snd))
    if newly_loaded:
        paths_str = ", ".join(str(p) for p in newly_loaded)
        print(f"[DEBUG][Fisherman Sound] 成功載入 {len(loaded)}/{len(FISHERMAN_SOUNDS)} 個漁夫語音檔 | 路徑: {paths_str}")
    return loaded


def stop_fisherman_sound():
    """立即停止所有正在播放中的漁夫語音（以及專屬 Channel），避免語音殘留到結算／過關／失敗對話中。"""
    global _fisherman_channel
    if not pygame.mixer.get_init():
        return
    if _fisherman_channel is not None:
        try:
            _fisherman_channel.stop()
        except pygame.error:
            pass
        _fisherman_channel = None
    for name in FISHERMAN_SOUNDS:
        snd = _cache.get(name)
        if snd is not None:
            snd.stop()


def play_fisherman_sound(index=3, source="未指定來源"):
    """播放指定編號（1~4）的漁夫語音（例如釣魚關卡固定播放 fisherman_sound_3.mp3）。"""
    global _fisherman_channel
    if not _ready():
        print(f"[DEBUG][Fisherman Sound][ERROR] 觸發來源: {source} | 播放失敗: pygame.mixer 未就緒")
        return
    _load_fisherman_sounds()
    target_name = f"fisherman_sound_{index}" if isinstance(index, int) else Path(str(index)).stem
    target_snd = _cache.get(target_name)
    if target_snd is None:
        print(f"[DEBUG][Fisherman Sound][ERROR] 觸發來源: {source} | 播放失敗: 找不到指定音檔 {target_name}.mp3")
        return
    stop_fisherman_sound()
    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
        cur_bgm_vol = pygame.mixer.music.get_volume()
        if cur_bgm_vol > FISHERMAN_BGM_DUCK_VOLUME:
            pygame.mixer.music.set_volume(FISHERMAN_BGM_DUCK_VOLUME)
    bgm_vol = round(pygame.mixer.music.get_volume(), 2) if pygame.mixer.get_init() else 0.1
    target_snd.set_volume(FISHERMAN_VOLUME)
    vol = round(target_snd.get_volume(), 2)
    file_path = _fisherman_paths.get(target_name)
    file_label = file_path.name if file_path else f"{target_name}.mp3"
    _fisherman_channel = target_snd.play()
    if _fisherman_channel is None:
        print(f"[DEBUG][Fisherman Sound][ERROR] 觸發來源: {source} | 音檔: {file_label} | 播放失敗: 無可用混音聲道 (channel is None)")
    else:
        print(f"[DEBUG][Fisherman Sound] 觸發來源: {source} | 固定播放音檔: {file_label} | 語音音量: {vol} (BGM音量: {bgm_vol}, 10x比例)")


def play_random_fisherman_sound(source="未指定來源"):
    """隨機挑選 fisherman_sound_1 ~ 4 之一播放；播放前先停止尚未播完的漁夫語音，並印出詳細 Debug 訊息。"""
    global _fisherman_channel
    if not _ready():
        print(f"[DEBUG][Fisherman Sound][ERROR] 觸發來源: {source} | 播放失敗: pygame.mixer 未就緒")
        return
    sounds = _load_fisherman_sounds()
    if not sounds:
        print(f"[DEBUG][Fisherman Sound][ERROR] 觸發來源: {source} | 播放失敗: 無可用的漁夫語音檔")
        return
    stop_fisherman_sound()
    # 確保播放漁夫語音時，BGM 維持在 0.1（與語音 1.0 呈 10 倍音量比例）
    if pygame.mixer.get_init() and pygame.mixer.music.get_busy():
        cur_bgm_vol = pygame.mixer.music.get_volume()
        if cur_bgm_vol > FISHERMAN_BGM_DUCK_VOLUME:
            pygame.mixer.music.set_volume(FISHERMAN_BGM_DUCK_VOLUME)
    bgm_vol = round(pygame.mixer.music.get_volume(), 2) if pygame.mixer.get_init() else 0.1
    chosen_name, chosen_snd = random.choice(sounds)
    chosen_snd.set_volume(FISHERMAN_VOLUME)
    vol = round(chosen_snd.get_volume(), 2)
    file_path = _fisherman_paths.get(chosen_name)
    file_label = file_path.name if file_path else f"{chosen_name}.mp3"
    _fisherman_channel = chosen_snd.play()
    if _fisherman_channel is None:
        print(f"[DEBUG][Fisherman Sound][ERROR] 觸發來源: {source} | 音檔: {file_label} | 播放失敗: 無可用混音聲道 (channel is None)")
    else:
        print(f"[DEBUG][Fisherman Sound] 觸發來源: {source} | 隨機播放音檔: {file_label} | 語音音量: {vol} (BGM音量: {bgm_vol}, 10x比例)")


def _load_achievement_sound():
    """預載成就解鎖音效（優先搜尋 assets/bgm/achievement_unlock.wav，其次 assets/sfx/）。"""
    if not _ready():
        return None
    if ACHIEVEMENT_SOUND_NAME in _cache:
        return _cache[ACHIEVEMENT_SOUND_NAME]
    snd = None
    for directory in (BGM_DIR, SFX_DIR, ASSET_ROOT):
        for ext in (".wav", ".ogg", ".mp3"):
            path = directory / f"{ACHIEVEMENT_SOUND_NAME}{ext}"
            if path.exists():
                try:
                    snd = pygame.mixer.Sound(str(path))
                    snd.set_volume(max(_volume, 0.85))
                except pygame.error as e:
                    print(f"[sfx] 載入成就音效失敗 {path}：{e}")
                    snd = None
                break
        if snd is not None:
            break
    if snd is None:
        # 備援：若音檔遺失則回退使用內建成功音效
        snd = _get("success")
    _cache[ACHIEVEMENT_SOUND_NAME] = snd
    return snd


def play_achievement_sound():
    """播放 Steam 風格成就解鎖音效。"""
    if not _ready():
        return
    snd = _load_achievement_sound()
    if snd is not None:
        snd.set_volume(max(_volume, 0.85) if _volume > 0 else 0.0)
        snd.stop()
        snd.play()


def preload():
    """遊戲開始時先把所有音效準備好，避免第一次播放時卡頓。"""
    if not _ready():
        return
    for name in SYNTH:
        _get(name)
    _load_fisherman_sounds()
    _load_achievement_sound()
