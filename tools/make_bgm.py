"""產生 8-bit 風格的背景音樂循環檔到 assets/bgm/。

用法（在專案根目錄）：
    python tools/make_bgm.py            # 產生全部
    python tools/make_bgm.py lake lab   # 只產生指定曲目

每首曲子由「和弦進行 + 主旋律 + 低音 + 琶音 + 鼓」組成，都寫在下面的 TRACKS。
想換成真的音樂，直接用同名的 .ogg/.mp3/.wav 覆蓋 assets/bgm/ 裡的檔案即可，程式會自動讀取。
"""
import array
import math
import random
import sys
import wave
from pathlib import Path

OUT_DIR = Path(__file__).resolve().parent.parent / "assets" / "bgm"
SR = 22050                      # 取樣率（8-bit 風格不需要太高）
STEPS_PER_BAR = 16              # 以十六分音符為最小單位

NOTE_INDEX = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}
CHORD_SHAPES = {"": (0, 4, 7), "m": (0, 3, 7), "7": (0, 4, 7, 10), "dim": (0, 3, 6)}


def _midi(name):
    """'C#5' / 'Bb4' / 'E5' → MIDI 編號。"""
    semi = NOTE_INDEX[name[0]]
    rest = name[1:]
    if rest and rest[0] in "#b":
        semi += 1 if rest[0] == "#" else -1
        rest = rest[1:]
    return 12 * (int(rest) + 1) + semi


