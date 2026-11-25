"""成就系統（Achievement System）：成就定義、JSON 本地存檔、統計追蹤與 Steam 風格滑入通知。

擴充新成就：
    只要在 ACHIEVEMENT_DEFS 新增一筆 dict，並在對應遊戲事件呼叫 unlock("<id>") 即可。

用法：
    import achievements
    achievements.record_tle()          # 累計 TLE 次數，達 5 次時自動解鎖「二退程設」
    achievements.unlock("withdraw_cs") # 直接解鎖指定成就（已解鎖過不會重複觸發）
    achievements.get_all()             # 取得所有成就清單（含 unlocked 狀態）
"""
from collections import deque
import json
from pathlib import Path

import pygame

from scenes import sfx

# ---------------- 路徑與設定 ----------------
BASE_DIR = Path(__file__).resolve().parent
SAVE_PATH = BASE_DIR / "save_achievements.json"

SCREEN_W, SCREEN_H = 1920, 1080

# 統一成就定義表（日後新增成就直接在此擴充）
ACHIEVEMENT_DEFS = [
    {
        "id": "withdraw_cs",
        "title": "二退程設",
        "description": "累計觸發 5 次 TLE，看來這學期只能先二退程設了...",
        "hint": "在機考關卡中累計觸發 5 次 TLE",
        "target_stat": "tle_count",
        "target_value": 5,
    },
]

# Steam 風格右側滑入通知（Toast）外觀與時間設定
TOAST_W, TOAST_H = 560, 136
TOAST_MARGIN_RIGHT = 32
TOAST_MARGIN_BOTTOM = 36
SLIDE_IN_MS = 380
HOLD_MS = 3500                # 停留 3.5 秒（3~4 秒）
SLIDE_OUT_MS = 380
TOAST_TOTAL_MS = SLIDE_IN_MS + HOLD_MS + SLIDE_OUT_MS

TOAST_BG = (22, 28, 40, 242)
TOAST_BORDER = (255, 210, 95)
TOAST_HEADER_COLOR = (255, 215, 105)
TOAST_TITLE_COLOR = (255, 255, 255)
TOAST_BADGE_BG = (45, 38, 22, 255)
# --------------------------------------------

_unlocked = set()
_stats = {"tle_count": 0}
_toast_queue = deque()
_active_toast = None          # {"achievement": dict, "start_ms": int, "card": Surface}
_fonts = {}


