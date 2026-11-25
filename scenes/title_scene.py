"""遊戲開始畫面（標題）與結尾畫面。

用法：
    from scenes.title_scene import run_title, run_ending
    if run_title() == "start": ...          # 回傳 "start" 或 "quit"
    run_ending(success=True)                # 回傳 "title"（回到標題）或 "quit"

操作：↑↓ / W S 選擇、Enter / Space 確定，也可以直接用滑鼠點按鈕。
"""
import math
import sys

import pygame

import achievements
from scenes import music, sfx
from scenes.dialogue_scene import (
    ASSET_DIR, FONT_ANTIALIAS, SCREEN_H, SCREEN_W, _make_font, _present, _wrap,
    get_virtual_screen, handle_window_event, init_display, screen_to_virtual,
)

# ---------------- 可調整設定 ----------------
GAME_TITLE = "BOOM BOOM NTHU"
GAME_SUBTITLE = "外星人矮為方的清大爆破計畫"
TITLE_BG = "bg_sky_night.png"
TITLE_BGM = "villain"

# 結局：success=True 是炸掉清大（ending_succeed），False 是被駐警隊帶走（alchemy_failed）
ENDINGS = {
    True: dict(
        label="結局一",
        name="清華的末日",
        text="矮為方成功完成了炸彈，清華大學迎來了最漫長的一夜。\n只是校長的校務評鑑，大概又要加班了。",
        bg="bg_sky_night.png", bgm="villain", color=(255, 200, 90)),
    False: dict(
        label="結局二",
        name="明天記得來上課",
        text="炸彈計畫功虧一簣，矮為方被駐警隊帶走。\n毀滅清大之前，得先撐過資工系的期末考。",
        bg="bg_game_find_room.png", bgm="campus", color=(140, 200, 255)),
}
CREDITS = "感謝遊玩！"

TITLE_SIZE = 128              # Unifont 是 16px 點陣字，用 16 的倍數最清楚
SUBTITLE_SIZE = 48
BUTTON_SIZE = 48
BODY_SIZE = 32

BUTTON_W, BUTTON_H, BUTTON_GAP = 420, 90, 28
FADE_MS = 700

TEXT_COLOR = (255, 255, 255)
SUB_COLOR = (220, 220, 220)
TITLE_COLOR = (255, 210, 90)
SHADOW_COLOR = (40, 10, 10)
BTN_FILL = (20, 20, 40, 190)
BTN_FILL_HOVER = (70, 50, 20, 220)
BTN_BORDER = (180, 180, 255)
BTN_BORDER_HOVER = (255, 230, 150)
# --------------------------------------------


def _quit():
    pygame.quit()
    sys.exit()


def _load_bg(name, shade_alpha):
    try:
        bg = pygame.image.load(str(ASSET_DIR / "bg" / name)).convert()
        if bg.get_size() != (SCREEN_W, SCREEN_H):
            bg = pygame.transform.scale(bg, (SCREEN_W, SCREEN_H))
    except (FileNotFoundError, pygame.error):
        bg = pygame.Surface((SCREEN_W, SCREEN_H))
        bg.fill((15, 15, 30))
    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, shade_alpha))
    bg.blit(shade, (0, 0))
    return bg


def _load_sprite(folder, name, height):
    """素材是 1920x1080 的整張圖層，裁掉透明邊後縮放到指定高度（最近鄰，保持像素感）。"""
    try:
        img = pygame.image.load(str(ASSET_DIR / folder / name)).convert_alpha()
    except (FileNotFoundError, pygame.error):
        return None
    img = img.subsurface(img.get_bounding_rect(min_alpha=1)).copy()
    scale = height / img.get_height()
    return pygame.transform.scale(img, (max(1, int(img.get_width() * scale)), height))


def _text(font, text, color, shadow=None, offset=4):
    surf = font.render(text, FONT_ANTIALIAS, color)
    if not shadow:
        return surf
    out = pygame.Surface((surf.get_width() + offset, surf.get_height() + offset), pygame.SRCALPHA)
    out.blit(font.render(text, FONT_ANTIALIAS, shadow), (offset, offset))
    out.blit(surf, (0, 0))
    return out