def _freq(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def _chord(sym):
    """'Am' → (根音 0~11, 音程 tuple)。"""
    root = NOTE_INDEX[sym[0]]
    q = sym[1:]
    if q and q[0] in "#b":
        root += 1 if q[0] == "#" else -1
        q = q[1:]
    return root % 12, CHORD_SHAPES[q]


# ---------------- 曲目 ----------------
# melody：以八分音符為單位，"E5*2" = 兩個八分音符長，"r" = 休止
# bass：root8（每八分音符根音）/ quarter（每拍根音）/ half（二分音符根音+五度）/ fifth（根音五度交替）
# arp：None / "up"（和弦分解）
# drums：每小節 16 格，k=大鼓 s=小鼓 h=鈸 .=空
TRACKS = {
    # 校園日常：輕快
    "campus": dict(
        bpm=120, lead="pulse", chords="C G Am F C F G C",
        melody="""E5 G5 C6*2 G5 E5 G5*2 | D5 G5 B5*2 A5 G5 D5*2 | C5 E5 A5*2 G5 E5 C5*2 |
                  F5*2 A5 G5 F5 E5 D5*2 | E5 G5 C6*2 D6 C6 G5*2 | A5*2 C6 A5 G5 F5 A5*2 |
                  G5 F5 E5 D5 B4*2 D5*2 | C5*4 r*4""",
        bass="fifth", arp="up", drums="k.h.s.h.k.h.s.h."),
    # 校長室：正經又有點滑稽
    "office": dict(
        bpm=100, lead="square", chords="Dm Bb C F Dm Gm A Dm",
        melody="""D5 r F5 r A5 r F5 r | D5 r F5 r Bb5*2 A5 G5 | E5 r G5 r C6*2 Bb5 A5 |
                  A5*3 G5 F5*2 r*2 | F5 r A5 r D6 r A5 r | G5 r Bb5 r D6*2 C6 Bb5 |
                  A5 C#6 E6 C#6 A5*2 G5 E5 | D5*4 r*4""",
        bass="quarter", arp=None, drums="k.......s......."),
    # 飛船墜落：緊急
    "panic": dict(
        bpm=150, lead="pulse", chords="Am Am F G Am Am F E",
        melody="""A5 A5 C6 A5 E6 A5 C6 A5 | A5 A5 C6 A5 G6 E6 D6 C6 | C6 A5 F5 A5 C6 F6 E6 C6 |
                  B5 G5 D5 G5 B5 D6 B5 G5 | A5 A5 C6 A5 E6 A5 C6 A5 | A5 A5 C6 A5 G6 E6 D6 C6 |
                  F6 E6 D6 C6 D6 C6 B5 A5 | G#5*2 B5*2 E6*4""",
        bass="root8", arp=None, drums="k.h.s.h.k.k.s.h."),
    # 限時解謎：緊張
    "tension": dict(
        bpm=132, lead="pulse", chords="Dm Dm Bb A Dm Dm Bb A",
        melody="""D5 F5 A5 F5 D5 F5 A5 F5 | D5 F5 Bb5 F5 D5 F5 A5 F5 | D5 F5 Bb5 D6 Bb5 F5 D5 F5 |
                  C#5 E5 A5 E5 C#5 E5 G5 E5 | D5 F5 A5 F5 D5 F5 A5 F5 | D5 F5 Bb5 F5 D5 F5 A5 F5 |
                  D5 F5 Bb5 D6 Bb5 F5 D5 F5 | E5 A5 C#6 E6 C#6 A5 E5 C#5""",
        bass="root8", arp=None, drums="k.h.h.h.k.hkh.h.", lead_vol=0.16),
    # 成功湖釣魚：悠閒
    "lake": dict(
        bpm=88, lead="triangle", chords="F C Dm Bb F C Bb C",
        melody="""A5*3 G5 F5*2 C5*2 | E5*3 F5 G5*4 | F5*3 E5 D5*2 A4*2 | D5*3 C5 Bb4*2 D5*2 |
                  A5*2 C6*2 Bb5 A5 G5 F5 | G5*6 E5*2 | F5*2 D5*2 F5 G5 A5*2 | G5*8""",
        bass="half", arp="up", drums="........h.......", lead_vol=0.3),
    # 化學館：神祕
    "lab": dict(
        bpm=96, lead="triangle", chords="Em C Am B Em C Am B",
        melody="""E5*2 r G5 B5*2 r*2 | C6*3 B5 G5*2 r*2 | A5*2 r C6 E6*2 D6 C6 | B5*4 D#6*2 B5*2 |
                  G5*2 r B5 E6*2 r*2 | E6*3 D6 C6*2 B5*2 | A5*2 C6*2 B5*2 A5*2 | F#5*4 D#5*4""",
        bass="half", arp="up", drums="k.......h.......", lead_vol=0.28),
    # 反派得意：進行曲
    "villain": dict(
        bpm=112, lead="square", chords="Cm Cm Ab G Cm Cm Ab G",
        melody="""C5*2 C5 C5 Eb5*2 G5*2 | C6*3 Bb5 G5*2 Eb5*2 | Ab5*2 G5 F5 Eb5*2 C5*2 |
                  D5*2 F5 Eb5 D5*2 B4*2 | C5*2 C5 C5 Eb5*2 G5*2 | Eb6*3 D6 C6*2 G5*2 |
                  Ab5*2 C6*2 Eb6*2 D6 C6 | B5*4 G5*4""",
        bass="root8", arp=None, drums="k.s.k.s.k.s.ksss"),
}


# ---------------- 合成 ----------------
def _osc(wave_name, phase):
    if wave_name == "pulse":                       # 25% 方波：經典 8-bit 主旋律
        return 1.0 if phase < 0.25 else -1.0
    if wave_name == "square":
        return 1.0 if phase < 0.5 else -1.0
    if wave_name == "triangle":
        return 4 * phase - 1 if phase < 0.5 else 3 - 4 * phase
    return math.sin(2 * math.pi * phase)


def _add_note(buf, start, length, freq, wave_name, vol):
    """把一個音加進 buf（float list）。含短 attack 與尾端 release，音與音之間留一點空隙。"""
    n = int(length * 0.9)
    attack = max(1, int(SR * 0.004))
    release = max(1, int(n * 0.25))
    step = freq / SR
    phase = 0.0
    end = min(len(buf), start + n)
    for i in range(start, end):
        k = i - start
        env = min(1.0, k / attack, (n - k) / release)
        buf[i] += _osc(wave_name, phase) * vol * env
        phase += step
        if phase >= 1.0:
            phase -= 1.0


def _add_drum(buf, start, kind, vol):
    rnd = random.Random(start)                     # 固定種子：每次產生結果一樣
    if kind == "k":                                # 大鼓：快速下滑的正弦波
        n = int(SR * 0.12)
        phase = 0.0
        for k in range(min(n, len(buf) - start)):
            t = k / n
            phase += (150 - 100 * t) / SR
            buf[start + k] += math.sin(2 * math.pi * phase) * vol * 1.6 * (1 - t)
    else:                                          # 小鼓 / 鈸：雜訊
        n = int(SR * (0.11 if kind == "s" else 0.03))
        hold = 3 if kind == "s" else 1
        v = 0.0
        for k in range(min(n, len(buf) - start)):
            if k % hold == 0:
                v = rnd.uniform(-1, 1)
            buf[start + k] += v * vol * (1.0 if kind == "s" else 0.5) * (1 - k / n)


def render(name, spec):
    chords = spec["chords"].split()
    bars = len(chords)
    step_len = SR * 60 / spec["bpm"] / 4             # 一個十六分音符的取樣數
    total = int(round(bars * STEPS_PER_BAR * step_len))
    buf = [0.0] * total

    def at(step):
        return int(round(step * step_len))

    # 主旋律
    step = 0
    for bar_i, bar in enumerate(spec["melody"].split("|")):
        bar_steps = 0
        for tok in bar.split():
            note, _, mul = tok.partition("*")
            steps = 2 * int(mul or 1)
            if note != "r":
                _add_note(buf, at(step), at(step + steps) - at(step), _freq(_midi(note)),
                          spec["lead"], spec.get("lead_vol", 0.2))
            step += steps
            bar_steps += steps
        if bar_steps != STEPS_PER_BAR:
            raise ValueError(f"{name} 第 {bar_i + 1} 小節長度是 {bar_steps // 2} 個八分音符，應為 8")

    # 低音、琶音、鼓
    for b, sym in enumerate(chords):
        root, shape = _chord(sym)
        base = b * STEPS_PER_BAR
        bass_root = 36 + root                        # C2 起算
        style = spec["bass"]
        if style == "root8":
            hits = [(s, 2, bass_root) for s in range(0, 16, 2)]
        elif style == "quarter":
            hits = [(s, 2, bass_root) for s in range(0, 16, 4)]
        elif style == "fifth":
            hits = [(s, 4, bass_root + (7 if (s // 4) % 2 else 0)) for s in range(0, 16, 4)]
        else:  # half
            hits = [(0, 8, bass_root), (8, 8, bass_root + 7)]
        for s, d, m in hits:
            _add_note(buf, at(base + s), at(base + s + d) - at(base + s), _freq(m), "triangle", 0.32)

        if spec.get("arp") == "up":
            tones = [60 + root + iv for iv in shape[:3]] + [72 + root]
            seq = tones + tones[-2:0:-1] + tones[:2]   # 1 3 5 8 5 3 1 3 → 八個八分音符
            for k, m in enumerate(seq[:8]):
                s = base + 2 * k
                _add_note(buf, at(s), at(s + 2) - at(s), _freq(m), "square", 0.06)

        for s, ch in enumerate(spec["drums"]):
            if ch in "ksh":
                _add_drum(buf, at(base + s), ch, 0.18)

    # 正規化並轉 16-bit
    peak = max(1e-9, max(abs(x) for x in buf))
    gain = 0.85 / peak
    return array.array("h", (int(x * gain * 32767) for x in buf))


def main():
    names = sys.argv[1:] or list(TRACKS)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name in names:
        pcm = render(name, TRACKS[name])
        path = OUT_DIR / f"{name}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(SR)
            w.writeframes(pcm.tobytes())
        print(f"{path.name}: {len(pcm) / SR:.1f} 秒")


if __name__ == "__main__":
    main()
