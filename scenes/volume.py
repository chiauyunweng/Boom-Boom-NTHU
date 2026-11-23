"""左上角的音量控制：點喇叭圖示展開面板，拖曳滑桿調整「音樂」與「音效」音量。

所有場景都會經過 dialogue_scene._present（畫面輸出）與 handle_window_event（事件），
這兩個函式會呼叫這裡的 draw_overlay / handle_event，所以不需要在各場景個別加。
"""
import pygame

from scenes import music, sfx

# ---------------- 可調整設定 ----------------
MUSIC_MAX = 0.5               # 音樂滑桿拉滿時的實際音量
SFX_MAX = 1.0                 # 音效滑桿拉滿時的實際音量
MUSIC_DEFAULT = music.VOLUME / MUSIC_MAX      # 預設滑桿位置（0~1）
SFX_DEFAULT = sfx.VOLUME / SFX_MAX

ICON_RECT = pygame.Rect(24, 24, 72, 72)       # 1920x1080 虛擬座標
PANEL_RECT = pygame.Rect(24, 108, 480, 190)
TRACK_LEFT, TRACK_W = 120, 260                # 滑桿相對面板的 x 與長度
ROW_Y = (55, 135)                             # 兩條滑桿相對面板的 y
KNOB_R = 14

BG = (0, 0, 0, 170)
BORDER = (180, 180, 255)
ACCENT = (255, 230, 150)
TEXT = (255, 255, 255)
TRACK = (90, 90, 120)
# --------------------------------------------

_levels = {"music": MUSIC_DEFAULT, "sfx": SFX_DEFAULT}
_open = False
_dragging = None              # 正在拖曳的滑桿："music" / "sfx" / None
_hover_icon = False
_font = None


def _apply():
    music.set_volume(_levels["music"] * MUSIC_MAX)
    sfx.set_volume(_levels["sfx"] * SFX_MAX)


def _track_rect(row):
    y = PANEL_RECT.top + ROW_Y[row]
    return pygame.Rect(PANEL_RECT.left + TRACK_LEFT, y - 6, TRACK_W, 12)


def _set_from_x(name, x):
    row = 0 if name == "music" else 1
    tr = _track_rect(row)
    _levels[name] = min(1.0, max(0.0, (x - tr.left) / tr.width))
    _apply()


def handle_event(event, vpos):
    """vpos：事件位置轉成 1920x1080 虛擬座標（可為 None）。點到音量 UI 就吃掉事件、回傳 True。"""
    global _open, _dragging, _hover_icon
    if event.type == pygame.MOUSEMOTION:
        _hover_icon = bool(vpos) and ICON_RECT.collidepoint(vpos)
        if _dragging and vpos:
            _set_from_x(_dragging, vpos[0])
            return True
        return False
    if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
        if _dragging:
            _dragging = None
            sfx.play("advance")                     # 放開時用音效試聽目前音量
            return True
        return False
    if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
        return False
    if vpos and ICON_RECT.collidepoint(vpos):
        _open = not _open
        return True
    if not _open:
        return False
    if vpos and PANEL_RECT.collidepoint(vpos):
        for row, name in enumerate(("music", "sfx")):
            if _track_rect(row).inflate(30, 36).collidepoint(vpos):
                _dragging = name
                _set_from_x(name, vpos[0])
        return True
    _open = False                                   # 點面板外面：收起面板，這次點擊不傳給遊戲
    return True


def _draw_speaker(surf, rect, muted, hover):
    color = ACCENT if hover or _open else TEXT
    box = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(box, BG, box.get_rect(), border_radius=14)
    pygame.draw.rect(box, ACCENT if _open else BORDER, box.get_rect(), 3, border_radius=14)
    w, h = rect.size
    cx, cy = w // 2 - 8, h // 2
    pygame.draw.rect(box, color, (cx - 16, cy - 8, 10, 16))
    pygame.draw.polygon(box, color, [(cx - 6, cy - 8), (cx + 6, cy - 18), (cx + 6, cy + 18), (cx - 6, cy + 8)])
    if muted:
        pygame.draw.line(box, (255, 90, 90), (cx + 14, cy - 10), (cx + 30, cy + 10), 4)
        pygame.draw.line(box, (255, 90, 90), (cx + 30, cy - 10), (cx + 14, cy + 10), 4)
    else:
        for r in (12, 22):
            pygame.draw.arc(box, color, (cx + 4 - r, cy - r, 2 * r, 2 * r), -0.9, 0.9, 3)
    surf.blit(box, rect)


def _render():
    """把音量 UI 畫在一張 1920x1080 透明圖層上，回傳 (圖層, 有內容的範圍)。"""
    global _font
    if _font is None:
        from scenes.dialogue_scene import _make_font
        _font = _make_font(32)
    area = ICON_RECT.union(PANEL_RECT) if _open else ICON_RECT
    layer = pygame.Surface((area.right + 4, area.bottom + 4), pygame.SRCALPHA)
    muted = _levels["music"] == 0 and _levels["sfx"] == 0
    _draw_speaker(layer, ICON_RECT, muted, _hover_icon)
    if _open:
        panel = pygame.Surface(PANEL_RECT.size, pygame.SRCALPHA)
        pygame.draw.rect(panel, (10, 10, 25, 220), panel.get_rect(), border_radius=16)
        pygame.draw.rect(panel, BORDER, panel.get_rect(), 3, border_radius=16)
        layer.blit(panel, PANEL_RECT)
        for row, (name, label) in enumerate((("music", "音樂"), ("sfx", "音效"))):
            tr = _track_rect(row)
            lab = _font.render(label, False, TEXT)
            layer.blit(lab, lab.get_rect(midleft=(PANEL_RECT.left + 30, tr.centery)))
            pygame.draw.rect(layer, TRACK, tr, border_radius=6)
            fill = tr.copy()
            fill.width = int(tr.width * _levels[name])
            if fill.width:
                pygame.draw.rect(layer, ACCENT, fill, border_radius=6)
            knob = (tr.left + int(tr.width * _levels[name]), tr.centery)
            pygame.draw.circle(layer, TEXT, knob, KNOB_R)
            pygame.draw.circle(layer, ACCENT if _dragging == name else BORDER, knob, KNOB_R, 3)
            pct = _font.render(f"{round(_levels[name] * 100)}%", False, TEXT)
            layer.blit(pct, pct.get_rect(midleft=(tr.right + 26, tr.centery)))
    return layer


def draw_overlay(screen, scale, offset):
    """在實際視窗上（縮放後的畫面之上）畫音量 UI，不會弄髒遊戲的虛擬畫布。"""
    layer = _render()
    if scale != 1:
        layer = pygame.transform.smoothscale(
            layer, (max(1, int(layer.get_width() * scale)), max(1, int(layer.get_height() * scale))))
    screen.blit(layer, offset)
