"""釣魚小遊戲（放在 scenes/fishing_scene.py）。

用法：
    from scenes.dialogue_scene import play_dialogue
    from scenes.fishing_scene import play_fishing

    play_dialogue("fishing_intro")
    inventory = play_fishing()          # 釣完所有物品、且最後一次釣魚成功後才會返回
    play_dialogue("fishing_quit")

流程：
    第一階段：SPACE 啟動判定線 → 再按 SPACE 停止 → 播放收線動畫 → 判定
    第二階段：成功 → 顯示物品（按 SPACE 回到第一階段）；失敗 → 顯示「沒釣到東西。」2 秒後自動回到第一階段
    物品釣完後仍會再釣一次：成功就直接返回（接 fishing_quit）；失敗則照常重來，直到成功。

素材（缺少時會印出警告；判定條三件缺少時用簡易方塊代替，方便先測試）：
    assets/ui/ui_game_judge_bar.png, ui_game_judge_range.png, ui_game_judge_line.png
    assets/bg/bg_game_sky.png, bg_game_move_cloud.png, bg_game_move_water.png, bg_game_dock.png
    assets/bg/bg_rod_1~5.png（收線）, bg_sparkles_1~4.png（循環）
    物品圖 obj_*.png：依序嘗試 assets/obj、assets/ui、assets/bg、assets/char、assets
物品說明文字：dialogues/dialogue_fishing_item_texts.json 的 "items"（物品名稱 → 說明）
"""
import json
import random
import sys

import pygame

from scenes import music, sfx
from scenes.dialogue_scene import (
    ASSET_DIR, FONT_ANTIALIAS, SCREEN_H, SCREEN_W, SPEAKER_COLOR, TEXT_COLOR,
    _make_font, _present, _resolve_dialogue, _wrap,
)

# ---------------- 可調整設定 ----------------
BAR_POS = (1650, 150)          # 判定條左上角
LINE_SPEED = 700               # 判定線速度（px/秒）
CLOUD_SPEED = 30               # 雲向左捲動速度（px/秒）
WATER_SPEED = 90               # 水向左捲動速度（px/秒）
ROD_FPS = 8                    # 釣竿收線動畫每秒幾幀
SPARKLE_FPS = 6                # sparkles 每秒幾幀
ROD_FRAMES = 5
SPARKLE_FRAMES = 4

FAIL_TEXT = "沒釣到東西。"
FAIL_DISPLAY_MS = 2000
FAIL_TEXT_SIZE = 96            # 比對話文字（32）大；Unifont 請用 16 的倍數
OUTLINE_PX = 4                 # 黑框粗細
ITEM_NAME_SIZE = 64
ITEM_DESC_SIZE = 32
ITEM_DESC_MAX_W = 1400
HINT_TEXT = "按 SPACE 繼續"
OVERLAY_ALPHA = 170            # 物品畫面的半透明黑底（0~255）

AUTO_START_AFTER_RETURN = False   # True：回到釣魚畫面且收線動畫結束後，判定線自動開始動

# (內部 id, 圖檔名, 物品名稱)
ITEMS = [
    ("bicycle", "obj_bicycle", "高姐姐的腳踏車"),
    ("garbage", "obj_garbage", "學生腐爛的夢想"),
    ("coin", "obj_coin", "DYY的銅板"),
    ("fisherman_bag", "obj_fisherman_bag", "漁父的包包"),
    ("Li", "obj_Li", "氫化鋁鋰"),
]
# --------------------------------------------

READY, MOVING, REELING, ITEM, FAIL, RETURN = "ready", "moving", "reeling", "item", "fail", "return"
PHASE1_STATES = (READY, MOVING, REELING, RETURN)   # sparkles 只在這些狀態播放


def _load(name):
    prefix = name.split("_", 1)[0]
    for folder in (prefix, "obj", "ui", "bg", "char", ""):
        path = ASSET_DIR / folder / f"{name}.png"
        if path.exists():
            return pygame.image.load(str(path)).convert_alpha()
    print(f"[fishing_scene] 找不到素材：{name}.png（已搜尋 {ASSET_DIR} 底下的 {prefix}/obj/ui/bg/char）")
    return None


def _placeholder(size, color, radius=0):
    s = pygame.Surface(size, pygame.SRCALPHA)
    pygame.draw.rect(s, color, s.get_rect(), border_radius=radius)
    return s


