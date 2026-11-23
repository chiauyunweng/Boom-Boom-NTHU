"""讀取單一 dialogue JSON 並用 pygame 播放對話。

專案結構：
    your_game_project/
        assets/{bg,char,ui,font}/
        dialogues/dialogue_crash.json ...
        scenes/dialogue_scene.py   <-- 本檔
        main.py

用法：
    from scenes.dialogue_scene import play_dialogue
    play_dialogue("crash")   # 也可寫 "crash.json" / "dialogue_crash.json" / 完整路徑
"""
import json
import sys
from pathlib import Path

import pygame

from scenes import music, sfx, volume

# ---------------- 路徑 ----------------
BASE_DIR = Path(__file__).resolve().parent.parent   # your_game_project/
ASSET_DIR = BASE_DIR / "assets"                     # assets/char, assets/bg, assets/ui
FONT_DIR = ASSET_DIR / "font"
DIALOGUE_DIR = BASE_DIR / "dialogues"

# ---------------- 可調整設定 ----------------
SCREEN_W, SCREEN_H = 1920, 1080                     # 邏輯解析度（所有素材以此為準）

# None = 自動使用 assets/font/ 底下的 unifont_jp*.ttf / .otf；也可手動指定完整路徑
FONT_PATH = None
FALLBACK_FONT_NAMES = (
    "microsoftjhenghei,microsoftyahei,notosanscjktc,notosanscjksc,"
    "pingfangtc,heititc,wqyzenhei,arialunicode"
)
# Unifont 是點陣字型，字級請用 16 的倍數（16/32/48/64）才會銳利
SPEAKER_SIZE = 48
TEXT_SIZE = 32
FONT_ANTIALIAS = False                              # 點陣字型關閉反鋸齒才清晰
SPEAKER_COLOR = (255, 230, 150)
TEXT_COLOR = (255, 255, 255)
LINE_SPACING = 12
CHARS_PER_SEC = 30            # 逐字顯示速度

TEXT_GAP_LEFT = 40            # 文字最左端與矮為方立繪「非透明部分右緣」的間隔
SPEAKER_Y_OFFSET = 40         # speaker 名字距對話框上緣
TEXT_Y_OFFSET = 130           # 內文第一行距對話框上緣

SHOW_HINT = True              # 是否顯示右下角的操作提示
HINT_TEXT = "按 SPACE、點擊滑鼠或觸控板繼續"
HINT_SIZE = 32
HINT_COLOR = (190, 190, 190)
HINT_MARGIN_RIGHT = 60        # 提示文字右緣距畫面（＝對話框）右緣的內邊距
HINT_MARGIN_BOTTOM = 40       # 提示文字下緣距畫面（＝對話框）下緣的內邊距；提示固定在對話框右下角

SKIP_RECT = pygame.Rect(SCREEN_W - 24 - 200, 24, 200, 72)   # 右上角「跳過」按鈕（左上角是音量鈕）
SKIP_LABEL = "跳過 ▶▶"
SKIP_KEY = pygame.K_s                                      # 鍵盤 S 也可以跳過

FRONT_CHAR = "short_and_square"                    # 位於對話框上方圖層的角色（矮為方）
DEFAULT_CHARS = ["short_and_square", "tall_and_round"]
# --------------------------------------------


def _resolve_dialogue(name):
    """接受 "crash"、"crash.json"、"dialogue_crash.json" 或完整路徑。"""
    p = Path(name)
    if p.is_absolute() and p.exists():
        return p
    stem = p.stem
    for cand in (stem, f"dialogue_{stem}"):
        f = DIALOGUE_DIR / f"{cand}.json"
        if f.exists():
            return f
    raise FileNotFoundError(f"找不到對話檔：{name}（已搜尋 {DIALOGUE_DIR}）")


_font_path_cache = []