def _button_rects(count, top):
    rects = []
    for i in range(count):
        r = pygame.Rect(0, 0, BUTTON_W, BUTTON_H)
        r.midtop = (SCREEN_W // 2, top + i * (BUTTON_H + BUTTON_GAP))
        rects.append(r)
    return rects


def _draw_buttons(canvas, font, labels, rects, selected, t):
    for i, (label, rect) in enumerate(zip(labels, rects)):
        hover = i == selected
        box = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(box, BTN_FILL_HOVER if hover else BTN_FILL, box.get_rect(), border_radius=16)
        pygame.draw.rect(box, BTN_BORDER_HOVER if hover else BTN_BORDER, box.get_rect(),
                         width=4, border_radius=16)
        canvas.blit(box, rect)
        surf = font.render(label, FONT_ANTIALIAS, BTN_BORDER_HOVER if hover else TEXT_COLOR)
        canvas.blit(surf, surf.get_rect(center=rect.center))
        if hover:                                   # 選中的按鈕左邊有個會跳動的箭頭
            arrow = font.render("▶", FONT_ANTIALIAS, BTN_BORDER_HOVER)
            dx = int(6 * math.sin(t * 8))
            canvas.blit(arrow, arrow.get_rect(midright=(rect.left - 20 + dx, rect.centery)))


def _menu_loop(draw_scene, labels, rects, on_choose_sfx="success",
               fade_in=True, no_fade_indices=None, initial_selected=0):
    """通用選單迴圈：draw_scene(canvas, t) 畫背景與內容，回傳被選中的按鈕 index。"""
    no_fade_indices = set(no_fade_indices or ())
    clock = pygame.time.Clock()
    font = _make_font(BUTTON_SIZE)
    canvas = get_virtual_screen()
    black = pygame.Surface((SCREEN_W, SCREEN_H))
    black.fill((0, 0, 0))
    selected = initial_selected % len(labels)
    elapsed = 0 if fade_in else FADE_MS
    pygame.event.clear()

    while True:
        dt = clock.tick(60)
        elapsed += dt
        t = elapsed / 1000
        chosen = None

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            if handle_window_event(event):          # F11 / Alt+Enter 全螢幕、視窗縮放
                continue
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_UP, pygame.K_w):
                    selected = (selected - 1) % len(labels)
                    sfx.play("advance")
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    selected = (selected + 1) % len(labels)
                    sfx.play("advance")
                elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_SPACE):
                    chosen = selected
                elif event.key == pygame.K_ESCAPE:
                    chosen = len(labels) - 1        # Esc ＝ 最後一個選項（離開）
            elif event.type == pygame.MOUSEMOTION:
                pos = screen_to_virtual(event.pos, clamp=True)
                for i, r in enumerate(rects):
                    if r.collidepoint(pos) and i != selected:
                        selected = i
                        sfx.play("advance")
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = screen_to_virtual(event.pos)    # 點在黑邊上會是 None
                for i, r in enumerate(rects):
                    if pos and r.collidepoint(pos):
                        chosen = selected = i

        draw_scene(canvas, t)
        _draw_buttons(canvas, font, labels, rects, selected, t)
        if elapsed < FADE_MS:                       # 淡入
            black.set_alpha(int(255 * (1 - elapsed / FADE_MS)))
            canvas.blit(black, (0, 0))

        _present(pygame.display.get_surface(), canvas)
        pygame.display.flip()

        if chosen is not None:
            if chosen in no_fade_indices:
                sfx.play("paper")
                return chosen
            sfx.play(on_choose_sfx if chosen == 0 else "cancel")
            _fade_out(canvas, clock)
            return chosen


