"""無損裁切 MP3 前 0.5 秒（500 ms）的 MPEG 音訊幀，保留 ID3 標籤與原始音質／音量。"""
from pathlib import Path

BITRATES_V1_L3 = [0, 32, 40, 48, 56, 64, 80, 96, 112, 128, 160, 192, 224, 256, 320, 0]
BITRATES_V2_L3 = [0, 8, 16, 24, 32, 40, 48, 56, 64, 80, 96, 112, 128, 144, 160, 0]
SAMPLERATES_V1 = [44100, 48000, 32000, 0]
SAMPLERATES_V2 = [22050, 24000, 16000, 0]
SAMPLERATES_V25 = [11025, 12000, 8000, 0]


def parse_id3v2_size(data):
    if len(data) >= 10 and data[:3] == b"ID3":
        s0, s1, s2, s3 = data[6], data[7], data[8], data[9]
        size = ((s0 & 0x7F) << 21) | ((s1 & 0x7F) << 14) | ((s2 & 0x7F) << 7) | (s3 & 0x7F)
        return 10 + size
    return 0


def parse_mp3_frame_header(data, pos):
    if pos + 4 > len(data):
        return None
    b0, b1, b2, b3 = data[pos], data[pos + 1], data[pos + 2], data[pos + 3]
    if b0 != 0xFF or (b1 & 0xE0) != 0xE0:
        return None
    version_id = (b1 >> 3) & 0x03  # 3=MPEG1, 2=MPEG2, 0=MPEG2.5
    layer_id = (b1 >> 1) & 0x03    # 1=Layer III
    if version_id == 1 or layer_id != 1:
        return None
    br_idx = (b2 >> 4) & 0x0F
    sr_idx = (b2 >> 2) & 0x03
    padding = (b2 >> 1) & 0x01
    if br_idx in (0, 15) or sr_idx == 3:
        return None
    if version_id == 3:
        bitrate = BITRATES_V1_L3[br_idx] * 1000
        sr = SAMPLERATES_V1[sr_idx]
        samples_per_frame = 1152
        frame_len = (144 * bitrate) // sr + padding
    else:
        bitrate = BITRATES_V2_L3[br_idx] * 1000
        sr = SAMPLERATES_V2[sr_idx] if version_id == 2 else SAMPLERATES_V25[sr_idx]
        samples_per_frame = 576
        frame_len = (72 * bitrate) // sr + padding
    return frame_len, sr, samples_per_frame, bitrate


def trim_mp3_leading_seconds(mp3_path, trim_sec=0.5):
    path = Path(mp3_path)
    data = path.read_bytes()
    id3_end = parse_id3v2_size(data)
    id3_header = data[:id3_end]

    pos = id3_end
    frames = []
    while pos < len(data) - 4:
        info = parse_mp3_frame_header(data, pos)
        if info is None:
            pos += 1
            continue
        frame_len, sr, spf, br = info
        if pos + frame_len > len(data):
            break
        frames.append((pos, frame_len, sr, spf, br))
        pos += frame_len

    if not frames:
        raise RuntimeError("找不到有效的 MP3 音訊幀")

    # 檢查第一幀是否為 Xing / Info VBR header frame
    first_pos, first_len, sr, spf, br = frames[0]
    first_bytes = data[first_pos:first_pos + first_len]
    has_xing = (b"Xing" in first_bytes or b"Info" in first_bytes)

    audio_frames = frames[1:] if has_xing else frames
    total_dur = sum(f[3] / f[2] for f in audio_frames)
    if abs(total_dur - 3.42) < 0.15:
        print(f"[提示] {path.name} 目前長度為 {total_dur:.2f}s，已經裁切過前 0.5 秒，跳過重複裁切。")
        return

    acc_sec = 0.0
    cut_idx = 0
    for i, (fpos, flen, fsr, fspf, fbr) in enumerate(audio_frames):
        frame_dur = fspf / fsr
        if acc_sec + frame_dur / 2 >= trim_sec:
            cut_idx = i
            break
        acc_sec += frame_dur

    kept_frames = audio_frames[cut_idx:]
    new_dur = sum(f[3] / f[2] for f in kept_frames)
    out_chunks = [id3_header]
    for fpos, flen, _, _, _ in kept_frames:
        out_chunks.append(data[fpos:fpos + flen])

    out_bytes = b"".join(out_chunks)
    path.write_bytes(out_bytes)
    print(
        f"[剪輯完成] {path.name}: 原始音訊長度={total_dur:.2f}s -> "
        f"裁切前 {acc_sec:.3f}s ({cut_idx} 幀) -> 新長度={new_dur:.2f}s ({len(out_bytes)} bytes)"
    )


if __name__ == "__main__":
    target = Path(__file__).resolve().parent.parent / "assets" / "bgm" / "fisherman_sound_2.mp3"
    trim_mp3_leading_seconds(target, trim_sec=0.5)
