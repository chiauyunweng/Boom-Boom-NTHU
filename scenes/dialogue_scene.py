"""讀取單一 dialogue JSON 並用 pygame 播放對話。

專案結構：
    your_game_project/
        assets/{bg,char,ui}/
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

# ---------------- 路徑 ----------------
BASE_DIR = Path(__file__).resolve().parent.parent   # your_game_project/
ASSET_DIR = BASE_DIR / "assets"                     # assets/char, assets/bg, assets/ui
DIALOGUE_DIR = BASE_DIR / "dialogues"

# ---------------- 可調整設定 ----------------
SCREEN_W, SCREEN_H = 1920, 1080

# 之後換字體：填入 .ttf/.otf 路徑即可，例如 BASE_DIR / "assets" / "font" / "NotoSansTC.ttf"
FONT_PATH = None
FALLBACK_FONT_NAMES = (
    "microsoftjhenghei,microsoftyahei,notosanscjktc,notosanscjksc,"
    "pingfangtc,heititc,wqyzenhei,arialunicode"
)
SPEAKER_SIZE = 44
TEXT_SIZE = 40
SPEAKER_COLOR = (255, 230, 150)
TEXT_COLOR = (255, 255, 255)
LINE_SPACING = 12
CHARS_PER_SEC = 30            # 逐字顯示速度

TEXT_GAP_LEFT = 40            # 文字最左端與矮為方立繪「非透明部分右緣」的間隔
SPEAKER_Y_OFFSET = 40         # speaker 名字距對話框上緣
TEXT_Y_OFFSET = 130           # 內文第一行距對話框上緣

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


class Assets:
    """載入並快取圖片，一律 convert_alpha()。"""

    def __init__(self):
        self._cache = {}

    def get(self, name):
        if name in self._cache:
            return self._cache[name]
        prefix = name.split("_", 1)[0]  # char / bg / ui
        path = ASSET_DIR / prefix / f"{name}.png"
        try:
            img = pygame.image.load(str(path)).convert_alpha()
        except (FileNotFoundError, pygame.error):
            print(f"[dialogue_scene] 找不到素材：{path}")
            img = None
        self._cache[name] = img
        return img

    def char(self, char_id, state):
        # 找不到該表情就退回 idle
        return self.get(f"char_{char_id}_{state}") or self.get(f"char_{char_id}_idle")


def _make_font(size):
    if FONT_PATH and Path(FONT_PATH).exists():
        return pygame.font.Font(str(FONT_PATH), size)
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
        img = assets.get(f"char_{FRONT_CHAR}_{state}")
        if img:
            right = max(right, img.get_bounding_rect(min_alpha=1).right)
    return right


def play_dialogue(json_path, screen=None):
    if not pygame.get_init():
        pygame.init()
    screen = screen or pygame.display.get_surface()
    if screen is None:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H))

    with open(_resolve_dialogue(json_path), "r", encoding="utf-8") as f:
        scene = json.load(f)

    assets = Assets()
    box = assets.get("ui_dialogue_box")
    box_y = SCREEN_H - box.get_height() if box else SCREEN_H  # 底部切齊畫面底部

    speaker_font = _make_font(SPEAKER_SIZE)
    text_font = _make_font(TEXT_SIZE)

    text_left = _front_char_right_edge(assets) + TEXT_GAP_LEFT
    text_w = SCREEN_W - 2 * text_left          # 文字區塊左右對稱 => 區塊置中，文字靠左
    if text_w < 200:                           # 保險
        text_w = SCREEN_W - 2 * TEXT_GAP_LEFT
        text_left = TEXT_GAP_LEFT

    clock = pygame.time.Clock()
    # Windows 開著中文輸入法時，空白鍵會被輸入法吃掉，收不到 KEYDOWN。
    # 關掉文字輸入模式，讓按鍵直接送給遊戲。
    pygame.key.stop_text_input()
    pygame.event.clear()  # 清掉上一個畫面殘留的按鍵事件

    for line in scene["lines"]:
        bg_name = line.get("bg", scene.get("bg"))
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
                    (front_sprites if cid == FRONT_CHAR else back_sprites).append(img)
        for p in props:
            img = assets.get(p)
            if img:
                back_sprites.append(img)

        name = line.get("speaker", "") or ""
        name_surf = speaker_font.render(name, True, SPEAKER_COLOR) if name else None
        wrapped = _wrap(line.get("text", ""), text_font, text_w)
        total = sum(len(l) for l in wrapped)

        elapsed_ms = 0
        next_line = False
        while not next_line:
            dt = clock.tick(60)
            elapsed_ms += dt
            shown = min(total, int(elapsed_ms * CHARS_PER_SEC / 1000))

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    pygame.quit()
                    sys.exit()
                elif (
                    (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE)
                    # 備援：輸入法仍攔截時，空白會以 TEXTINPUT 事件送來
                    or (event.type == pygame.TEXTINPUT and event.text == " ")
                ):
                    if shown < total:                       # 還在逐字：先全部顯示
                        elapsed_ms = int(total * 1000 / CHARS_PER_SEC) + 1
                        shown = total
                    else:                                   # 已顯示完：下一句
                        next_line = True

            if next_line:
                break

            # 圖層（下到上）：背景 → 其他角色 → 對話框 → 矮為方 → 文字
            screen.fill((0, 0, 0))
            if bg:
                screen.blit(bg, (0, 0))
            for s in back_sprites:
                screen.blit(s, (0, 0))
            if box:
                screen.blit(box, (0, box_y))
            for s in front_sprites:
                screen.blit(s, (0, 0))

            if name_surf:
                screen.blit(name_surf, ((SCREEN_W - name_surf.get_width()) // 2,
                                        box_y + SPEAKER_Y_OFFSET))
            y = box_y + TEXT_Y_OFFSET
            remaining = shown
            for ln in wrapped:
                if remaining <= 0:
                    break
                part = ln[:remaining]
                remaining -= len(ln)
                if part:
                    screen.blit(text_font.render(part, True, TEXT_COLOR), (text_left, y))
                y += text_font.get_linesize() + LINE_SPACING

            pygame.display.flip()


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((SCREEN_W, SCREEN_H))
    play_dialogue(sys.argv[1] if len(sys.argv) > 1 else "crash")
    pygame.quit()