def _find_font():
    """回傳字型路徑；找不到回傳 None（改用系統字型）。"""
    if _font_path_cache:
        return _font_path_cache[0]
    path = None
    if FONT_PATH and Path(FONT_PATH).exists():
        path = Path(FONT_PATH)
    elif FONT_DIR.exists():
        # 不分大小寫、含子資料夾；優先找 unifont_jp，其次任何 unifont，最後任何字型檔
        files = sorted(p for p in FONT_DIR.rglob("*")
                       if p.suffix.lower() in (".ttf", ".otf", ".ttc"))
        for key in ("unifont_jp", "unifont", ""):
            hit = [p for p in files if key in p.name.lower()]
            if hit:
                path = hit[0]
                break
    if path is None:
        print(f"[dialogue_scene] 在 {FONT_DIR} 找不到 .ttf/.otf 字型，改用系統字型")
    else:
        print(f"[dialogue_scene] 使用字型：{path}")
    _font_path_cache.append(path)
    return path


_INVISIBLE = {"⁠", "​", "‌", "‍", "﻿", "­"}
_REPLACE = {"⋯": "…"}      # ⋯ → …（多數字型都有 …）
_warned_missing = set()


def _sanitize(text, font):
    """移除不可見字元、替換常缺字的符號，並提示字型缺字。"""
    out = []
    for ch in text:
        if ch in _INVISIBLE:
            continue
        ch = _REPLACE.get(ch, ch)
        if ch != "\n" and font.metrics(ch) == [None] and ch not in _warned_missing:
            _warned_missing.add(ch)
            print(f"[dialogue_scene] 字型缺字：{ch!r} (U+{ord(ch):04X})")
        out.append(ch)
    return "".join(out)


