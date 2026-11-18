"""化學館煉金小遊戲：把釣到的物品依正確順序拖進中央的實驗裝置。

流程（由 play_alchemy_chapter 串起）：
    alchemy_find_clue → alchemy_device → 小遊戲
        成功        → alchemy_succeed → ending_succeed
        放錯順序    → 倒數 -10 秒，物品全部退回，重來（只有第一次放錯會播 alchemy_wrong_procedure）
        時間到      → alchemy_failed

用法：
    from scenes.alchemy_scene import play_alchemy_chapter, run_alchemy
    play_alchemy_chapter(caught_items)   # caught_items：釣魚關卡得到的物品名稱 list
"""
import sys

import pygame

from scenes import sfx
from scenes.dialogue_scene import (
    ASSET_DIR, FONT_ANTIALIAS, SCREEN_H, SCREEN_W, _make_font, _present, _wrap, play_dialogue,
)

# ---------------- 可調整設定 ----------------
TIME_LIMIT_SEC = 120          # 總時間 2 分鐘
PENALTY_SEC = 10              # 放錯一次扣 10 秒

# 正確放入順序（漁父的包包用不到）
CORRECT_ORDER = [
    "高姐姐的腳踏車",
    "氫化鋁鋰",
    "學生腐爛的夢想",
    "DYY的銅板",
]

# 說明書內容（放入順序的謎題）
MANUAL_TITLE = "實驗裝置使用說明書"
MANUAL_TEXT = (
    "本裝置須依下列步驟放入材料，順序錯誤將觸發警報。\n"
    "\n"
    "一、能載人在校園裡奔馳、卻總是被拖吊的，最先放入。\n"
    "二、遇水會劇烈反應的白色粉末，緊接其後。\n"
    "三、期末過後被丟棄、散發著酸臭味的東西，放在第三。\n"
    "四、最後，投入一枚印著熟悉面孔的硬幣。\n"
    "\n"
    "※ 並非所有物品都需要放入。"
)
MANUAL_RECT = pygame.Rect(0, 0, 1100, 720)
MANUAL_RECT.center = (SCREEN_W // 2, SCREEN_H // 2)
PAPER_COLOR = (245, 235, 210)
INK_COLOR = (60, 40, 30)

# 物品名稱 → assets/obj 底下的圖檔
ITEM_IMAGES = {
    "高姐姐的腳踏車": "obj_bicycle.PNG",
    "DYY的銅板": "IMG_0436.PNG",
    "學生腐爛的夢想": "obj_garbage.PNG",
    "氫化鋁鋰": "IMG_0435.PNG",
    "漁父的包包": "obj_fisherman_bag.PNG",
}
ALL_ITEMS = list(ITEM_IMAGES)

BG_NAME = "bg_dlg_go_alchemy.png"

SLOT_SIZE = 150               # 上方物品欄每格大小
SLOT_GAP = 30
SLOT_TOP = 40
ICON_PAD = 14                 # 圖示與格子邊緣的距離
DRAG_SIZE = 200               # 拖曳中的物品顯示大小
PLACED_SIZE = 90              # 裝置內已放入物品的小圖示

DEVICE_RECT = pygame.Rect(0, 0, 560, 460)
DEVICE_RECT.center = (SCREEN_W // 2, 600)

MANUAL_ICON_RECT = pygame.Rect(0, 0, 150, 190)    # 裝置右側可點擊的說明書
MANUAL_ICON_RECT.midleft = (DEVICE_RECT.right + 70, DEVICE_RECT.centery - 20)

TEXT_COLOR = (255, 255, 255)
HINT_COLOR = (220, 220, 220)
WARN_COLOR = (255, 90, 90)
SLOT_COLOR = (20, 20, 40, 170)
SLOT_BORDER = (180, 180, 255)
DEVICE_COLOR = (30, 40, 70, 200)
DEVICE_BORDER = (120, 200, 255)
DEVICE_HOVER = (255, 230, 150)
# --------------------------------------------


def _quit():
    pygame.quit()
    sys.exit()


def _load_icon(name, size):
    """載入物品圖、裁掉透明邊，等比縮放到 size x size 以內。"""
    path = ASSET_DIR / "obj" / ITEM_IMAGES[name]
    try:
        img = pygame.image.load(str(path)).convert_alpha()
    except (FileNotFoundError, pygame.error):
        print(f"[alchemy_scene] 找不到素材：{path}")
        img = pygame.Surface((size, size), pygame.SRCALPHA)
        img.fill((200, 80, 200))
        return img
    img = img.subsurface(img.get_bounding_rect(min_alpha=1)).copy()
    scale = min(size / img.get_width(), size / img.get_height())
    return pygame.transform.smoothscale(
        img, (max(1, int(img.get_width() * scale)), max(1, int(img.get_height() * scale))))


def _load_bg():
    try:
        bg = pygame.image.load(str(ASSET_DIR / "bg" / BG_NAME)).convert()
    except (FileNotFoundError, pygame.error):
        bg = pygame.Surface((SCREEN_W, SCREEN_H))
        bg.fill((15, 15, 25))
    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 150))                   # 背景壓暗，讓物品與裝置更明顯
    bg.blit(shade, (0, 0))
    return bg