def _arc_height(bar):
    """判定條上下端圓弧的高度：由上往下找第一列幾乎填滿整個寬度的位置。"""
    w, h = bar.get_size()
    for y in range(h // 2):
        if bar.subsurface((0, y, w, 1)).get_bounding_rect(min_alpha=1).width >= w * 0.9:
            return y
    return 0


def _outlined(font, text, color, px=OUTLINE_PX):
    base = font.render(text, FONT_ANTIALIAS, color)
    edge = font.render(text, FONT_ANTIALIAS, (0, 0, 0))
    surf = pygame.Surface((base.get_width() + 2 * px, base.get_height() + 2 * px), pygame.SRCALPHA)
    for dx in range(-px, px + 1):
        for dy in range(-px, px + 1):
            if dx * dx + dy * dy <= px * px:
                surf.blit(edge, (px + dx, px + dy))
    surf.blit(base, (px, px))
    return surf


def _blit_scroll(target, img, y, offset):
    w = img.get_width()
    x = -(int(offset) % w)          # offset 增加 → 畫面向左捲動
    while x < SCREEN_W:
        target.blit(img, (x, y))
        x += w


def _load_descriptions():
    try:
        with open(_resolve_dialogue("fishing_item_texts"), "r", encoding="utf-8") as f:
            return json.load(f).get("items", {})
    except (FileNotFoundError, ValueError):
        print("[fishing_scene] 讀不到 fishing_item_texts.json，物品說明將是空白")
        return {}


class FishingGame:
    def __init__(self):
        # --- 素材 ---
        self.bg_sky = _load("bg_game_sky")
        self.bg_cloud = _load("bg_game_move_cloud")
        self.bg_water = _load("bg_game_move_water")
        self.bg_dock = _load("bg_game_dock")
        self.rod = [_load(f"bg_rod_{i}") for i in range(1, ROD_FRAMES + 1)]
        self.sparkles = [_load(f"bg_sparkles_{i}") for i in range(1, SPARKLE_FRAMES + 1)]

        self.bar = _load("ui_game_judge_bar") or _placeholder((80, 780), (60, 60, 60, 255), 40)
        self.range_img = _load("ui_game_judge_range") or _placeholder((80, 200), (80, 220, 120, 150))
        self.line_img = _load("ui_game_judge_line") or _placeholder((160, 12), (255, 60, 60, 255))

        self.bar_rect = self.bar.get_rect(topleft=BAR_POS)
        self.arc = _arc_height(self.bar)
        self.line_x = self.bar_rect.centerx - self.line_img.get_width() // 2   # 線中心與判定條中心共用 x
        self.line_h = self.line_img.get_height()
        self.range_h = self.range_img.get_height()

        # --- 物品 ---
        descriptions = _load_descriptions()
        self.items = [{"id": i, "image": _load(img), "name": n, "description": descriptions.get(n, "")}
                      for i, img, n in ITEMS]
        self.inventory = []
        self.current = None

        # --- 文字 ---
        self.fail_surf = _outlined(_make_font(FAIL_TEXT_SIZE), FAIL_TEXT, TEXT_COLOR)
        self.name_font = _make_font(ITEM_NAME_SIZE)
        self.desc_font = _make_font(ITEM_DESC_SIZE)
        self.hint_surf = _outlined(self.desc_font, HINT_TEXT, TEXT_COLOR, 2)
        self.overlay = pygame.Surface((SCREEN_W, SCREEN_H), pygame.SRCALPHA)
        self.overlay.fill((0, 0, 0, OVERLAY_ALPHA))
        self.item_surfs = []          # [(surface, (x, y)), ...]

        # --- 狀態 ---
        self.t = 0.0                  # 背景捲動用
        self.sparkle_t = 0.0
        self.rod_t = 0.0
        self.fail_timer = 0
        self.done = False
        self._reset_phase1()

    # ---------- 第一階段 ----------
    def _reset_phase1(self):
        lo = self.bar_rect.top + self.arc
        hi = self.bar_rect.bottom - self.arc - self.range_h
        self.range_y = random.randint(lo, hi) if hi >= lo else self.bar_rect.centery - self.range_h // 2
        self.line_y = float(self.bar_rect.bottom - self.line_h)   # 起始在判定條最底部
        self.direction = -1                                       # 先往上
        self.state = READY

    def _move_line(self, dt):
        self.line_y += self.direction * LINE_SPEED * dt
        top, bottom = self.bar_rect.top, self.bar_rect.bottom - self.line_h
        if self.line_y <= top:
            self.line_y, self.direction = top, 1
        elif self.line_y >= bottom:
            self.line_y, self.direction = bottom, -1

    def _judge(self):
        center_y = self.line_y + self.line_h / 2
        if self.range_y <= center_y <= self.range_y + self.range_h:
            self.on_success()
        else:
            self.on_fail()

    # ---------- 第二階段 ----------
    def on_success(self):
        sfx.play("catch")
        if not self.items:            # 物品已釣完：這次成功就直接結束遊戲
            self.done = True
            return
        item = random.choice(self.items)
        self.items.remove(item)
        self.inventory.append({"id": item["id"], "name": item["name"], "description": item["description"]})
        self.current = item
        self._build_item_surfs(item)
        self.state = ITEM

    def on_fail(self):
        sfx.play("miss")
        self.fail_timer = pygame.time.get_ticks()
        self.state = FAIL

    def _build_item_surfs(self, item):
        cx = SCREEN_W // 2
        self.item_surfs = []
        y = SCREEN_H // 2
        if item["image"]:
            r = item["image"].get_rect(center=(cx, SCREEN_H // 2))
            self.item_surfs.append((item["image"], r.topleft))
            y = r.bottom
        name = _outlined(self.name_font, item["name"], SPEAKER_COLOR)
        y += 30
        self.item_surfs.append((name, (cx - name.get_width() // 2, y)))
        y += name.get_height() + 10
        for ln in _wrap(item["description"], self.desc_font, ITEM_DESC_MAX_W):
            if ln:
                s = _outlined(self.desc_font, ln, TEXT_COLOR, 2)
                self.item_surfs.append((s, (cx - s.get_width() // 2, y)))
            y += self.desc_font.get_linesize() + 8

    # ---------- 更新 ----------
    def update(self, dt_ms, space):
        dt = min(dt_ms, 50) / 1000
        self.t += dt
        if self.state in PHASE1_STATES:
            self.sparkle_t += dt

        if self.state == READY:
            if space:
                self.state = MOVING
                sfx.play("cast")
        elif self.state == MOVING:
            self._move_line(dt)
            if space:                                   # 停止判定線，開始收線
                self.state, self.rod_t = REELING, 0.0
                sfx.play("reel")
        elif self.state == REELING:
            self.rod_t += dt
            if self.rod_t * ROD_FPS >= ROD_FRAMES:      # 收線播完才判定
                self._judge()
        elif self.state == ITEM:
            if space:
                sfx.play("advance")
                self._begin_return()
        elif self.state == FAIL:                        # 計時期間忽略空白鍵
            if pygame.time.get_ticks() - self.fail_timer >= FAIL_DISPLAY_MS:
                self._begin_return()
        elif self.state == RETURN:
            self.rod_t += dt
            if self.rod_t * ROD_FPS >= ROD_FRAMES:
                self._reset_phase1()
                if AUTO_START_AFTER_RETURN:
                    self.state = MOVING

    def _begin_return(self):
        self.state, self.rod_t = RETURN, 0.0

    # ---------- 繪製 ----------
    def _rod_frame(self):
        last = ROD_FRAMES - 1
        if self.state == REELING:
            return min(int(self.rod_t * ROD_FPS), last)
        if self.state == RETURN:
            return last - min(int(self.rod_t * ROD_FPS), last)
        if self.state in (ITEM, FAIL):
            return last
        return 0

    def draw(self, target):
        target.fill((0, 0, 0))
        # 圖層（下到上）：sky → cloud → water → sparkles → dock → rod → 判定條(bar → range → line)
        if self.bg_sky:
            target.blit(self.bg_sky, (0, 0))
        if self.bg_cloud:
            _blit_scroll(target, self.bg_cloud, 0, self.t * CLOUD_SPEED)
        if self.bg_water:
            _blit_scroll(target, self.bg_water, SCREEN_H - self.bg_water.get_height(), self.t * WATER_SPEED)
        sp = self.sparkles[int(self.sparkle_t * SPARKLE_FPS) % SPARKLE_FRAMES]
        if sp:
            target.blit(sp, (0, 0))
        if self.bg_dock:
            target.blit(self.bg_dock, (0, 0))
        rod = self.rod[self._rod_frame()]
        if rod:
            target.blit(rod, (0, 0))

        target.blit(self.bar, self.bar_rect)
        target.blit(self.range_img, (self.bar_rect.left, self.range_y))
        target.blit(self.line_img, (self.line_x, int(self.line_y)))

        if self.state == FAIL:
            target.blit(self.fail_surf, self.fail_surf.get_rect(center=(SCREEN_W // 2, SCREEN_H // 2)))
        elif self.state == ITEM:
            target.blit(self.overlay, (0, 0))
            for surf, pos in self.item_surfs:
                target.blit(surf, pos)
            target.blit(self.hint_surf, self.hint_surf.get_rect(midbottom=(SCREEN_W // 2, SCREEN_H - 40)))


def play_fishing(screen=None):
    """進行釣魚遊戲，回傳 inventory（list of {"id","name","description"}）。"""
    if not pygame.get_init():
        pygame.init()
    screen = screen or pygame.display.get_surface()
    if screen is None:
        screen = pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)

    music.play("lake")
    game = FishingGame()
    canvas = pygame.Surface((SCREEN_W, SCREEN_H)).convert()   # 視窗不是 1920x1080 時才會用到
    clock = pygame.time.Clock()
    pygame.key.stop_text_input()    # 避免中文輸入法吃掉空白鍵
    pygame.event.clear()

    while not game.done:
        dt = clock.tick(60)
        space = False
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            elif (event.type == pygame.KEYDOWN and event.key == pygame.K_SPACE) or \
                    (event.type == pygame.TEXTINPUT and event.text == " "):
                space = True            # 同一幀無論收到幾個空白事件，只算一次

        game.update(dt, space)
        if game.done:
            break

        screen = pygame.display.get_surface()
        direct = screen.get_size() == (SCREEN_W, SCREEN_H)
        game.draw(screen if direct else canvas)
        if not direct:
            _present(screen, canvas)
        pygame.display.flip()

    return game.inventory


if __name__ == "__main__":
    pygame.init()
    pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
    inv = play_fishing()
    print("inventory:", [i["name"] for i in inv])
    pygame.quit()
