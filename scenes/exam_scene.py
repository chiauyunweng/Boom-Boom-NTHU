"""機考關卡（Computer Exam Chapter）：找教室 → 紙條 → 電腦密碼，接在釣魚關卡之前。

流程（由 play_exam_chapter 串起）：
    puzzle_find_room → [找教室 60 秒：點門 → 座位表 → 點自己的座位]
        超時                  → puzzle_fail → 重來
        找到正確座位          → puzzle_find_room_correct（播到「發現紙條」時彈出紙條）
                              → [電腦密碼 120 秒：點資料夾 → 輸入 11539]
        答對                  → puzzle_succeed → 獲得「文件」道具
        答錯（< 5 次）        → puzzle_wrong（顯示剩餘次數），繼續輸入
        答錯 5 次 / 超時      → puzzle_fail → 回到找教室階段

用法：
    from scenes.exam_scene import play_exam_chapter
    item = play_exam_chapter()      # 回傳 {"name": "文件", "text": ...}
"""
import random
import sys

import pygame

from scenes import music, sfx
from scenes.alchemy_scene import _panel
from scenes.dialogue_scene import (
    ASSET_DIR, FONT_ANTIALIAS, SCREEN_H, SCREEN_W, _make_font, _present, _wrap,
    get_virtual_screen, get_virtual_snapshot, handle_window_event, init_display,
    play_dialogue, screen_to_virtual,
)

# ---------------- 可調整設定 ----------------
FIND_ROOM_SEC = 60            # 階段一：找教室 1 分鐘
COMPUTER_SEC = 120            # 階段三：密碼解謎 2 分鐘
SEAT_PENALTY_SEC = 5          # 點錯座位扣的秒數（0 = 不扣）
MAX_WRONG = 5                 # 密碼最多錯幾次
PASSWORD = "11539"

BG_FIND_ROOM = "bg_game_find_room.png"
BG_COMPUTER = "bg_computer.png"          # 還沒有圖檔時會自動用程式畫的佔位桌面
DOOR_IDLE = "obj_idle_find_room_door.png"
DOOR_SELECT = "obj_select_find_room_door.png"
FOLDER_IMG = "obj_idle_folder.png"       # 還沒有圖檔時會自動用程式畫的佔位資料夾

# 座位表：ROWS x COLS；Row 1 最靠近黑板；Col 1~8 由左至右，兩兩一組
ROWS, COLS = 6, 8
DOOR_NAMES = ["教室一", "教室二", "教室三"]    # 門上的標示（依位置由左至右，固定不變）
CLASSROOMS = [
    {"name": "教室一", "taken": {(1, 3), (2, 6), (3, 1), (4, 7), (5, 4)}, "correct": None},
    {"name": "教室二", "taken": {(1, 6), (2, 4), (3, 7), (4, 5), (5, 3)}, "correct": None},
    {"name": "教室三", "taken": {(1, 2), (2, 5), (3, 7), (5, 3), (6, 8)}, "correct": (4, 1)},
]

# 座位規則文件：內容之後在這裡填入（\n 換行）
RULES_TITLE = "座位規則"
RULES_TEXT = (
    "為避免同學們上機考作弊，請依照以下規則入座。\n"
    "\n"
    "一、同一行不能有人。\n"
    "二、同一列不能有人。\n"
    "三、對角線也不能坐人。\n"
    "四、最後，需要計算紙可以跟助教拿喔\\(･◡･)/。"
)
RULES_BTN_LABEL = "座位規則"
RULES_BTN = pygame.Rect(20, SCREEN_H - 110, 180, 80)          # 找教室畫面左下角（座位表彈窗外側）

# 獲得的「文件」道具：內容之後在這裡填入
DOC_NAME = "文件"
DOC_TITLE = "文件"
DOC_TEXT = "資料夾裡是一張地圖。"
DOC_IMAGE = "obj_map"          # assets/obj/obj_map.(png|jpg)，副檔名自動比對