class Assets:
    """載入並快取圖片，一律 convert_alpha()。"""

    def __init__(self):
        self._cache = {}

    def get(self, name, optional=False):
        """optional=True：素材可有可無（例如沒有 frown 的角色），找不到不印警告。"""
        if name in self._cache:
            return self._cache[name]
        prefix = name.split("_", 1)[0]  # char / bg / ui
        path = ASSET_DIR / prefix / f"{name}.png"
        try:
            img = pygame.image.load(str(path)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            if not optional:
                print(f"[dialogue_scene] 找不到素材：{path}")
            img = None
        if img and prefix == "bg":
            # 背景一律當不透明圖：convert() 會丟掉 alpha，透明處改顯示底下的色彩
            # （和上機考 exam_scene 的做法一致，也比 convert_alpha 的繪製快）
            w, h = img.get_size()
            if pygame.mask.from_surface(img, 254).count() < w * h:
                print(f"[dialogue_scene] 注意：{name}.png 含有透明像素，已當成不透明背景顯示；"
                      f"若畫面仍不對，請檢查這張圖的透明區域")
            img = img.convert()
        if img and prefix in ("char", "bg") and img.get_size() != (SCREEN_W, SCREEN_H):
            print(f"[dialogue_scene] 注意：{name}.png 尺寸是 {img.get_size()}，"
                  f"不是 {SCREEN_W}x{SCREEN_H}，會因此被裁切或偏移")
        self._cache[name] = img
        return img

    def char(self, char_id, state):
        # 找不到該表情就退回 idle
        img = self.get(f"char_{char_id}_{state}")   # 找不到會印出完整路徑
        return img or self.get(f"char_{char_id}_idle")


def _make_font(size):
    path = _find_font()
    if path:
        return pygame.font.Font(str(path), size)
    return pygame.font.SysFont(FALLBACK_FONT_NAMES, size)


def _wrap(text, font, max_w):
    """逐字換行（適合中文），支援 \\n。"""
    lines = []
    for para in text.split("\n"):
        cur = ""
        for ch in para:
            if cur and font.size(cur + ch)[0] > max_w:
                lines.append(cur)
                cur = ch
            else:
                cur += ch
        lines.append(cur)
    return lines


def _front_char_right_edge(assets):
    """矮為方所有表情中，非透明像素的最右端。
    與當前場景有沒有顯示矮為方無關，所以文字左緣永遠固定。"""
    right = 0
    for state in ("idle", "talk", "frown"):
        img = assets.get(f"char_{FRONT_CHAR}_{state}", optional=True)
        if img:
            right = max(right, img.get_bounding_rect(min_alpha=1).right)
    return right


def _present(screen, canvas):
    """把 1920x1080 的 canvas 等比例縮放（完整顯示、置中、其餘填黑）到視窗。"""
    global _last_virtual_surface
    _last_virtual_surface = canvas
    win_w, win_h = screen.get_size()
    if (win_w, win_h) == (SCREEN_W, SCREEN_H):
        screen.blit(canvas, (0, 0))
        volume.draw_overlay(screen, 1, (0, 0))    # 左上角音量鈕（畫在視窗上，不弄髒 canvas）
        return
    scale = min(win_w / SCREEN_W, win_h / SCREEN_H)
    scaled_w = max(1, int(SCREEN_W * scale))
    scaled_h = max(1, int(SCREEN_H * scale))
    offset_x = (win_w - scaled_w) // 2
    offset_y = (win_h - scaled_h) // 2
    scaled = pygame.transform.smoothscale(canvas, (scaled_w, scaled_h))
    screen.fill((0, 0, 0))
    screen.blit(scaled, (offset_x, offset_y))
    volume.draw_overlay(screen, scale, (offset_x, offset_y))


_last_virtual_surface = None
_virtual_screen = None
_windowed_size = (1280, 720)
_is_fullscreen = False


def get_virtual_screen():
    """取得全域共用 1920x1080 虛擬畫布（virtual_screen / canvas）。"""
    global _virtual_screen
    if _virtual_screen is None:
        _virtual_screen = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
    return _virtual_screen


def get_virtual_snapshot():
    """複製目前虛擬畫布畫面（供彈出說明書、紙條、地圖時作為底圖）。"""
    src = _last_virtual_surface or _virtual_screen
    if src is not None and src.get_size() == (SCREEN_W, SCREEN_H):
        return src.copy()
    surf = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
    surf.fill((0, 0, 0))
    return surf


def init_display(caption="Visual Novel Game"):
    """設定 Windows 高 DPI 感知，並依螢幕可用解析度建立 16:9 的自適應可縮放視窗。"""
    global _windowed_size, _is_fullscreen
    import ctypes
    try:
        ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass

    if not pygame.get_init():
        pygame.init()

    info = pygame.display.Info()
    cur_w = info.current_w if info.current_w > 0 else SCREEN_W
    cur_h = info.current_h if info.current_h > 0 else SCREEN_H

    max_w = min(SCREEN_W, int(cur_w * 0.9))
    max_h = min(SCREEN_H, int(cur_h * 0.85))
    scale = min(max_w / SCREEN_W, max_h / SCREEN_H)
    win_w = max(640, int(SCREEN_W * scale))
    win_h = max(360, int(SCREEN_H * scale))
    _windowed_size = (win_w, win_h)
    _is_fullscreen = False

    screen = pygame.display.set_mode(_windowed_size, pygame.RESIZABLE)
    pygame.display.set_caption(caption)
    return screen


def toggle_fullscreen():
    """切換全螢幕 / 視窗模式（F11 或 Alt+Enter）。"""
    global _is_fullscreen, _windowed_size
    screen = pygame.display.get_surface()
    if not _is_fullscreen:
        if screen is not None:
            _windowed_size = screen.get_size()
        _is_fullscreen = True
        return pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
    else:
        _is_fullscreen = False
        return pygame.display.set_mode(_windowed_size, pygame.RESIZABLE)


def handle_window_event(event):
    """處理視窗縮放、F11 / Alt+Enter 全螢幕切換與左上角音量鈕；若已處理由此回傳 True。"""
    global _windowed_size
    if event.type in (pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP, pygame.MOUSEMOTION):
        if volume.handle_event(event, screen_to_virtual(event.pos)):
            return True
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_F11 or (
            event.key == pygame.K_RETURN and (event.mod & pygame.KMOD_ALT)
        ):
            toggle_fullscreen()
            return True
    elif event.type == pygame.VIDEORESIZE and not _is_fullscreen:
        w, h = max(320, event.w), max(180, event.h)
        _windowed_size = (w, h)
    return False


def screen_to_virtual(pos, clamp=False):
    """將實際視窗滑鼠座標 (mx, my) 轉換為 1920x1080 虛擬座標 (vx, vy)。
    若點擊落在黑邊區域（超出 0~1920 或 0~1080 範圍）：
      - clamp=False（預設，用於點擊判定）：回傳 None，忽略該次黑邊點擊
      - clamp=True（用於 MOUSEMOTION 追蹤）：回傳轉換後的虛擬座標（黑邊外不觸發 hover）"""
    surface = pygame.display.get_surface()
    if surface is None:
        return pos
    win_w, win_h = surface.get_size()
    if win_w <= 0 or win_h <= 0:
        return None
    scale = min(win_w / SCREEN_W, win_h / SCREEN_H)
    scaled_w = SCREEN_W * scale
    scaled_h = SCREEN_H * scale
    offset_x = (win_w - scaled_w) / 2.0
    offset_y = (win_h - scaled_h) / 2.0
    vx = (pos[0] - offset_x) / scale
    vy = (pos[1] - offset_y) / scale
    if not (0 <= vx < SCREEN_W and 0 <= vy < SCREEN_H):
        if not clamp:
            return None
    return int(vx), int(vy)


def _as_list(value):
    if not value:
        return []
    return [value] if isinstance(value, str) else list(value)


_warned_props = set()


def _prop_sprite(assets, spec):
    """props 的一個項目 → (圖, 左上角座標)；找不到圖回傳 None。
    字串："obj_bomb"，當成整張 1920x1080 素材貼在 (0,0)（和背景、立繪一樣）。
    dict ：{"image": "obj_bomb", "center": [x, y]} 或 {"image": ..., "pos": [x, y]}，
           可加 "scale": 倍率（小圖用）。圖檔依前綴找資料夾，例如 obj_bomb → assets/obj/obj_bomb.png。"""
    if isinstance(spec, str):
        spec = {"image": spec}
    img = assets.get(spec["image"])
    if img is None:
        return None
    if "center" in spec:          # 以「圖案本身」置中：先裁掉透明邊（整張 1920x1080 的素材也能移動）
        img = img.subsurface(img.get_bounding_rect(min_alpha=1))
    scale = spec.get("scale")
    if scale and scale != 1:
        img = pygame.transform.smoothscale(
            img, (max(1, int(img.get_width() * scale)), max(1, int(img.get_height() * scale))))
    if "center" in spec:
        pos = img.get_rect(center=tuple(spec["center"])).topleft
    else:
        pos = tuple(spec.get("pos", (0, 0)))
        if (pos == (0, 0) and img.get_size() != (SCREEN_W, SCREEN_H)
                and spec["image"] not in _warned_props):
            _warned_props.add(spec["image"])
            print(f"[dialogue_scene] 注意：{spec['image']}.png 尺寸是 {img.get_size()}，會貼在左上角 (0,0)；"
                  f'若是小圖，請在 JSON 寫 {{"image": "{spec["image"]}", "center": [x, y]}}')
    return img, pos


def _apply_vars(text, variables):
    """把文字裡的 {名稱} 換成 variables 內的值（沒給的 {xxx} 原樣保留）。"""
    for key, val in (variables or {}).items():
        text = text.replace("{" + key + "}", str(val))
    return text


def _draw_skip(target, font, hover):
    box = pygame.Surface(SKIP_RECT.size, pygame.SRCALPHA)
    pygame.draw.rect(box, (0, 0, 0, 170), box.get_rect(), border_radius=14)
    pygame.draw.rect(box, SPEAKER_COLOR if hover else (180, 180, 255), box.get_rect(), 3, border_radius=14)
    label = font.render(SKIP_LABEL, FONT_ANTIALIAS, SPEAKER_COLOR if hover else TEXT_COLOR)
    box.blit(label, label.get_rect(center=box.get_rect().center))
    target.blit(box, SKIP_RECT)


def _skip_rest(lines, events):
    """跳過剩下的台詞：不播音效，但背景音樂切到最後的狀態，且事件（紙條、說明書等線索）照樣觸發。"""
    for line in lines:
        if line.get("bgm"):
            music.play(line["bgm"])
        for event_name in _as_list(line.get("event")):
            callback = (events or {}).get(event_name)
            if callback is not None:
                callback()
                pygame.key.stop_text_input()
                pygame.event.clear()


def play_dialogue(json_path, screen=None, events=None, variables=None, bg_override=None):
    """播放一段對話 JSON。
    events：{事件名: 函式}。JSON 某句寫 "event": "名稱"（或 ["a", "b"]），
            玩家讀完該句、按下 SPACE 後會先呼叫該函式（例如彈出紙條），再接下一句。
    variables：{名稱: 值}。文字裡的 {名稱} 會被換掉，例如 "還剩 {remaining} 次機會"。
    JSON 每句還可寫 "sfx": "名稱"（該句開始時播音效）、"bgm": "名稱"（換背景音樂，"none" = 停止）；
    整段 JSON 最上層也可寫 "bgm"，在開頭生效。
    右上角的「跳過」（或按 S）會直接結束這段對話，但剩下台詞的事件仍會觸發。"""
    if not pygame.get_init():
        pygame.init()
    screen = screen or pygame.display.get_surface()
    if screen is None:
        screen = init_display()

    with open(_resolve_dialogue(json_path), "r", encoding="utf-8") as f:
        scene = json.load(f)

    if scene.get("bgm"):
        music.play(scene["bgm"])

    assets = Assets()
    box = assets.get("ui_dialogue_box")
    box_y = SCREEN_H - box.get_height() if box else SCREEN_H  # 底部切齊畫面底部

    speaker_font = _make_font(SPEAKER_SIZE)
    text_font = _make_font(TEXT_SIZE)
    skip_font = _make_font(32)
    skip_hover = False
    hint_surf = (_make_font(HINT_SIZE).render(HINT_TEXT, FONT_ANTIALIAS, HINT_COLOR)
                 if SHOW_HINT else None)

    text_left = _front_char_right_edge(assets) + TEXT_GAP_LEFT
    text_w = SCREEN_W - 2 * text_left          # 文字區塊左右對稱 => 區塊置中，文字靠左
    if text_w < 200:                           # 保險
        text_w = SCREEN_W - 2 * TEXT_GAP_LEFT
        text_left = TEXT_GAP_LEFT

    canvas = get_virtual_screen()
    clock = pygame.time.Clock()
    # Windows 開著中文輸入法時，空白鍵會被輸入法吃掉，收不到 KEYDOWN。
    pygame.key.stop_text_input()
    pygame.event.clear()  # 清掉上一個畫面殘留的按鍵事件

    lines = scene["lines"]
    for index, line in enumerate(lines):
        if line.get("bgm"):
            music.play(line["bgm"])
        for sfx_name in _as_list(line.get("sfx")):
            sfx.play(sfx_name)
        bg_name = bg_override or line.get("bg", scene.get("bg"))
        bg = assets.get(bg_name) if bg_name else None
        show_chars = line.get("show_characters", scene.get("show_characters", True))
        char_ids = line.get("characters", scene.get("characters", DEFAULT_CHARS))
        props = line.get("props", scene.get("props", []))   # 例如 char_TA_silhouette
        speaker_id = line.get("speaker_id")                 # 說話角色；旁白留空/null
        overrides = line.get("states", {})                  # 例如 {"tall_and_round": "frown"}

        # 決定每個角色的立繪
        back_sprites, front_sprites = [], []
        if show_chars:
            for cid in char_ids:
                state = overrides.get(cid) or ("talk" if cid == speaker_id else "idle")
                img = assets.char(cid, state)
                if img:
                    (front_sprites if cid == FRONT_CHAR else back_sprites).append((img, (0, 0)))
        for p in props:
            sprite = _prop_sprite(assets, p)
            if sprite:
                back_sprites.append(sprite)

        name = _apply_vars(line.get("speaker", "") or "", variables)
        name_surf = (speaker_font.render(name, FONT_ANTIALIAS, SPEAKER_COLOR)
                     if name else None)
        text = _apply_vars(line.get("text", ""), variables)
        wrapped = _wrap(_sanitize(text, text_font), text_font, text_w)
        total = sum(len(l) for l in wrapped)

        elapsed_ms = 0
        next_line = False
        skip = False
        while not next_line:
            dt = clock.tick(60)
            elapsed_ms += dt
            shown = min(total, int(elapsed_ms * CHARS_PER_SEC / 1000))

            advance = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif handle_window_event(event):
                    continue
                elif (
                    (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE)
                    # 備援：輸入法仍攔截時，空白會以 TEXTINPUT 事件送來
                    or (event.type == pygame.TEXTINPUT and event.text == " ")
                ):
                    advance = True                          # 同一幀不論收到幾個，只算一次
                elif event.type == pygame.KEYDOWN and event.key == SKIP_KEY:
                    skip = True
                elif event.type == pygame.MOUSEMOTION:
                    vpos = screen_to_virtual(event.pos)
                    skip_hover = bool(vpos) and SKIP_RECT.collidepoint(vpos)
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    # 滑鼠左鍵；若點在黑邊區域則忽略
                    vpos = screen_to_virtual(event.pos)
                    if vpos is not None and SKIP_RECT.collidepoint(vpos):
                        skip = True
                    elif vpos is not None:
                        advance = True

            if skip:
                break

            if advance:
                sfx.play("advance")
                if shown < total:                           # 還在逐字：先全部顯示
                    elapsed_ms = int(total * 1000 / CHARS_PER_SEC) + 1
                    shown = total
                else:                                       # 已顯示完：下一句
                    next_line = True

            if next_line:
                break

            # 統一繪製在 1920x1080 虛擬畫布 canvas 上，再等比例縮放至實際視窗
            screen = pygame.display.get_surface()
            target = canvas

            # 圖層（下到上）：背景 → 其他角色 → 對話框 → 矮為方 → 文字
            target.fill((0, 0, 0))
            if bg:
                target.blit(bg, (0, 0))
            for s, pos in back_sprites:
                target.blit(s, pos)
            if box:
                target.blit(box, (0, box_y))
            for s, pos in front_sprites:
                target.blit(s, pos)

            if hint_surf:
                target.blit(hint_surf, hint_surf.get_rect(
                    bottomright=(SCREEN_W - HINT_MARGIN_RIGHT, SCREEN_H - HINT_MARGIN_BOTTOM)))
            if name_surf:
                target.blit(name_surf, ((SCREEN_W - name_surf.get_width()) // 2,
                                        box_y + SPEAKER_Y_OFFSET))
            y = box_y + TEXT_Y_OFFSET
            remaining = shown
            for ln in wrapped:
                if remaining <= 0:
                    break
                part = ln[:remaining]
                remaining -= len(ln)
                if part:
                    target.blit(text_font.render(part, FONT_ANTIALIAS, TEXT_COLOR),
                                (text_left, y))
                y += text_font.get_linesize() + LINE_SPACING

            _draw_skip(target, skip_font, skip_hover)
            _present(screen, canvas)
            pygame.display.flip()

        if skip:
            sfx.play("advance")
            for sfx_name in _as_list(line.get("sfx")):
                sfx.stop(sfx_name)                          # 例如警報聲，跳過時一起停掉
            _skip_rest(lines[index:], events)
            break

        # 這句讀完、按下 SPACE 之後：觸發這句指定的事件（畫面仍停在這句，事件會以它當背景）
        for event_name in _as_list(line.get("event")):
            callback = (events or {}).get(event_name)
            if callback is None:
                print(f"[dialogue_scene] 沒有註冊的事件：{event_name}")
                continue
            callback()
            pygame.key.stop_text_input()
            pygame.event.clear()
            clock.tick()                                    # 丟掉事件期間累積的時間


if __name__ == "__main__":
    init_display()
    play_dialogue(sys.argv[1] if len(sys.argv) > 1 else "crash")
    pygame.quit()