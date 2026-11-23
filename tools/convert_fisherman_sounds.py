"""使用 Windows 內建 Media Foundation API 將 M4A 轉為 16-bit PCM WAV，並做 +18dB 音量放大與軟限幅。"""
import array
import ctypes
from ctypes import POINTER, Structure, byref, c_int32, c_uint8, c_uint32, c_uint64, c_void_p, c_wchar_p
import math
from pathlib import Path
import shutil
import wave


class GUID(Structure):
    _fields_ = [
        ("Data1", c_uint32),
        ("Data2", ctypes.c_uint16),
        ("Data3", ctypes.c_uint16),
        ("Data4", c_uint8 * 8),
    ]

    @classmethod
    def from_str(cls, s):
        import uuid
        u = uuid.UUID(s)
        b = u.bytes_le
        g = cls()
        ctypes.memmove(byref(g), b, 16)
        return g


MF_VERSION = 0x00020070
MF_SOURCE_READER_FIRST_AUDIO_STREAM = c_uint32(0xFFFFFFFD)

MFMediaType_Audio = GUID.from_str("73647561-0000-0010-8000-00AA00389B71")
MFAudioFormat_PCM = GUID.from_str("00000001-0000-0010-8000-00AA00389B71")
MF_MT_MAJOR_TYPE = GUID.from_str("48eba18e-f8c9-4687-bf11-0a74c9f96a8f")
MF_MT_SUBTYPE = GUID.from_str("f7e34c9a-42e8-4714-b74b-cb29d72c35e5")
MF_MT_AUDIO_BITS_PER_SAMPLE = GUID.from_str("f2deb57f-40fa-4764-aa33-ed4f2d1ff669")
MF_MT_AUDIO_SAMPLES_PER_SECOND = GUID.from_str("5faeeae7-0290-4c31-9e8a-c534f68d9dba")
MF_MT_AUDIO_NUM_CHANNELS = GUID.from_str("37e48bf5-645e-4c5b-89de-ada9e29b696a")

ole32 = ctypes.windll.ole32
mfplat = ctypes.windll.mfplat
mfreadwrite = ctypes.windll.mfreadwrite

ole32.CoInitializeEx(None, 0)
mfplat.MFStartup(MF_VERSION, 0)


def _vcall(obj_ptr, vtable_index, restype, *argtypes):
    vtable = ctypes.cast(obj_ptr, POINTER(POINTER(c_void_p))).contents
    fn_addr = vtable[vtable_index]
    proto = ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)
    return proto(fn_addr)