def _show_achievements_modal(draw_scene):
    """主畫面「成就」彈窗：展示所有成就（已解鎖彩色高亮／未解鎖灰階上鎖）並支援滾動與關閉。"""
    clock = pygame.time.Clock()
    canvas = get_virtual_screen()
    header_font = _make_font(48)
    title_font = _make_font(48)
    body_font = _make_font(32)
    items = achievements.get_all()
    unlocked_cnt = sum(1 for a in items if a["unlocked"])

    panel = pygame.Rect(0, 0, 1280, 790)
    panel.center = (SCREEN_W // 2, SCREEN_H // 2)
    close_x = pygame.Rect(0, 0, 56, 56)
    close_x.topright = (panel.right - 24, panel.top + 24)
    close_btn = pygame.Rect(0, 0, 260, 72)
    close_btn.midbottom = (panel.centerx, panel.bottom - 28)

    list_area = pygame.Rect(panel.left + 48, panel.top + 132, panel.width - 96, panel.height - 252)
    card_h, card_gap = 156, 20
    content_h = max(0, len(items) * (card_h + card_gap) - card_gap)
    max_scroll = max(0, content_h - list_area.height)
    scroll_y = 0

    shade = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
    shade.fill((0, 0, 0, 185))
    mouse = (0, 0)
    elapsed = 0
    pygame.event.clear()

    while True:
        dt = clock.tick(60)
        elapsed += dt
        t = elapsed / 1000

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
            if handle_window_event(event):
                continue
            if event.type == pygame.MOUSEMOTION:
                mouse = screen_to_virtual(event.pos, clamp=True)
            elif event.type == pygame.MOUSEWHEEL:
                scroll_y = max(0, min(max_scroll, scroll_y - event.y * 48))
            elif event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN, pygame.K_SPACE):
                    sfx.play("cancel")
                    return
                elif event.key in (pygame.K_DOWN, pygame.K_s):
                    scroll_y = min(max_scroll, scroll_y + 48)
                elif event.key in (pygame.K_UP, pygame.K_w):
                    scroll_y = max(0, scroll_y - 48)
            elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                pos = screen_to_virtual(event.pos)
                if pos is None:
                    continue
                if close_x.collidepoint(pos) or close_btn.collidepoint(pos) or not panel.collidepoint(pos):
                    sfx.play("cancel")
                    return

        draw_scene(canvas, t)
        canvas.blit(shade, (0, 0))

        # 彈窗主體
        box = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(box, (18, 22, 38, 244), box.get_rect(), border_radius=22)
        pygame.draw.rect(box, BTN_BORDER, box.get_rect(), 4, border_radius=22)
        canvas.blit(box, panel)

        # 標題與解鎖統計
        hdr = header_font.render("成就列表", FONT_ANTIALIAS, TITLE_COLOR)
        canvas.blit(hdr, (panel.left + 52, panel.top + 32))
        prog = body_font.render(f"已解鎖：{unlocked_cnt} / {len(items)}", FONT_ANTIALIAS, SUB_COLOR)
        canvas.blit(prog, prog.get_rect(midright=(close_x.left - 28, panel.top + 56)))
        pygame.draw.line(canvas, (90, 95, 130),
                         (panel.left + 44, panel.top + 104), (panel.right - 44, panel.top + 104), 3)

        # 右上角 [X]
        hx = close_x.collidepoint(mouse)
        pygame.draw.rect(canvas, (210, 75, 75) if hx else (150, 52, 52), close_x, border_radius=12)
        pygame.draw.rect(canvas, TEXT_COLOR, close_x, 3, border_radius=12)
        xc = close_x.inflate(-24, -24)
        pygame.draw.line(canvas, TEXT_COLOR, xc.topleft, xc.bottomright, 5)
        pygame.draw.line(canvas, TEXT_COLOR, xc.topright, xc.bottomleft, 5)

        # 成就卡片清單（支援裁切與捲動）
        prev_clip = canvas.get_clip()
        canvas.set_clip(list_area)
        for idx, ach in enumerate(items):
            cy = list_area.top + idx * (card_h + card_gap) - scroll_y
            card_rect = pygame.Rect(list_area.left, cy, list_area.width, card_h)
            if card_rect.bottom < list_area.top or card_rect.top > list_area.bottom:
                continue

            unlocked = ach["unlocked"]
            card_surf = pygame.Surface(card_rect.size, pygame.SRCALPHA)
            fill_col = (54, 46, 24, 236) if unlocked else (30, 33, 44, 224)
            border_col = BTN_BORDER_HOVER if unlocked else (95, 100, 118)
            pygame.draw.rect(card_surf, fill_col, card_surf.get_rect(), border_radius=16)
            pygame.draw.rect(card_surf, border_col, card_surf.get_rect(), 3, border_radius=16)

            # 左側圖示框
            badge = pygame.Rect(24, (card_h - 100) // 2, 100, 100)
            badge_bg = (34, 28, 16, 255) if unlocked else (22, 24, 32, 255)
            pygame.draw.rect(card_surf, badge_bg, badge, border_radius=14)
            pygame.draw.rect(card_surf, border_col, badge, 3, border_radius=14)
            achievements.draw_trophy_icon(card_surf, badge, unlocked=unlocked)

            # 成就名稱與狀態標籤
            tx = badge.right + 28
            disp_title = ach["title"] if unlocked else "？？？"
            t_col = TITLE_COLOR if unlocked else (150, 155, 170)
            t_surf = title_font.render(disp_title, FONT_ANTIALIAS, t_col)
            card_surf.blit(t_surf, (tx, 22))

            tag_text = "已解鎖" if unlocked else "未解鎖"
            tag_bg = (80, 145, 70) if unlocked else (75, 78, 92)
            tag_surf = body_font.render(tag_text, FONT_ANTIALIAS, TEXT_COLOR if unlocked else (185, 190, 200))
            tag_rect = tag_surf.get_rect(topright=(card_rect.width - 28, 24))
            pygame.draw.rect(card_surf, tag_bg, tag_rect.inflate(24, 10), border_radius=10)
            card_surf.blit(tag_surf, tag_rect)

            # 描述文字（未解鎖時顯示條件提示與目前進度）
            if unlocked:
                desc_text = ach["description"]
                desc_col = (240, 236, 220)
            else:
                hint_txt = ach.get("hint", "達成隱藏條件即可解鎖")
                if "target_value" in ach:
                    cur = min(ach.get("progress", 0), ach["target_value"])
                    desc_text = f"解鎖條件：{hint_txt}（目前進度：{cur} / {ach['target_value']}）"
                else:
                    desc_text = f"解鎖條件：{hint_txt}"
                desc_col = (145, 150, 165)

            dy = 82
            for ln in _wrap(desc_text, body_font, card_rect.width - tx - 28)[:2]:
                if ln:
                    card_surf.blit(body_font.render(ln, FONT_ANTIALIAS, desc_col), (tx, dy))
                dy += body_font.get_linesize() + 4

            canvas.blit(card_surf, card_rect)
        canvas.set_clip(prev_clip)

        # 底部關閉按鈕
        hc = close_btn.collidepoint(mouse)
        cb_surf = pygame.Surface(close_btn.size, pygame.SRCALPHA)
        pygame.draw.rect(cb_surf, BTN_FILL_HOVER if hc else BTN_FILL, cb_surf.get_rect(), border_radius=14)
        pygame.draw.rect(cb_surf, BTN_BORDER_HOVER if hc else BTN_BORDER, cb_surf.get_rect(), 3, border_radius=14)
        canvas.blit(cb_surf, close_btn)
        ct = body_font.render("關閉（Esc）", FONT_ANTIALIAS, BTN_BORDER_HOVER if hc else TEXT_COLOR)
        canvas.blit(ct, ct.get_rect(center=close_btn.center))

        _present(pygame.display.get_surface(), canvas)
        pygame.display.flip()


def _fade_out(canvas, clock, ms=500):
    black = pygame.Surface((SCREEN_W, SCREEN_H))
    black.fill((0, 0, 0))
    snapshot = canvas.copy()
    elapsed = 0
    while elapsed < ms:
        elapsed += clock.tick(60)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                _quit()
        canvas.blit(snapshot, (0, 0))
        black.set_alpha(int(255 * min(1, elapsed / ms)))
        canvas.blit(black, (0, 0))
        _present(pygame.display.get_surface(), canvas)
        pygame.display.flip()
    pygame.event.clear()


def run_title():
    """標題畫面。回傳 "start"（開始遊戲）或 "quit"。"""
    music.play(TITLE_BGM)
    bg = _load_bg(TITLE_BG, 90)
    hero = _load_sprite("char", "char_short_and_square_idle.png", 520)
    bomb = _load_sprite("obj", "obj_bomb.png", 360)
    title = _text(_make_font(TITLE_SIZE), GAME_TITLE, TITLE_COLOR, SHADOW_COLOR, 8)
    subtitle = _text(_make_font(SUBTITLE_SIZE), GAME_SUBTITLE, SUB_COLOR, (0, 0, 0))
    hint = _make_font(BODY_SIZE).render("↑↓ 選擇　Enter / 點擊 確定", FONT_ANTIALIAS, (170, 170, 170))
    labels = ["開始遊戲", "成就", "離開遊戲"]
    rects = _button_rects(len(labels), 560)

    def draw(canvas, t):
        canvas.blit(bg, (0, 0))
        if hero:                                    # 矮為方在左下輕輕上下浮動
            canvas.blit(hero, hero.get_rect(bottomleft=(110, SCREEN_H + int(8 * math.sin(t * 2)))))
        if bomb:                                    # 炸彈在右下微微搖晃
            rot = pygame.transform.rotate(bomb, 4 * math.sin(t * 3))
            canvas.blit(rot, rot.get_rect(midbottom=(SCREEN_W - 300, SCREEN_H - 30)))
        y = 175 + int(6 * math.sin(t * 1.5))
        canvas.blit(title, title.get_rect(midtop=(SCREEN_W // 2, y)))
        canvas.blit(subtitle, subtitle.get_rect(midtop=(SCREEN_W // 2, y + title.get_height() + 30)))
        canvas.blit(hint, hint.get_rect(midbottom=(SCREEN_W // 2, SCREEN_H - 40)))

    first_entry = True
    selected = 0
    while True:
        choice = _menu_loop(
            draw, labels, rects,
            fade_in=first_entry,
            no_fade_indices={1},
            initial_selected=selected,
        )
        first_entry = False
        if choice == 0:
            return "start"
        if choice == 1:
            selected = 1
            _show_achievements_modal(draw)
            continue
        return "quit"


def run_ending(success):
    """結尾畫面：顯示達成的結局。回傳 "title"（回到標題）或 "quit"。"""
    info = ENDINGS[bool(success)]
    music.play(info["bgm"])
    bg = _load_bg(info["bg"], 170)
    big = _make_font(TITLE_SIZE)
    label = _text(_make_font(SUBTITLE_SIZE), info["label"], SUB_COLOR, (0, 0, 0))
    name = _text(big, f"「{info['name']}」", info["color"], SHADOW_COLOR, 8)
    body_font = _make_font(BODY_SIZE)
    body = [body_font.render(line, FONT_ANTIALIAS, TEXT_COLOR) for line in info["text"].split("\n")]
    the_end = _text(_make_font(64), "THE END", TITLE_COLOR, SHADOW_COLOR, 6)
    thanks = body_font.render(CREDITS, FONT_ANTIALIAS, SUB_COLOR)
    labels = ["回到標題", "離開遊戲"]
    rects = _button_rects(len(labels), 760)

    def draw(canvas, t):
        canvas.blit(bg, (0, 0))
        canvas.blit(the_end, the_end.get_rect(midtop=(SCREEN_W // 2, 90)))
        canvas.blit(label, label.get_rect(midtop=(SCREEN_W // 2, 220)))
        canvas.blit(name, name.get_rect(midtop=(SCREEN_W // 2, 290)))
        y = 480
        for surf in body:
            canvas.blit(surf, surf.get_rect(midtop=(SCREEN_W // 2, y)))
            y += surf.get_height() + 16
        canvas.blit(thanks, thanks.get_rect(midtop=(SCREEN_W // 2, y + 30)))

    return "title" if _menu_loop(draw, labels, rects, on_choose_sfx="advance") == 0 else "quit"


if __name__ == "__main__":
    init_display("Title Test")
    while run_title() == "start":
        if run_ending(True) == "quit" or run_ending(False) == "quit":
            break
    pygame.quit()