def _to_logical(pos):
    """視窗座標 → 1920x1080 邏輯座標（使用 pygame.SCALED 時兩者相同）。"""
    win_w, win_h = pygame.display.get_surface().get_size()
    if (win_w, win_h) == (SCREEN_W, SCREEN_H):
        return pos
    scale = min(win_w / SCREEN_W, win_h / SCREEN_H)
    ox = (win_w - SCREEN_W * scale) / 2
    oy = (win_h - SCREEN_H * scale) / 2
    return int((pos[0] - ox) / scale), int((pos[1] - oy) / scale)


def _panel(target, rect, fill, border, width=4, radius=18):
    surf = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(surf, fill, surf.get_rect(), border_radius=radius)
    target.blit(surf, rect.topleft)
    pygame.draw.rect(target, border, rect, width, border_radius=radius)


def _draw_manual_icon(target, font, hover):
    r = MANUAL_ICON_RECT
    fold = 36
    pts = [r.topleft, (r.right - fold, r.top), (r.right, r.top + fold), r.bottomright, r.bottomleft]
    pygame.draw.polygon(target, PAPER_COLOR, pts)
    pygame.draw.polygon(target, (200, 185, 150),
                        [(r.right - fold, r.top), (r.right - fold, r.top + fold), (r.right, r.top + fold)])
    pygame.draw.polygon(target, DEVICE_HOVER if hover else INK_COLOR, pts, 5 if hover else 3)
    for k in range(5):
        y = r.top + 60 + k * 24
        pygame.draw.line(target, (150, 130, 100), (r.left + 20, y), (r.right - 20 - (k % 2) * 30, y), 3)
    label = font.render("說明書", FONT_ANTIALIAS, DEVICE_HOVER if hover else TEXT_COLOR)
    target.blit(label, label.get_rect(midtop=(r.centerx, r.bottom + 12)))


def _draw_manual(target, title_font, font):
    """在畫面中央畫出攤開的說明書（含半透明遮罩）。"""
    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 170))
    target.blit(shade, (0, 0))
    r = MANUAL_RECT
    pygame.draw.rect(target, PAPER_COLOR, r, border_radius=12)
    pygame.draw.rect(target, INK_COLOR, r, 6, border_radius=12)

    title = title_font.render(MANUAL_TITLE, FONT_ANTIALIAS, INK_COLOR)
    target.blit(title, title.get_rect(midtop=(r.centerx, r.top + 50)))
    pygame.draw.line(target, INK_COLOR, (r.left + 80, r.top + 125), (r.right - 80, r.top + 125), 3)

    y = r.top + 165
    for ln in _wrap(MANUAL_TEXT, font, r.width - 160):
        if ln:
            target.blit(font.render(ln, FONT_ANTIALIAS, INK_COLOR), (r.left + 80, y))
        y += font.get_linesize() + 14

    hint = font.render("點擊任意處或按空白鍵關閉", FONT_ANTIALIAS, (130, 110, 90))
    target.blit(hint, hint.get_rect(midbottom=(r.centerx, r.bottom - 30)))


def _is_close_event(event):
    return (
        (event.type == pygame.MOUSEBUTTONDOWN and event.button == 1)
        or (event.type == pygame.KEYDOWN
            and event.key in (pygame.K_SPACE, pygame.K_ESCAPE, pygame.K_RETURN))
        or (event.type == pygame.TEXTINPUT and event.text == " ")
    )


def show_manual():
    """獨立顯示說明書（劇情中拿起說明書時用），蓋在目前畫面上，關閉後返回。"""
    screen = pygame.display.get_surface()
    backdrop = screen.copy()
    if backdrop.get_size() != (SCREEN_W, SCREEN_H):
        backdrop = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
        backdrop.fill((0, 0, 0))
    canvas = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
    title_font, font = _make_font(48), _make_font(32)
    clock = pygame.time.Clock()
    pygame.event.clear()
    sfx.play("paper")
    while True:
        clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            if _is_close_event(event):
                sfx.play("paper")
                return
        screen = pygame.display.get_surface()
        direct = screen.get_size() == (SCREEN_W, SCREEN_H)
        target = screen if direct else canvas
        target.blit(backdrop, (0, 0))
        _draw_manual(target, title_font, font)
        if not direct:
            _present(screen, canvas)
        pygame.display.flip()