def decode_m4a_to_pcm(src_path):
    """回傳 (sample_rate, channels, pcm_bytes_16bit)。"""
    # Media Foundation 需要有 .m4a 副檔名才能自動辨識容器
    tmp_path = None
    src = Path(src_path)
    if src.suffix.lower() != ".m4a":
        tmp_path = src.with_suffix(".tmp_decode.m4a")
        shutil.copy2(src, tmp_path)
        read_target = str(tmp_path)
    else:
        read_target = str(src)

    try:
        reader = c_void_p()
        hr = mfreadwrite.MFCreateSourceReaderFromURL(
            c_wchar_p(read_target), None, byref(reader)
        )
        if hr != 0:
            raise RuntimeError(f"MFCreateSourceReaderFromURL failed: 0x{hr & 0xFFFFFFFF:08X}")

        media_type = c_void_p()
        hr = mfplat.MFCreateMediaType(byref(media_type))
        if hr != 0:
            raise RuntimeError(f"MFCreateMediaType failed: 0x{hr & 0xFFFFFFFF:08X}")

        # IMFAttributes::SetGUID is vtable index 24; SetUINT32 is vtable index 21; GetUINT32 is index 12
        SetGUID = _vcall(media_type, 24, c_int32, POINTER(GUID), POINTER(GUID))
        SetUINT32 = _vcall(media_type, 21, c_int32, POINTER(GUID), c_uint32)

        SetGUID(media_type, byref(MF_MT_MAJOR_TYPE), byref(MFMediaType_Audio))
        SetGUID(media_type, byref(MF_MT_SUBTYPE), byref(MFAudioFormat_PCM))
        SetUINT32(media_type, byref(MF_MT_AUDIO_BITS_PER_SAMPLE), 16)

        # IMFSourceReader::SetCurrentMediaType is vtable index 7
        SetCurrentMediaType = _vcall(reader, 7, c_int32, c_uint32, c_void_p, c_void_p)
        hr = SetCurrentMediaType(reader, MF_SOURCE_READER_FIRST_AUDIO_STREAM, None, media_type)
        if hr != 0:
            raise RuntimeError(f"SetCurrentMediaType failed: 0x{hr & 0xFFFFFFFF:08X}")

        # IMFSourceReader::GetCurrentMediaType is vtable index 6
        out_type = c_void_p()
        GetCurrentMediaType = _vcall(reader, 6, c_int32, c_uint32, POINTER(c_void_p))
        hr = GetCurrentMediaType(reader, MF_SOURCE_READER_FIRST_AUDIO_STREAM, byref(out_type))
        if hr != 0:
            raise RuntimeError(f"GetCurrentMediaType failed: 0x{hr & 0xFFFFFFFF:08X}")

        # IMFAttributes::GetUINT32 is vtable index 11
        GetUINT32 = _vcall(out_type, 11, c_int32, POINTER(GUID), POINTER(c_uint32))
        channels = c_uint32(1)
        sample_rate = c_uint32(48000)
        GetUINT32(out_type, byref(MF_MT_AUDIO_NUM_CHANNELS), byref(channels))
        GetUINT32(out_type, byref(MF_MT_AUDIO_SAMPLES_PER_SECOND), byref(sample_rate))
        if channels.value not in (1, 2):
            channels.value = 1
        if not (8000 <= sample_rate.value <= 192000):
            sample_rate.value = 48000

        # IMFSourceReader::ReadSample is vtable index 9
        ReadSample = _vcall(
            reader, 9, c_int32,
            c_uint32, c_uint32, POINTER(c_uint32), POINTER(c_uint32),
            POINTER(c_uint64), POINTER(c_void_p)
        )
        Release = _vcall(reader, 2, c_uint32)

        chunks = []
        while True:
            actual_stream = c_uint32()
            flags = c_uint32()
            timestamp = c_uint64()
            sample = c_void_p()
            hr = ReadSample(
                reader, MF_SOURCE_READER_FIRST_AUDIO_STREAM, 0,
                byref(actual_stream), byref(flags), byref(timestamp), byref(sample)
            )
            if hr != 0:
                raise RuntimeError(f"ReadSample failed: 0x{hr & 0xFFFFFFFF:08X}")
            if flags.value & 0x00000002:  # MF_SOURCE_READERF_ENDOFSTREAM
                if sample.value:
                    _vcall(sample, 2, c_uint32)(sample)
                break
            if sample.value:
                # IMFSample inherits from IMFAttributes (33 methods: 0..32)
                # 33: GetSampleFlags, 34: SetSampleFlags, 35: GetSampleTime, 36: SetSampleTime,
                # 37: GetSampleDuration, 38: SetSampleDuration, 39: GetBufferCount,
                # 40: GetBufferByIndex, 41: ConvertToContiguousBuffer
                buf = c_void_p()
                ConvertToContiguousBuffer = _vcall(sample, 41, c_int32, POINTER(c_void_p))
                hr = ConvertToContiguousBuffer(sample, byref(buf))
                if hr == 0 and buf.value:
                    # IMFMediaBuffer::Lock is vtable index 3; Unlock is index 4
                    ptr = c_void_p()
                    max_len = c_uint32()
                    cur_len = c_uint32()
                    Lock = _vcall(buf, 3, c_int32, POINTER(c_void_p), POINTER(c_uint32), POINTER(c_uint32))
                    Unlock = _vcall(buf, 4, c_int32)
                    if Lock(buf, byref(ptr), byref(max_len), byref(cur_len)) == 0:
                        data = ctypes.string_at(ptr.value, cur_len.value)
                        chunks.append(data)
                        Unlock(buf)
                    _vcall(buf, 2, c_uint32)(buf)
                _vcall(sample, 2, c_uint32)(sample)

        _vcall(out_type, 2, c_uint32)(out_type)
        _vcall(media_type, 2, c_uint32)(media_type)
        Release(reader)
        return sample_rate.value, channels.value, b"".join(chunks)
    finally:
        if tmp_path and tmp_path.exists():
            tmp_path.unlink()