# 版面
DOOR_H = 560
PANEL = pygame.Rect(0, 0, 1500, 900)
PANEL.center = (SCREEN_W // 2, SCREEN_H // 2)
CLOSE_RECT = pygame.Rect(0, 0, 64, 64)
CLOSE_RECT.topright = (PANEL.right - 24, PANEL.top + 24)
SEAT_W, SEAT_H = 118, 92
ROW_PITCH = 104
IN_GAP, AISLE = 6, 84
GRID_W = COLS * SEAT_W + (COLS // 2) * IN_GAP + (COLS // 2 - 1) * AISLE
GRID_LEFT = PANEL.centerx - GRID_W // 2 + 30
GRID_TOP = PANEL.top + 215

NOTE_RECT = pygame.Rect(0, 0, 1200, 560)
NOTE_RECT.center = (SCREEN_W // 2, SCREEN_H // 2)
NOTE_BTN = pygame.Rect(40, SCREEN_H - 120, 200, 80)          # 左下角：重看紙條
FOLDER_RECT = pygame.Rect(0, 0, 170, 150)
FOLDER_RECT.topleft = (150, 160)
PW_RECT = pygame.Rect(0, 0, 560, 780)
PW_RECT.center = (SCREEN_W // 2, SCREEN_H // 2 + 10)
PW_NOTE_BTN = pygame.Rect(0, 0, 240, 90)                     # 密碼視窗右側：重看紙條
PW_NOTE_BTN.topleft = (PW_RECT.right + 40, PW_RECT.top + 100)

TEXT = (255, 255, 255)
HINT = (220, 220, 220)
WARN = (255, 90, 90)
GOLD = (255, 230, 150)
INK = (60, 40, 30)
PAPER = (245, 232, 196)
ORANGE = (232, 118, 24)
# --------------------------------------------


def _quit():
    pygame.quit()
    sys.exit()


# ---------------- 素材 ----------------
def _load_img(folder, name):
    try:
        return pygame.image.load(str(ASSET_DIR / folder / name)).convert_alpha()
    except (FileNotFoundError, pygame.error):
        print(f"[exam_scene] 找不到素材：{ASSET_DIR / folder / name}（使用佔位圖）")
        return None


def _placeholder_computer_bg():
    bg = pygame.Surface((SCREEN_W, SCREEN_H))
    for y in range(SCREEN_H):                       # 藍色漸層桌面
        t = y / SCREEN_H
        pygame.draw.line(bg, (int(30 + 20 * t), int(80 + 60 * t), int(150 + 60 * t)),
                         (0, y), (SCREEN_W, y))
    pygame.draw.rect(bg, (25, 30, 45), (0, SCREEN_H - 70, SCREEN_W, 70))   # 工作列
    pygame.draw.rect(bg, (70, 130, 220), (16, SCREEN_H - 58, 46, 46), border_radius=8)
    return bg


def _load_bg(name):
    img = _load_img("bg", name)
    if img is None:
        return _placeholder_computer_bg() if name == BG_COMPUTER else _blank_bg()
    return img.convert()


def _blank_bg():
    bg = pygame.Surface((SCREEN_W, SCREEN_H))
    bg.fill((40, 40, 50))
    return bg


def _scaled_to_height(img, h):
    return pygame.transform.smoothscale(img, (int(img.get_width() * h / img.get_height()), h))


def _folder_surface():
    img = _load_img("obj", FOLDER_IMG)
    if img is not None:
        scale = min(FOLDER_RECT.w / img.get_width(), FOLDER_RECT.h / img.get_height())
        return pygame.transform.smoothscale(
            img, (max(1, int(img.get_width() * scale)), max(1, int(img.get_height() * scale))))
    s = pygame.Surface(FOLDER_RECT.size, pygame.SRCALPHA)
    w, h = s.get_size()
    pygame.draw.rect(s, (214, 170, 60), (0, 14, w * 0.42, 30), border_top_left_radius=10,
                     border_top_right_radius=10)
    pygame.draw.rect(s, (240, 196, 80), (0, 30, w, h - 30), border_radius=12)
    pygame.draw.rect(s, (150, 110, 30), (0, 30, w, h - 30), 4, border_radius=12)
    return s


# ---------------- 畫面輸出（相容視窗縮放） ----------------
class _Frame:
    """每個 loop 開頭 begin() 取得 1920x1080 虛擬畫布繪圖目標，結尾 end() 完成等比縮放與 flip。"""

    def __init__(self):
        self.canvas = get_virtual_screen()
        self.screen = None

    def begin(self):
        self.screen = pygame.display.get_surface()
        return self.canvas

    def end(self):
        _present(self.screen, self.canvas)
        pygame.display.flip()


def _draw_timer(target, font, remaining_ms, label):
    secs = max(0, (remaining_ms + 999) // 1000)
    color = WARN if secs <= 10 else TEXT
    t = font.render(f"{secs // 60:02d}:{secs % 60:02d}", FONT_ANTIALIAS, color)
    r = t.get_rect(topright=(SCREEN_W - 50, 40))
    _panel(target, r.inflate(40, 20), (0, 0, 0, 150), (180, 180, 255), 3, 12)
    target.blit(t, r)
    lab = _make_font(32).render(label, FONT_ANTIALIAS, HINT)
    target.blit(lab, lab.get_rect(topright=(r.right, r.bottom + 22)))


def _tick_sound(state, remaining_ms):
    secs = (remaining_ms + 999) // 1000
    if secs <= 10 and secs != state.get("last") and remaining_ms > 0:
        state["last"] = secs
        sfx.play("tick")


# ---------------- TLE 大字 ----------------
TLE_HOLD_MS = 1800            # TLE 大字停留時間（1.5~2 秒）
TLE_TEXT_SIZE = 192           # 釣魚「沒釣到」是 96；這裡放大一倍。Unifont 請用 16 的倍數
TLE_OUTLINE_PX = 6


def _show_tle(bg):
    """時間到：畫面只留背景（所有彈窗關閉、無法操作），中央顯示描邊大字 TLE，停留後返回。
    風格與釣魚關卡「沒釣到東西。」一致：白字 + 黑色描邊（共用 fishing_scene._outlined）。"""
    from scenes.fishing_scene import _outlined
    from scenes.dialogue_scene import TEXT_COLOR
    frame = _Frame()
    clock = pygame.time.Clock()
    surf = _outlined(_make_font(TLE_TEXT_SIZE), "TLE", TEXT_COLOR, TLE_OUTLINE_PX)
    sfx.play("timeout")
    pygame.event.clear()
    clock.tick()
    elapsed = 0
    while elapsed < TLE_HOLD_MS:
        elapsed += clock.tick(60)
        for event in pygame.event.get():      # 只處理關閉視窗與視窗縮放，其餘點擊/按鍵一律忽略
            if event.type == pygame.QUIT:
                _quit()
            handle_window_event(event)
        target = frame.begin()
        target.blit(bg, (0, 0))
        target.blit(surf, surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2)))
        frame.end()
    pygame.event.clear()


# ---------------- 座位表 ----------------
def _seat_rect(row, col):
    """row / col 皆從 1 起算。兩兩一組，組間有走道。"""
    group, k = divmod(col - 1, 2)
    x = GRID_LEFT + group * (2 * SEAT_W + IN_GAP + AISLE) + k * (SEAT_W + IN_GAP)
    y = GRID_TOP + (row - 1) * ROW_PITCH
    return pygame.Rect(x, y, SEAT_W, SEAT_H)


def _draw_empty_seat(target, r, hover):
    desk = pygame.Rect(r.x, r.y, r.w, 58)
    if hover:
        glow = pygame.Surface((r.w + 24, r.h + 24), pygame.SRCALPHA)
        pygame.draw.rect(glow, (255, 230, 120, 110), glow.get_rect(), border_radius=16)
        target.blit(glow, (r.x - 12, r.y - 12))
    pygame.draw.rect(target, (196, 154, 98) if not hover else (230, 190, 120), desk, border_radius=8)
    pygame.draw.rect(target, (110, 78, 40), desk, 3, border_radius=8)
    mon = pygame.Rect(0, 0, 54, 34)
    mon.midtop = (r.centerx, r.y + 6)
    pygame.draw.rect(target, (30, 34, 48), mon, border_radius=4)
    pygame.draw.rect(target, (90, 170, 240), mon.inflate(-8, -8), border_radius=2)
    pygame.draw.rect(target, (30, 34, 48), (r.centerx - 8, mon.bottom, 16, 6))
    pygame.draw.rect(target, (235, 235, 240), (r.centerx - 24, r.y + 46, 48, 8), border_radius=3)  # 鍵盤
    chair = pygame.Rect(0, 0, 54, 26)
    chair.midtop = (r.centerx, r.y + 64)
    pygame.draw.rect(target, (70, 90, 130), chair, border_radius=8)
    pygame.draw.rect(target, (35, 45, 75), chair, 3, border_radius=8)
    if hover:
        pygame.draw.rect(target, GOLD, r.inflate(10, 10), 4, border_radius=12)


def _draw_taken_seat(target, r):
    desk = pygame.Rect(r.x, r.y, r.w, 58)
    pygame.draw.rect(target, (96, 82, 70), desk, border_radius=8)
    pygame.draw.rect(target, (55, 45, 38), desk, 3, border_radius=8)
    mon = pygame.Rect(0, 0, 54, 34)
    mon.midtop = (r.centerx, r.y + 6)
    pygame.draw.rect(target, (20, 22, 30), mon, border_radius=4)
    pygame.draw.rect(target, (50, 60, 80), mon.inflate(-8, -8), border_radius=2)
    chair = pygame.Rect(0, 0, 54, 26)
    chair.midtop = (r.centerx, r.y + 64)
    pygame.draw.rect(target, (60, 62, 72), chair, border_radius=8)
    # 像素小人（坐在椅子上，頭在桌後露出）
    cx, top = r.centerx, r.y + 36
    pygame.draw.rect(target, (240, 200, 160), (cx - 9, top - 14, 18, 16))            # 頭
    pygame.draw.rect(target, (50, 40, 40), (cx - 9, top - 16, 18, 6))                # 頭髮
    pygame.draw.rect(target, (220, 90, 90), (cx - 13, top + 16, 26, 20))             # 身體
    pygame.draw.rect(target, (240, 200, 160), (cx - 17, top + 20, 5, 12))            # 手
    pygame.draw.rect(target, (240, 200, 160), (cx + 12, top + 20, 5, 12))
    pygame.draw.rect(target, (35, 35, 35), r, 2, border_radius=8)


def _draw_seating(target, fonts, room, label, mouse):
    """room：被指派到該扇門的教室資料；label：門上的名稱（依門的位置，不隨隨機分配改變）。"""
    """畫座位表彈窗；回傳滑鼠目前指向的空位 (row, col) 或 None。"""
    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    target.blit(shade, (0, 0))
    _panel(target, PANEL, (46, 52, 66, 250), (200, 205, 230), 6, 26)

    title = fonts["big"].render(f"{label} 座位表", FONT_ANTIALIAS, TEXT)
    target.blit(title, (PANEL.left + 50, PANEL.top + 32))

    hover_close = CLOSE_RECT.collidepoint(mouse)
    pygame.draw.rect(target, (200, 70, 70) if hover_close else (140, 50, 50), CLOSE_RECT,
                     border_radius=12)
    pygame.draw.rect(target, TEXT, CLOSE_RECT, 3, border_radius=12)
    c = CLOSE_RECT.inflate(-26, -26)
    pygame.draw.line(target, TEXT, c.topleft, c.bottomright, 6)
    pygame.draw.line(target, TEXT, c.topright, c.bottomleft, 6)

    board = pygame.Rect(0, 0, 900, 72)
    board.midtop = (GRID_LEFT + GRID_W // 2, PANEL.top + 120)
    pygame.draw.rect(target, (120, 85, 50), board.inflate(14, 14), border_radius=8)
    pygame.draw.rect(target, (36, 82, 62), board, border_radius=4)
    bt = fonts["big"].render("黑 板", FONT_ANTIALIAS, (235, 240, 235))
    target.blit(bt, bt.get_rect(center=board.center))

    hover = None
    for row in range(1, ROWS + 1):
        lab = fonts["small"].render(f"第{row}排", FONT_ANTIALIAS, HINT)
        target.blit(lab, lab.get_rect(midright=(GRID_LEFT - 24, _seat_rect(row, 1).centery - 6)))
        for col in range(1, COLS + 1):
            r = _seat_rect(row, col)
            if (row, col) in room["taken"]:
                _draw_taken_seat(target, r)
            else:
                is_hover = r.inflate(10, 10).collidepoint(mouse)
                if is_hover:
                    hover = (row, col)
                _draw_empty_seat(target, r, is_hover)

    legend = fonts["small"].render("亮色桌椅 = 空位（可點擊）　暗色＋小人 = 已入座　請點選你的座位",
                                   FONT_ANTIALIAS, HINT)
    target.blit(legend, legend.get_rect(midbottom=(PANEL.centerx, PANEL.bottom - 22)))
    return hover


# ---------------- 階段一：找教室 ----------------
def run_find_room():
    """成功找到座位回傳 True；時間到回傳 False。"""
    frame = _Frame()
    clock = pygame.time.Clock()
    fonts = {"big": _make_font(48), "small": _make_font(32)}
    bg = _load_bg(BG_FIND_ROOM)
    door_idle = _load_img("obj", DOOR_IDLE)
    door_sel = _load_img("obj", DOOR_SELECT) or door_idle
    if door_idle is not None:
        door_idle = _scaled_to_height(door_idle, DOOR_H)
        door_sel = _scaled_to_height(door_sel, DOOR_H)
    door_w = door_idle.get_width() if door_idle else 250
    gap = 150
    total = 3 * door_w + 2 * gap
    left = (SCREEN_W - total) // 2
    doors = [pygame.Rect(left + i * (door_w + gap), 250, door_w, DOOR_H) for i in range(3)]

    remaining_ms = FIND_ROOM_SEC * 1000
    rooms = list(CLASSROOMS)              # 每次進入找教室階段都重新隨機指派教室到三扇門（由左至右）
    random.shuffle(rooms)
    open_room = None
    rules_open = False
    toast, toast_ms = "", 0
    mouse = (0, 0)
    tick = {}

    music.play("tension")
    pygame.key.stop_text_input()
    pygame.event.clear()
    clock.tick()

    while True:
        dt = clock.tick(60)
        remaining_ms -= dt
        toast_ms = max(0, toast_ms - dt)
        if remaining_ms <= 0:
            _show_tle(bg)
            return False
        _tick_sound(tick, remaining_ms)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            elif handle_window_event(event):
                continue
            elif event.type == pygame.MOUSEMOTION:
                mouse = screen_to_virtual(event.pos, clamp=True)
            elif rules_open:                         # 規則視窗開著：只處理關閉，倒數與座位表狀態都照舊
                if _is_close_event(event):
                    rules_open = False
                    sfx.play("paper")
            elif event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE and open_room is not None:
                open_room = None
                sfx.play("cancel")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                vpos = screen_to_virtual(event.pos)
                if vpos is None:
                    continue
                mouse = vpos
                if RULES_BTN.collidepoint(mouse):
                    rules_open = True
                    sfx.play("paper")
                elif open_room is None:
                    for i, d in enumerate(doors):
                        if d.collidepoint(mouse):
                            open_room = i
                            sfx.play("door")
                            break
                elif CLOSE_RECT.collidepoint(mouse):
                    open_room = None
                    sfx.play("cancel")
                else:
                    for row in range(1, ROWS + 1):
                        for col in range(1, COLS + 1):
                            if (row, col) in rooms[open_room]["taken"]:
                                continue
                            if not _seat_rect(row, col).inflate(10, 10).collidepoint(mouse):
                                continue
                            if rooms[open_room]["correct"] == (row, col):
                                sfx.play("success")
                                return True
                            sfx.play("buzz")
                            toast = "這不是我的座位……"
                            toast_ms = 1800
                            if SEAT_PENALTY_SEC:
                                remaining_ms -= SEAT_PENALTY_SEC * 1000
                                toast += f"（-{SEAT_PENALTY_SEC} 秒）"

        target = frame.begin()
        target.blit(bg, (0, 0))
        for i, d in enumerate(doors):
            hov = open_room is None and not rules_open and d.collidepoint(mouse)
            img = door_sel if hov else door_idle
            if img is not None:
                target.blit(img, img.get_rect(center=d.center) if hov else d.topleft)
            else:
                pygame.draw.rect(target, GOLD if hov else (150, 110, 70), d, border_radius=10)
            lab = fonts["big"].render(DOOR_NAMES[i], FONT_ANTIALIAS, GOLD if hov else TEXT)
            lr = lab.get_rect(midtop=(d.centerx, d.bottom + 16))
            _panel(target, lr.inflate(30, 12), (0, 0, 0, 160), (180, 180, 255), 2, 10)
            target.blit(lab, lr)
        hint = fonts["small"].render("點擊門查看座位表，找到自己的座位", FONT_ANTIALIAS, TEXT)
        hr = hint.get_rect(midtop=(SCREEN_W // 2, 40))
        _panel(target, hr.inflate(40, 20), (0, 0, 0, 150), (180, 180, 255), 3, 12)
        target.blit(hint, hr)

        if open_room is not None:
            _draw_seating(target, fonts, rooms[open_room], DOOR_NAMES[open_room], mouse)
        hov_rules = RULES_BTN.collidepoint(mouse) and not rules_open
        _panel(target, RULES_BTN, (245, 232, 196, 245), GOLD if hov_rules else INK, 5, 14)
        rt = fonts["small"].render(RULES_BTN_LABEL, FONT_ANTIALIAS, INK)
        target.blit(rt, rt.get_rect(center=RULES_BTN.center))
        _draw_timer(target, fonts["big"], remaining_ms, "找教室")
        if toast_ms:
            t = fonts["big"].render(toast, FONT_ANTIALIAS, WARN)
            tr = t.get_rect(center=(SCREEN_W // 2, SCREEN_H - 70))
            _panel(target, tr.inflate(50, 24), (0, 0, 0, 210), WARN, 3, 12)
            target.blit(t, tr)
        if rules_open:
            _draw_doc_view(target, fonts, RULES_TITLE, RULES_TEXT, "點擊任意處或按空白鍵關閉")
            _draw_timer(target, fonts["big"], remaining_ms, "找教室")
        frame.end()


# ---------------- 紙條 ----------------
# 每個「欄」是一位數字的 7 段顯示格（寬 CW、高 CH）。右半張紙從摺痕往右依序是第 1~5 欄，
# 左半張紙從摺痕往左依序是第 1~5 欄；沿摺痕對折時，同一欄的左右兩半（左半張為鏡像）疊合成一位數字：
#   欄 1：右 ' + 左 ╷        → 1
#   欄 2：右 ╷ + 左 ''       → 1
#   欄 3：右 ≡(含左上短豎) + 左 ╷  → 5
#   欄 4：右 │ + 左 ≡        → 3
#   欄 5：右 □ + 左 └（鏡像成 ┘） → 9
CW, CH, PITCH, FIRST_OFFSET, STROKE = 44, 150, 66, 34, 9
_H = CH / 2
# 線段格式：("h", x1, x2, y) 水平；("v", x, y1, y2) 垂直（格內座標，右半張畫法）
_RIGHT_PIECES = [
    [("v", CW, 0, _H)],                                                         # '
    [("v", CW, _H, CH)],                                                        # ╷
    [("h", 0, CW, 0), ("h", 0, CW, _H), ("h", 0, CW, CH), ("v", 0, 0, _H)],     # ≡（含左上短豎）
    [("v", CW, 0, CH)],                                                         # │
    [("h", 0, CW, 0), ("h", 0, CW, _H), ("v", 0, 0, _H), ("v", CW, 0, _H)],     # □
]
_LEFT_PIECES = [
    [("v", CW, _H, CH)],                                                        # ╷
    [("v", CW, 0, _H * 0.4), ("v", CW, _H * 0.6, _H)],                          # ''
    [("v", CW, _H, CH)],                                                        # ╷
    [("h", 0, CW, 0), ("h", 0, CW, _H), ("h", 0, CW, CH)],                      # ≡
    [("v", CW, _H, CH), ("h", 0, CW, CH)],                                      # └（鏡像後）
]


def _stroke_rect(seg, ox, oy, fold_x, mirror):
    kind = seg[0]
    if kind == "h":
        _, x1, x2, y = seg
        xa, xb, ya, yb = ox + x1, ox + x2, oy + y, oy + y
    else:
        _, x, y1, y2 = seg
        xa, xb, ya, yb = ox + x, ox + x, oy + y1, oy + y2
    if mirror:                                   # 以摺痕為軸左右翻轉
        xa, xb = 2 * fold_x - xa, 2 * fold_x - xb
    h = STROKE // 2
    return pygame.Rect(min(xa, xb) - h, min(ya, yb) - h,
                       abs(xb - xa) + STROKE, abs(yb - ya) + STROKE)


_note_cache = []


def _build_note():
    """預先畫好整張紙條（不含半透明遮罩）。"""
    if _note_cache:
        return _note_cache[0]
    r = NOTE_RECT
    s = pygame.Surface(r.size, pygame.SRCALPHA)
    local = s.get_rect()
    pygame.draw.rect(s, PAPER, local, border_radius=10)
    rng = random.Random(7)
    for _ in range(260):                                          # 紙張雜點質感
        x, y = rng.randrange(local.w), rng.randrange(local.h)
        v = rng.randint(-14, 8)
        pygame.draw.circle(s, (PAPER[0] + v, PAPER[1] + v, PAPER[2] + v), (x, y), rng.randint(1, 2))
    for y in range(40, local.h, 44):                              # 淡淡的橫線
        pygame.draw.line(s, (228, 214, 176), (20, y), (local.w - 20, y), 1)
    fold_x = local.w * 2 // 3                                     # 約 2/3 處的摺痕
    for i in range(36):                                           # 摺痕兩側陰影漸層
        a = int(46 * (1 - i / 36))
        sh = pygame.Surface((1, local.h), pygame.SRCALPHA)
        sh.fill((90, 60, 20, a))
        s.blit(sh, (fold_x + i, 0))
        s.blit(sh, (fold_x - i - 1, 0))
    y = 14
    while y < local.h - 14:                                       # 摺痕虛線
        pygame.draw.line(s, (130, 100, 70), (fold_x, y), (fold_x, min(y + 16, local.h - 14)), 3)
        y += 28
    # 黑色 TEAM
    big = _make_font(96)
    team = big.render("TEAM", FONT_ANTIALIAS, (20, 20, 20))
    s.blit(team, team.get_rect(midleft=(56, local.centery)))
    # 橘色殘缺筆畫
    oy = local.centery - CH // 2
    for k in range(5):
        ox = fold_x + FIRST_OFFSET + k * PITCH
        for seg in _RIGHT_PIECES[k]:
            pygame.draw.rect(s, ORANGE, _stroke_rect(seg, ox, oy, fold_x, False))
        for seg in _LEFT_PIECES[k]:
            pygame.draw.rect(s, ORANGE, _stroke_rect(seg, ox, oy, fold_x, True))
    pygame.draw.rect(s, (150, 120, 80), local, 5, border_radius=10)
    _note_cache.append(s)
    return s


def _draw_note(target, font):
    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    target.blit(shade, (0, 0))
    target.blit(_build_note(), NOTE_RECT.topleft)
    hint = font.render("點擊任意處或按空白鍵收起", FONT_ANTIALIAS, HINT)
    target.blit(hint, hint.get_rect(midtop=(SCREEN_W // 2, NOTE_RECT.bottom + 30)))


def _is_close_event(event):
    if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
        return screen_to_virtual(event.pos) is not None
    return (
        (event.type == pygame.KEYDOWN
            and event.key in (pygame.K_SPACE, pygame.K_ESCAPE, pygame.K_RETURN))
        or (event.type == pygame.TEXTINPUT and event.text == " ")
    )


def show_note():
    """獨立顯示紙條（對話事件用，不計時），蓋在目前畫面上，關閉後返回。"""
    backdrop = get_virtual_snapshot()
    frame = _Frame()
    font = _make_font(32)
    clock = pygame.time.Clock()
    pygame.event.clear()
    sfx.play("paper")
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            if handle_window_event(event):
                continue
            if _is_close_event(event):
                sfx.play("paper")
                return
        target = frame.begin()
        target.blit(backdrop, (0, 0))
        _draw_note(target, font)
        frame.end()


# ---------------- 階段三：電腦密碼 ----------------
KEYS = ["1", "2", "3", "4", "5", "6", "7", "8", "9", "C", "0", "OK"]


def _key_rects():
    rects = {}
    kw, kh, g = 150, 100, 20
    left = PW_RECT.centerx - (3 * kw + 2 * g) // 2
    top = PW_RECT.top + 270
    for i, k in enumerate(KEYS):
        rects[k] = pygame.Rect(left + (i % 3) * (kw + g), top + (i // 3) * (kh + g), kw, kh)
    return rects


def _draw_password(target, fonts, entry, mouse, wrong_count, shake):
    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 150))
    target.blit(shade, (0, 0))
    r = PW_RECT.move(shake, 0)
    _panel(target, r, (236, 236, 242, 252), (60, 90, 160), 6, 18)
    pygame.draw.rect(target, (60, 90, 160), (r.x, r.y, r.w, 76), border_top_left_radius=18,
                     border_top_right_radius=18)
    t = fonts["small"].render("資料夾已加密－請輸入密碼", FONT_ANTIALIAS, TEXT)
    target.blit(t, (r.x + 28, r.y + 22))
    close = pygame.Rect(0, 0, 50, 50)
    close.topright = (r.right - 14, r.y + 13)
    hc = close.collidepoint(mouse)
    pygame.draw.rect(target, (220, 80, 80) if hc else (170, 60, 60), close, border_radius=8)
    c = close.inflate(-22, -22)
    pygame.draw.line(target, TEXT, c.topleft, c.bottomright, 5)
    pygame.draw.line(target, TEXT, c.topright, c.bottomleft, 5)

    # 五格密碼顯示
    box_w, g = 84, 14
    left = r.centerx - (5 * box_w + 4 * g) // 2
    for i in range(5):
        b = pygame.Rect(left + i * (box_w + g), r.y + 110, box_w, 100)
        pygame.draw.rect(target, (255, 255, 255), b, border_radius=8)
        pygame.draw.rect(target, (60, 90, 160) if i == len(entry) else (150, 150, 170), b,
                         4 if i == len(entry) else 3, border_radius=8)
        if i < len(entry):
            d = fonts["big"].render(entry[i], FONT_ANTIALIAS, INK)
            target.blit(d, d.get_rect(center=b.center))
    left_tries = MAX_WRONG - wrong_count
    info = fonts["small"].render(f"剩餘嘗試次數：{left_tries}", FONT_ANTIALIAS,
                                 WARN if left_tries <= 2 else (70, 70, 90))
    target.blit(info, info.get_rect(midtop=(r.centerx, r.y + 228)))

    hover_key = None
    for k, kr in _key_rects().items():
        kr = kr.move(shake, 0)
        hov = kr.collidepoint(mouse)
        base = {"C": (200, 120, 90), "OK": (80, 160, 100)}.get(k, (90, 110, 170))
        col = tuple(min(255, v + 40) for v in base) if hov else base
        pygame.draw.rect(target, col, kr, border_radius=12)
        pygame.draw.rect(target, (30, 40, 80), kr, 3, border_radius=12)
        lab = fonts["big"].render({"C": "清除", "OK": "確認"}.get(k, k), FONT_ANTIALIAS, TEXT)
        target.blit(lab, lab.get_rect(center=kr.center))
        if hov:
            hover_key = k
    return close, hover_key


def _draw_doc_view(target, fonts, title, text, footer, image=None):
    """閱讀視窗。image：選用的 Surface，會等比縮放置中顯示在標題下方、說明文字上方。"""
    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    target.blit(shade, (0, 0))
    r = pygame.Rect(0, 0, 1400, 900) if image is not None else pygame.Rect(0, 0, 1100, 720)
    r.center = (SCREEN_W // 2, SCREEN_H // 2)
    pygame.draw.rect(target, PAPER, r, border_radius=12)
    pygame.draw.rect(target, INK, r, 6, border_radius=12)
    xr = pygame.Rect(0, 0, 56, 56)                       # 右上角關閉按鈕（點視窗任意處也可關閉）
    xr.topright = (r.right - 20, r.top + 20)
    pygame.draw.rect(target, (170, 60, 60), xr, border_radius=10)
    xc = xr.inflate(-24, -24)
    pygame.draw.line(target, TEXT, xc.topleft, xc.bottomright, 5)
    pygame.draw.line(target, TEXT, xc.topright, xc.bottomleft, 5)
    tt = fonts["big"].render(title, FONT_ANTIALIAS, INK)
    target.blit(tt, tt.get_rect(midtop=(r.centerx, r.top + 50)))
    pygame.draw.line(target, INK, (r.left + 80, r.top + 125), (r.right - 80, r.top + 125), 3)
    y = r.top + 165
    if image is not None:
        box = pygame.Rect(r.left + 60, r.top + 145, r.width - 120, r.height - 145 - 170)
        scale = min(box.w / image.get_width(), box.h / image.get_height())
        img = pygame.transform.smoothscale(
            image, (max(1, int(image.get_width() * scale)), max(1, int(image.get_height() * scale))))
        ir = img.get_rect(center=box.center)
        target.blit(img, ir)
        pygame.draw.rect(target, INK, ir.inflate(8, 8), 4)
        y = box.bottom + 24
    for ln in _wrap(text, fonts["small"], r.width - 160):
        if ln:
            target.blit(fonts["small"].render(ln, FONT_ANTIALIAS, INK), (r.left + 80, y))
        y += fonts["small"].get_linesize() + 14
    ft = fonts["small"].render(footer, FONT_ANTIALIAS, (130, 110, 90))
    target.blit(ft, ft.get_rect(midbottom=(r.centerx, r.bottom - 30)))


_doc_image_cache = []


def _load_doc_image():
    """載入文件圖片（自動比對 .png / .jpg / .jpeg）；找不到回傳 None。"""
    if _doc_image_cache:
        return _doc_image_cache[0]
    img = None
    for ext in (".png", ".PNG", ".jpg", ".JPG", ".jpeg"):
        p = ASSET_DIR / "obj" / (DOC_IMAGE + ext)
        if p.exists():
            try:
                img = pygame.image.load(str(p)).convert_alpha()      # 保留透明通道
            except pygame.error:
                img = None
            break
    if img is None:
        print(f"[exam_scene] 找不到文件圖片：{ASSET_DIR / 'obj' / DOC_IMAGE}.*")
    _doc_image_cache.append(img)
    return img


def run_computer():
    """密碼解開回傳 True；時間到或錯誤達上限回傳 False。"""
    frame = _Frame()
    clock = pygame.time.Clock()
    fonts = {"big": _make_font(48), "small": _make_font(32)}
    bg = _load_bg(BG_COMPUTER)
    folder = _folder_surface()
    folder_pos = folder.get_rect(center=FOLDER_RECT.center)

    remaining_ms = COMPUTER_SEC * 1000
    wrong_count = 0
    entry = ""
    pw_open = False
    note_open = False
    shake_ms = 0
    mouse = (0, 0)
    tick = {}
    keys = _key_rects()

    music.play("tension")
    pygame.key.stop_text_input()
    pygame.event.clear()
    clock.tick()

    def submit():
        nonlocal entry, wrong_count, shake_ms, pw_open
        if entry == PASSWORD:
            return True
        wrong_count += 1
        entry = ""
        shake_ms = 400
        if wrong_count >= MAX_WRONG:
            return False
        play_dialogue("puzzle_wrong", variables={"remaining": MAX_WRONG - wrong_count})
        music.play("tension")
        pygame.key.stop_text_input()
        pygame.event.clear()
        clock.tick()                    # 丟掉劇情期間累積的時間（對話不計時）
        return None

    while True:
        dt = clock.tick(60)
        remaining_ms -= dt
        shake_ms = max(0, shake_ms - dt)
        if remaining_ms <= 0:
            _show_tle(bg)
            return False
        _tick_sound(tick, remaining_ms)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            elif handle_window_event(event):
                continue
            elif event.type == pygame.MOUSEMOTION:
                mouse = screen_to_virtual(event.pos, clamp=True)
                continue

            result = "pending"
            if note_open:
                if _is_close_event(event):
                    note_open = False
                    sfx.play("paper")
                continue
            if event.type == pygame.KEYDOWN and pw_open:
                if event.key == pygame.K_ESCAPE:
                    pw_open, entry = False, ""
                    sfx.play("cancel")
                elif event.key == pygame.K_BACKSPACE:
                    entry = entry[:-1]
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
                    if len(entry) == 5:
                        result = submit()
                else:
                    ch = event.unicode if event.unicode.isdigit() else ""
                    if not ch and pygame.K_KP0 <= event.key <= pygame.K_KP9:
                        ch = str(event.key - pygame.K_KP0)
                    if ch and len(entry) < 5:
                        entry += ch
                        sfx.play("advance")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                vpos = screen_to_virtual(event.pos)
                if vpos is None:
                    continue
                mouse = vpos
                if pw_open:
                    if PW_NOTE_BTN.collidepoint(mouse):         # 密碼視窗旁的「查看紙條」；已輸入內容保留
                        note_open = True
                        sfx.play("paper")
                    elif pygame.Rect(0, 0, 50, 50).move(PW_RECT.right - 64, PW_RECT.y + 13).collidepoint(mouse):
                        pw_open, entry = False, ""
                        sfx.play("cancel")
                    else:
                        for k, kr in keys.items():
                            if not kr.collidepoint(mouse):
                                continue
                            if k == "C":
                                entry = ""
                                sfx.play("cancel")
                            elif k == "OK":
                                if len(entry) == 5:
                                    result = submit()
                                else:
                                    sfx.play("buzz")
                            elif len(entry) < 5:
                                entry += k
                                sfx.play("advance")
                            break
                elif NOTE_BTN.collidepoint(mouse):
                    note_open = True
                    sfx.play("paper")
                elif folder_pos.collidepoint(mouse):
                    pw_open = True
                    entry = ""
                    sfx.play("pickup")
            if result is True:
                sfx.play("success")
                return True
            if result is False:
                return False

        target = frame.begin()
        target.blit(bg, (0, 0))
        hov_folder = not pw_open and not note_open and folder_pos.collidepoint(mouse)
        if hov_folder:
            glow = pygame.Surface((folder_pos.w + 30, folder_pos.h + 30), pygame.SRCALPHA)
            pygame.draw.rect(glow, (255, 255, 255, 80), glow.get_rect(), border_radius=14)
            target.blit(glow, (folder_pos.x - 15, folder_pos.y - 15))
        target.blit(folder, folder_pos)
        fl = fonts["small"].render("資料夾", FONT_ANTIALIAS, TEXT)
        target.blit(fl, fl.get_rect(midtop=(folder_pos.centerx, folder_pos.bottom + 14)))

        hov_note = NOTE_BTN.collidepoint(mouse) and not pw_open and not note_open
        _panel(target, NOTE_BTN, (245, 232, 196, 235), GOLD if hov_note else INK, 4, 12)
        nt = fonts["small"].render("紙條", FONT_ANTIALIAS, INK)
        target.blit(nt, nt.get_rect(center=NOTE_BTN.center))

        _draw_timer(target, fonts["big"], remaining_ms, "解開文件")
        if pw_open:
            shake = int(12 * (shake_ms / 400) * (1 if (shake_ms // 50) % 2 else -1))
            _draw_password(target, fonts, entry, mouse, wrong_count, shake)
            hov_pn = PW_NOTE_BTN.collidepoint(mouse) and not note_open
            _panel(target, PW_NOTE_BTN, (245, 232, 196, 245), GOLD if hov_pn else INK, 5, 14)
            pt = fonts["small"].render("查看紙條", FONT_ANTIALIAS, INK)
            target.blit(pt, pt.get_rect(center=PW_NOTE_BTN.center))
            if not note_open:
                hint = fonts["small"].render("可用鍵盤輸入數字，Enter 確認，Backspace 刪除，Esc 關閉",
                                             FONT_ANTIALIAS, HINT)
                target.blit(hint, hint.get_rect(midbottom=(SCREEN_W // 2, SCREEN_H - 24)))
        else:
            hint = fonts["small"].render("點擊資料夾輸入密碼　（左下角可重看紙條）", FONT_ANTIALIAS, HINT)
            target.blit(hint, hint.get_rect(midbottom=(SCREEN_W // 2, SCREEN_H - 90)))
        if note_open:
            _draw_note(target, fonts["small"])
            _draw_timer(target, fonts["big"], remaining_ms, "解開文件")
        frame.end()


# ---------------- 獲得道具 ----------------
def show_item_acquired():
    """獲得地圖：螢幕中央直接顯示 obj_map 大圖（無視窗、標題、文字）。
    點圖片以外的遮罩區、右上角 [X]、或按 Esc / 空白 / Enter 關閉；關閉後才返回。"""
    backdrop = get_virtual_snapshot()
    frame = _Frame()
    clock = pygame.time.Clock()

    img = _load_doc_image()
    if img is not None:                                   # 等比縮放到畫面內（保留邊距）
        scale = min((SCREEN_W - 160) / img.get_width(), (SCREEN_H - 160) / img.get_height())
        img = pygame.transform.smoothscale(
            img, (max(1, int(img.get_width() * scale)), max(1, int(img.get_height() * scale))))
        img_rect = img.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2))
    else:
        img_rect = pygame.Rect(0, 0, 0, 0)
    xr = pygame.Rect(0, 0, 56, 56)                        # 圖片右上角的關閉 [X]
    xr.center = (img_rect.right - 10, img_rect.top + 10) if img else (SCREEN_W - 60, 60)
    xr.clamp_ip(pygame.Rect(0, 0, SCREEN_W, SCREEN_H))
    mouse = (0, 0)

    pygame.key.stop_text_input()
    pygame.event.clear()
    sfx.play("catch")
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            elif handle_window_event(event):
                continue
            elif event.type == pygame.MOUSEMOTION:
                mouse = screen_to_virtual(event.pos, clamp=True)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = screen_to_virtual(event.pos)
                if pos is None:
                    continue
                if xr.collidepoint(pos) or not img_rect.collidepoint(pos):
                    sfx.play("paper")
                    return
            elif event.type == pygame.KEYDOWN and event.key in (
                    pygame.K_ESCAPE, pygame.K_SPACE, pygame.K_RETURN):
                sfx.play("paper")
                return
        target = frame.begin()
        target.blit(backdrop, (0, 0))
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        target.blit(shade, (0, 0))
        if img is not None:
            target.blit(img, img_rect)
        hov = xr.collidepoint(mouse)
        pygame.draw.rect(target, (220, 80, 80) if hov else (170, 60, 60), xr, border_radius=10)
        pygame.draw.rect(target, TEXT, xr, 3, border_radius=10)
        xc = xr.inflate(-24, -24)
        pygame.draw.line(target, TEXT, xc.topleft, xc.bottomright, 5)
        pygame.draw.line(target, TEXT, xc.topright, xc.bottomleft, 5)
        frame.end()


# ---------------- 整章 ----------------
def _wait_retry(bg, label):
    """失敗對話結束後：顯示背景與一顆按鈕，等玩家點擊（或按 Enter / 空白）才返回。"""
    frame = _Frame()
    clock = pygame.time.Clock()
    font = _make_font(48)
    btn = pygame.Rect(0, 0, 520, 130)
    btn.center = (SCREEN_W // 2, SCREEN_H // 2)
    mouse = (0, 0)
    music.play("none")
    pygame.key.stop_text_input()
    pygame.event.clear()
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            elif handle_window_event(event):
                continue
            elif event.type == pygame.MOUSEMOTION:
                mouse = screen_to_virtual(event.pos, clamp=True)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = screen_to_virtual(event.pos)
                if pos is not None and btn.collidepoint(pos):
                    sfx.play("pickup")
                    return
            elif event.type == pygame.KEYDOWN and event.key in (pygame.K_RETURN, pygame.K_SPACE):
                sfx.play("pickup")
                return
        target = frame.begin()
        target.blit(bg, (0, 0))
        shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        shade.fill((0, 0, 0, 120))
        target.blit(shade, (0, 0))
        hov = btn.collidepoint(mouse)
        _panel(target, btn, (60, 90, 160, 245) if not hov else (90, 125, 205, 250),
               GOLD if hov else TEXT, 6, 24)
        t = font.render(label, FONT_ANTIALIAS, TEXT)
        target.blit(t, t.get_rect(center=btn.center))
        frame.end()


def play_exam_chapter():
    """機考整章：找教室（失敗 → 按鈕重來）→ 紙條 → 密碼（失敗 → 按鈕回到拿到紙條處）。
    回傳獲得的道具 dict。"""
    while True:
        # ---- 階段一：找教室 ----
        play_dialogue("puzzle_find_room")
        if not run_find_room():
            play_dialogue("puzzle_fail", bg_override="bg_game_find_room")
            _wait_retry(_load_bg(BG_FIND_ROOM), "重新找教室")
            continue
        # ---- 階段三：紙條 + 密碼；失敗只回到拿到紙條處 ----
        while True:
            play_dialogue("puzzle_find_room_correct", events={"show_note": show_note})
            if run_computer():
                play_dialogue("puzzle_succeed")
                show_item_acquired()
                return {"name": DOC_NAME, "text": DOC_TEXT}
            play_dialogue("puzzle_fail")       # 密碼錯 5 次或超時
            _wait_retry(_load_bg(BG_COMPUTER), "重新解謎")


if __name__ == "__main__":
    init_display("Exam Test")
    play_exam_chapter()
    pygame.quit()
