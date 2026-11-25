"""合成 Steam 風格成就解鎖提示音（清脆、有空間感的雙音階和弦短音效）。

輸出：assets/bgm/achievement_unlock.wav（44100 Hz, 16-bit 立體聲 PCM）
用法：python tools/make_achievement_sfx.py
"""
import array
import math
from pathlib import Path
import wave

SAMPLE_RATE = 44100
DURATION_SEC = 1.65


def _bell_tone(t, freq, decay):
    """清脆玻璃鐘／電鋼琴感音色：基頻 + 泛音 + 細微雙聲部微失諧。"""
    if t < 0:
        return 0.0
    attack = min(1.0, t / 0.004)
    env = attack * math.exp(-t * decay)
    # 基頻 + 微失諧（增加空間感）+ 八度泛音 + 柔和三倍泛音
    sig = (
        0.58 * math.sin(2.0 * math.pi * freq * t)
        + 0.22 * math.sin(2.0 * math.pi * (freq * 1.0025) * t)
        + 0.14 * math.sin(2.0 * math.pi * (freq * 2.0) * t) * math.exp(-t * 2.5)
        + 0.06 * math.sin(2.0 * math.pi * (freq * 3.0) * t) * math.exp(-t * 5.0)
    )
    return env * sig


def synthesize_steam_chime():
    """產生 Steam 風格雙音階和弦音效，回傳 (left_samples, right_samples)。"""
    n = int(SAMPLE_RATE * DURATION_SEC)
    dry_l = [0.0] * n
    dry_r = [0.0] * n

    # 兩段上行清脆和弦（類似 Steam 成就彈窗的「叮—咚！」明亮解決感）
    # 第一拍（t=0.00s）：E5 + B5（清脆起音）
    # 第二拍（t=0.115s）：G#5 + B5 + E6 + F#6（明亮的大九和弦尾韻）
    notes = [
        # (start_sec, freq_hz, gain, decay, pan [-1..1])
        (0.000, 659.25, 0.42, 5.2, -0.20),   # E5
        (0.000, 987.77, 0.30, 5.8,  0.20),   # B5
        (0.115, 830.61, 0.36, 2.7, -0.25),   # G#5
        (0.115, 987.77, 0.28, 2.6,  0.10),   # B5
        (0.120, 1318.51, 0.44, 2.2,  0.22),  # E6（主旋律亮點）
        (0.128, 1479.98, 0.16, 3.0, -0.15),  # F#6（些微空間點綴）
    ]

    for start, freq, gain, decay, pan in notes:
        start_idx = int(start * SAMPLE_RATE)
        l_gain = gain * math.cos((pan + 1.0) * math.pi / 4.0)
        r_gain = gain * math.sin((pan + 1.0) * math.pi / 4.0)
        for i in range(start_idx, n):
            t = (i - start_idx) / SAMPLE_RATE
            val = _bell_tone(t, freq, decay)
            dry_l[i] += val * l_gain
            dry_r[i] += val * r_gain

    # 加入立體聲多階回聲（Reverb / Shimmer 空間感）
    wet_l = list(dry_l)
    wet_r = list(dry_r)
    taps = [
        # (delay_ms, gain_l, gain_r)
        (42,  0.24, 0.14),
        (78,  0.12, 0.22),
        (125, 0.16, 0.10),
        (185, 0.08, 0.14),
        (260, 0.09, 0.07),
        (350, 0.05, 0.06),
    ]
    for delay_ms, gl, gr in taps:
        d = int(SAMPLE_RATE * delay_ms / 1000.0)
        for i in range(d, n):
            wet_l[i] += dry_r[i - d] * gl
            wet_r[i] += dry_l[i - d] * gr

    # 結尾淡出避免喀噠聲
    fade_samples = int(SAMPLE_RATE * 0.08)
    for i in range(fade_samples):
        k = i / fade_samples
        wet_l[n - 1 - i] *= k
        wet_r[n - 1 - i] *= k

    # 正規化至 0.92 峰值
    peak = max(max(abs(x) for x in wet_l), max(abs(x) for x in wet_r), 1e-6)
    scale = 0.92 / peak
    out = array.array("h")
    for l_val, r_val in zip(wet_l, wet_r):
        out.append(max(-32767, min(32767, int(l_val * scale * 32767))))
        out.append(max(-32767, min(32767, int(r_val * scale * 32767))))
    return out


def main():
    out_path = Path(__file__).resolve().parent.parent / "assets" / "bgm" / "achievement_unlock.wav"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    pcm = synthesize_steam_chime()
    with wave.open(str(out_path), "wb") as wf:
        wf.setnchannels(2)
        wf.setsampwidth(2)
        wf.setframerate(SAMPLE_RATE)
        wf.writeframes(pcm.tobytes())
    print(f"[make_achievement_sfx] 已產生 {out_path} ({DURATION_SEC:.2f}s, {out_path.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