def _load():
    """從本地 JSON 存檔載入已解鎖成就與統計資料。"""
    global _unlocked, _stats
    _unlocked = set()
    _stats = {"tle_count": 0}
    if not SAVE_PATH.exists():
        return
    try:
        with open(SAVE_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            valid_ids = {a["id"] for a in ACHIEVEMENT_DEFS}
            _unlocked = {aid for aid in data.get("unlocked", []) if aid in valid_ids}
            raw_stats = data.get("stats", {})
            if isinstance(raw_stats, dict):
                _stats.update(raw_stats)
    except (OSError, ValueError) as e:
        print(f"[achievements] 讀取存檔失敗（將使用預設狀態）：{e}")


def _save():
    """將已解鎖成就與統計資料寫入本地 JSON 存檔。"""
    payload = {
        "unlocked": sorted(_unlocked),
        "stats": _stats,
    }
    try:
        with open(SAVE_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError as e:
        print(f"[achievements] 寫入存檔失敗：{e}")


def get_all():
    """回傳所有成就的清單（每筆包含 id, title, description, hint, unlocked 等欄位）。"""
    out = []
    for item in ACHIEVEMENT_DEFS:
        entry = dict(item)
        entry["unlocked"] = item["id"] in _unlocked
        stat_key = item.get("target_stat")
        if stat_key:
            entry["progress"] = int(_stats.get(stat_key, 0))
        out.append(entry)
    return out


def get_stats():
    """回傳目前累計統計資料的複本。"""
    return dict(_stats)


def is_unlocked(achievement_id):
    return achievement_id in _unlocked


def _find_def(achievement_id):
    for item in ACHIEVEMENT_DEFS:
        if item["id"] == achievement_id:
            return item
    return None


def unlock(achievement_id):
    """解鎖指定成就；若為首次解鎖則存檔並排入通知佇列，回傳 True；已解鎖或無效則回傳 False。"""
    ach = _find_def(achievement_id)
    if ach is None or achievement_id in _unlocked:
        return False
    _unlocked.add(achievement_id)
    _save()
    _toast_queue.append(dict(ach))
    print(f"[achievements] 解鎖成就：{ach['title']} ({achievement_id})")
    return True


def record_tle():
    """記錄一次 TLE，累計達 5 次時自動解鎖「二退程設」。回傳是否於本次解鎖新成就。"""
    _stats["tle_count"] = int(_stats.get("tle_count", 0)) + 1
    _save()
    count = _stats["tle_count"]
    print(f"[achievements] 累計 TLE 次數：{count}")
    if count >= 5:
        return unlock("withdraw_cs")
    return False


# ---------------- 圖示與通知繪製 ----------------
def draw_trophy_icon(surface, rect, unlocked=True):
    """在指定 rect 內繪製精緻的獎盃（已解鎖）或鎖頭（未解鎖）徽章圖示。"""
    cx, cy = rect.centerx, rect.centery
    if unlocked:
        gold = (255, 212, 82)
        gold_hi = (255, 240, 165)
        gold_dark = (185, 132, 32)
        # 底座
        pygame.draw.rect(surface, gold_dark, (cx - 22, cy + 24, 44, 9), border_radius=3)
        pygame.draw.rect(surface, gold, (cx - 16, cy + 17, 32, 8), border_radius=2)
        # 盃柱
        pygame.draw.rect(surface, gold_dark, (cx - 5, cy + 4, 10, 14))
        # 兩側耳把
        pygame.draw.arc(surface, gold, (cx - 32, cy - 22, 20, 26), 1.4, 4.9, 4)
        pygame.draw.arc(surface, gold, (cx + 12, cy - 22, 20, 26), -1.7, 1.7, 4)
        # 盃身
        cup_pts = [
            (cx - 20, cy - 26),
            (cx + 20, cy - 26),
            (cx + 15, cy + 2),
            (cx + 6, cy + 8),
            (cx - 6, cy + 8),
            (cx - 15, cy + 2),
        ]
        pygame.draw.polygon(surface, gold, cup_pts)
        pygame.draw.polygon(surface, gold_dark, cup_pts, 3)
        # 高光與小星點
        pygame.draw.line(surface, gold_hi, (cx - 13, cy - 21), (cx - 10, cy - 3), 3)
        pygame.draw.circle(surface, gold_hi, (cx + 2, cy - 12), 4)
    else:
        gray = (125, 130, 145)
        gray_dark = (75, 80, 92)
        # 鎖環
        pygame.draw.arc(surface, gray, (cx - 15, cy - 26, 30, 32), 0, 3.1416, 5)
        pygame.draw.line(surface, gray, (cx - 15, cy - 10), (cx - 15, cy - 2), 5)
        pygame.draw.line(surface, gray, (cx + 15, cy - 10), (cx + 15, cy - 2), 5)
        # 鎖身
        body = pygame.Rect(cx - 21, cy - 4, 42, 32)
        pygame.draw.rect(surface, gray, body, border_radius=6)
        pygame.draw.rect(surface, gray_dark, body, 3, border_radius=6)
        # 鑰匙孔
        pygame.draw.circle(surface, gray_dark, (cx, cy + 9), 5)
        pygame.draw.rect(surface, gray_dark, (cx - 2, cy + 12, 4, 8))


def _get_font(size):
    if size not in _fonts:
        from scenes.dialogue_scene import _make_font
        _fonts[size] = _make_font(size)
    return _fonts[size]


def _build_toast_card(ach):
    """預先繪製一張 Steam 風格成就通知卡（TOAST_W x TOAST_H）。"""
    card = pygame.Surface((TOAST_W, TOAST_H), pygame.SRCALPHA)
    r = card.get_rect()
    pygame.draw.rect(card, TOAST_BG, r, border_radius=14)
    # 頂部金色亮條
    pygame.draw.rect(card, TOAST_BORDER, (0, 0, TOAST_W, 6),
                     border_top_left_radius=14, border_top_right_radius=14)
    pygame.draw.rect(card, TOAST_BORDER, r, 3, border_radius=14)

    # 左側獎盃徽章方塊
    badge = pygame.Rect(20, (TOAST_H - 92) // 2 + 2, 92, 92)
    pygame.draw.rect(card, TOAST_BADGE_BG, badge, border_radius=12)
    pygame.draw.rect(card, TOAST_BORDER, badge, 3, border_radius=12)
    draw_trophy_icon(card, badge, unlocked=True)

    # 右側文字：「成就解鎖！」 + 成就名稱
    header_font = _get_font(32)
    title_font = _get_font(48)
    header = header_font.render("成就解鎖！", False, TOAST_HEADER_COLOR)
    title = title_font.render(ach["title"], False, TOAST_TITLE_COLOR)
    text_x = badge.right + 24
    card.blit(header, (text_x, 22))
    card.blit(title, (text_x, 66))
    return card


def _start_next_toast(now_ms):
    global _active_toast
    if _active_toast is not None or not _toast_queue:
        return
    ach = _toast_queue.popleft()
    _active_toast = {
        "achievement": ach,
        "start_ms": now_ms,
        "card": _build_toast_card(ach),
    }
    sfx.play_achievement_sound()


def draw_overlay(screen, scale, offset):
    """在實際視窗上繪製右側滑入的成就通知（由 dialogue_scene._present 統一呼叫）。"""
    global _active_toast
    if not pygame.get_init():
        return
    now_ms = pygame.time.get_ticks()
    if _active_toast is None:
        if not _toast_queue:
            return
        _start_next_toast(now_ms)
        if _active_toast is None:
            return

    elapsed = now_ms - _active_toast["start_ms"]
    if elapsed >= TOAST_TOTAL_MS:
        _active_toast = None
        _start_next_toast(now_ms)
        if _active_toast is None:
            return
        elapsed = 0

    # 計算滑入／停留／滑出進度（0 = 藏在右側外，1 = 完全展開）
    if elapsed < SLIDE_IN_MS:
        t = elapsed / SLIDE_IN_MS
        progress = 1.0 - (1.0 - t) ** 3            # ease-out cubic
    elif elapsed < SLIDE_IN_MS + HOLD_MS:
        progress = 1.0
    else:
        t = (elapsed - SLIDE_IN_MS - HOLD_MS) / SLIDE_OUT_MS
        progress = max(0.0, 1.0 - t ** 3)          # ease-in cubic

    hidden_x = SCREEN_W + 10
    shown_x = SCREEN_W - TOAST_W - TOAST_MARGIN_RIGHT
    vx = hidden_x + (shown_x - hidden_x) * progress
    vy = SCREEN_H - TOAST_H - TOAST_MARGIN_BOTTOM

    card = _active_toast["card"]
    if scale != 1:
        draw_surf = pygame.transform.smoothscale(
            card, (max(1, int(TOAST_W * scale)), max(1, int(TOAST_H * scale))))
    else:
        draw_surf = card

    # 裁切在遊戲有效畫面（Letterbox 內），避免通知露到右側黑邊外
    clip_rect = pygame.Rect(
        offset[0], offset[1],
        max(1, int(SCREEN_W * scale)), max(1, int(SCREEN_H * scale)),
    )
    prev_clip = screen.get_clip()
    screen.set_clip(clip_rect)
    screen.blit(draw_surf, (int(offset[0] + vx * scale), int(offset[1] + vy * scale)))
    screen.set_clip(prev_clip)


# 模組載入時自動讀取本地存檔
_load()