def boost_and_limit_pcm16(pcm_bytes, gain_db=18.0):
    """將 16-bit PCM 放大 +18dB 並加上軟限幅（soft limiter），確保極大聲且不破音。"""
    samples = array.array("h")
    samples.frombytes(pcm_bytes)
    if not samples:
        return pcm_bytes

    peak = max(abs(x) for x in samples) or 1
    rms = math.sqrt(sum(float(x) * float(x) for x in samples) / len(samples))
    linear_gain = 10.0 ** (gain_db / 20.0)   # +18dB ≈ 7.94x

    # 使用 tanh 軟飽和限幅器，將放大後的訊號平滑壓在 ±32000 內，避免硬削波破音
    ceiling = 32000.0
    out = array.array("h", [0] * len(samples))
    for i, s in enumerate(samples):
        amplified = s * linear_gain
        # 膝點設在 24000，超過膝點使用 tanh 軟限幅至 32000
        if abs(amplified) <= 24000.0:
            val = amplified
        else:
            sign = 1.0 if amplified > 0 else -1.0
            excess = (abs(amplified) - 24000.0) / 8000.0
            val = sign * (24000.0 + 8000.0 * math.tanh(excess))
        out[i] = max(-32767, min(32767, int(val)))

    new_peak = max(abs(x) for x in out)
    new_rms = math.sqrt(sum(float(x) * float(x) for x in out) / len(out))
    eff_db = 20.0 * math.log10(max(1.0, new_rms) / max(1.0, rms))
    print(f"  原始 Peak={peak}, RMS={rms:.0f} -> 增益後 Peak={new_peak}, RMS={new_rms:.0f} (實效增益 +{eff_db:.1f} dB)")
    return out.tobytes()


def main():
    bgm_dir = Path(__file__).resolve().parent.parent / "assets" / "bgm"
    targets = [
        ("fisherman_sound_1.m4a", "fisherman_sound_1.wav"),
        ("fisherman_sound_2", "fisherman_sound_2.wav"),
        ("fisherman_sound_3", "fisherman_sound_3.wav"),
        ("fisherman_sound_4", "fisherman_sound_4.wav"),
    ]
    for src_name, dst_name in targets:
        src_path = bgm_dir / src_name
        dst_path = bgm_dir / dst_name
        if not src_path.exists():
            # 若之前被改名成 .mp3 也一併檢查
            alt_mp3 = bgm_dir / f"{Path(dst_name).stem}.mp3"
            if alt_mp3.exists():
                src_path = alt_mp3
            else:
                print(f"[跳過] 找不到來源檔案: {src_path}")
                continue
        print(f"[轉檔] {src_path.name} -> {dst_name}")
        sr, ch, pcm = decode_m4a_to_pcm(src_path)
        boosted = boost_and_limit_pcm16(pcm, gain_db=18.0)
        with wave.open(str(dst_path), "wb") as wf:
            wf.setnchannels(ch)
            wf.setsampwidth(2)
            wf.setframerate(sr)
            wf.writeframes(boosted)
        dur = len(boosted) / (2 * ch * sr)
        print(f"  已儲存 {dst_path} ({sr} Hz, {ch} ch, {dur:.2f}s, {dst_path.stat().st_size} bytes)")
        # 轉檔確認成功後，清理舊的無副檔名或 .m4a / .mp3 檔案
        if dst_path.exists() and dst_path.stat().st_size > 1000 and src_path != dst_path:
            src_path.unlink()
            print(f"  已清理舊檔: {src_path.name}")
        extra_mp3 = bgm_dir / f"{Path(dst_name).stem}.mp3"
        if extra_mp3.exists() and extra_mp3 != dst_path:
            extra_mp3.unlink()
            print(f"  已清理舊檔: {extra_mp3.name}")


if __name__ == "__main__":
    main()