def run_alchemy(items=None):
    """執行小遊戲。成功回傳 True；時間到回傳 False。
    放錯順序時會自動播放 alchemy_wrong_procedure 並扣時間。"""
    items = [i for i in (items or ALL_ITEMS) if i in ITEM_IMAGES]
    missing = [i for i in CORRECT_ORDER if i not in items]
    if missing:
        print(f"[alchemy_scene] 注意：缺少正確順序所需的物品 {missing}，此關不可能成功")

    screen = pygame.display.get_surface()
    canvas = pygame.Surface((SCREEN_W, SCREEN_H)).convert()
    clock = pygame.time.Clock()

    bg = _load_bg()
    font = _make_font(32)
    big_font = _make_font(48)
    icons = {n: _load_icon(n, SLOT_SIZE - 2 * ICON_PAD) for n in items}
    drag_icons = {n: _load_icon(n, DRAG_SIZE) for n in items}
    placed_icons = {n: _load_icon(n, PLACED_SIZE) for n in items}

    # 上方物品欄：置中排成一排
    row_w = len(items) * SLOT_SIZE + (len(items) - 1) * SLOT_GAP
    left = (SCREEN_W - row_w) // 2
    slots = {n: pygame.Rect(left + k * (SLOT_SIZE + SLOT_GAP), SLOT_TOP, SLOT_SIZE, SLOT_SIZE)
             for k, n in enumerate(items)}

    remaining_ms = TIME_LIMIT_SEC * 1000
    placed = []                 # 已放入裝置的物品（依放入順序）
    dragging = None             # 正在拖曳的物品名稱
    drag_offset = (0, 0)
    mouse = (0, 0)
    penalty_flash_ms = 0        # 顯示「-10 秒」的剩餘時間
    success_ms = None           # 成功後停留一下再結束
    manual_open = False         # 閱讀說明書時倒數照常進行
    wrong_count = 0             # 放錯次數
    last_tick = None            # 最後 10 秒每秒響一次

    pygame.key.stop_text_input()
    pygame.event.clear()

    while True:
        dt = clock.tick(60)
        if success_ms is None:
            remaining_ms -= dt
        penalty_flash_ms = max(0, penalty_flash_ms - dt)

        if remaining_ms <= 0:
            sfx.play("timeout")
            return False
        secs_left = (remaining_ms + 999) // 1000
        if success_ms is None and secs_left <= 10 and secs_left != last_tick:
            last_tick = secs_left
            sfx.play("tick")
        if success_ms is not None:
            success_ms -= dt
            if success_ms <= 0:
                return True

        wrong = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            elif event.type == pygame.MOUSEMOTION:
                mouse = _to_logical(event.pos)
            elif success_ms is not None:
                continue
            elif manual_open:
                if _is_close_event(event):
                    manual_open = False
                    sfx.play("paper")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                mouse = _to_logical(event.pos)
                if MANUAL_ICON_RECT.collidepoint(mouse):
                    manual_open = True
                    sfx.play("paper")
                    continue
                for n, r in slots.items():
                    if n not in placed and r.collidepoint(mouse):
                        dragging = n
                        drag_offset = (mouse[0] - r.centerx, mouse[1] - r.centery)
                        sfx.play("pickup")
                        break
            elif event.type == pygame.MOUSEBUTTONUP and event.button == 1 and dragging:
                mouse = _to_logical(event.pos)
                if DEVICE_RECT.collidepoint(mouse):
                    step = len(placed)
                    if step < len(CORRECT_ORDER) and dragging == CORRECT_ORDER[step]:
                        placed.append(dragging)
                        if len(placed) == len(CORRECT_ORDER):
                            success_ms = 1200
                            sfx.play("success")
                        else:
                            sfx.play("drop")
                    else:
                        wrong = True
                else:
                    sfx.play("cancel")
                dragging = None        # 沒放進裝置就自動回到物品欄

        if wrong:
            # 放錯：扣時間，物品全部退回；只有第一次放錯會播放警報劇情（期間不計時）
            wrong_count += 1
            if wrong_count == 1:
                play_dialogue("alchemy_wrong_procedure")   # 第一句會響警報（JSON 的 "sfx": "alarm"）
            else:
                sfx.play("alarm")
                clock.tick()           # 丟掉劇情期間累積的時間
                pygame.key.stop_text_input()
                pygame.event.clear()
            remaining_ms -= PENALTY_SEC * 1000
            penalty_flash_ms = 1500
            placed.clear()
            if remaining_ms <= 0:
                sfx.play("timeout")
                return False
            continue

        # ---------------- 繪製 ----------------
        screen = pygame.display.get_surface()
        direct = screen.get_size() == (SCREEN_W, SCREEN_H)
        target = screen if direct else canvas
        target.blit(bg, (0, 0))

        # 物品欄
        hover_name = None
        for n, r in slots.items():
            _panel(target, r, SLOT_COLOR, SLOT_BORDER, 3, 14)
            if n in placed or n == dragging:
                continue
            ic = icons[n]
            target.blit(ic, ic.get_rect(center=r.center))
            if r.collidepoint(mouse) and not dragging:
                hover_name = n
        if hover_name:
            label = font.render(hover_name, FONT_ANTIALIAS, TEXT_COLOR)
            r = slots[hover_name]
            lr = label.get_rect(midtop=(r.centerx, r.bottom + 12))
            lr.clamp_ip(target.get_rect())
            _panel(target, lr.inflate(24, 12), (0, 0, 0, 200), SLOT_BORDER, 2, 8)
            target.blit(label, lr)

        # 實驗裝置
        over_device = dragging and DEVICE_RECT.collidepoint(mouse)
        _panel(target, DEVICE_RECT, DEVICE_COLOR,
               DEVICE_HOVER if over_device else DEVICE_BORDER, 6, 28)
        title = big_font.render("實驗裝置", FONT_ANTIALIAS, TEXT_COLOR)
        target.blit(title, title.get_rect(midtop=(DEVICE_RECT.centerx, DEVICE_RECT.top + 30)))
        progress = font.render(f"已放入 {len(placed)} / {len(CORRECT_ORDER)}",
                               FONT_ANTIALIAS, HINT_COLOR)
        target.blit(progress, progress.get_rect(
            midbottom=(DEVICE_RECT.centerx, DEVICE_RECT.bottom - 30)))
        if placed:
            gap = 12
            w = len(placed) * PLACED_SIZE + (len(placed) - 1) * gap
            x = DEVICE_RECT.centerx - w // 2
            for n in placed:
                ic = placed_icons[n]
                target.blit(ic, ic.get_rect(center=(x + PLACED_SIZE // 2, DEVICE_RECT.centery)))
                x += PLACED_SIZE + gap
        if success_ms is not None:
            ok = big_font.render("成功！", FONT_ANTIALIAS, DEVICE_HOVER)
            target.blit(ok, ok.get_rect(center=(DEVICE_RECT.centerx, DEVICE_RECT.centery + 90)))

        _draw_manual_icon(target, font,
                          not dragging and not manual_open and MANUAL_ICON_RECT.collidepoint(mouse))

        # 倒數計時（右上角）
        secs = max(0, (remaining_ms + 999) // 1000)
        t_color = WARN_COLOR if secs <= 20 else TEXT_COLOR
        timer = big_font.render(f"{secs // 60:02d}:{secs % 60:02d}", FONT_ANTIALIAS, t_color)
        target.blit(timer, timer.get_rect(topright=(SCREEN_W - 50, SLOT_TOP)))
        if penalty_flash_ms:
            pen = big_font.render(f"-{PENALTY_SEC} 秒", FONT_ANTIALIAS, WARN_COLOR)
            target.blit(pen, pen.get_rect(topright=(SCREEN_W - 50, SLOT_TOP + 64)))

        # 操作提示
        hint = font.render("將物品拖曳到實驗裝置中，依照說明書的順序放入（點擊說明書可閱讀）",
                           FONT_ANTIALIAS, HINT_COLOR)
        target.blit(hint, hint.get_rect(midbottom=(SCREEN_W // 2, SCREEN_H - 50)))

        # 拖曳中的物品畫在最上層
        if dragging:
            ic = drag_icons[dragging]
            target.blit(ic, ic.get_rect(center=(mouse[0] - drag_offset[0],
                                                mouse[1] - drag_offset[1])))

        if manual_open:
            _draw_manual(target, big_font, font)
            target.blit(timer, timer.get_rect(topright=(SCREEN_W - 50, SLOT_TOP)))  # 閱讀時仍看得到時間

        if not direct:
            _present(screen, canvas)
        pygame.display.flip()


def play_alchemy_chapter(items=None):
    """化學館整章：劇情 → 小遊戲 → 依結果播放結局。成功回傳 True。"""
    play_dialogue("alchemy_find_clue")
    play_dialogue("alchemy_device", events={"show_manual": show_manual})
    if run_alchemy(items):
        play_dialogue("alchemy_succeed")
        play_dialogue("ending_succeed")
        return True
    play_dialogue("alchemy_failed")
    return False


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Alchemy Test")
    play_alchemy_chapter()
    pygame.quit()
