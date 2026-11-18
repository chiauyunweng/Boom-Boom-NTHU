"""對話測試入口（放在專案根目錄，與 main.py 同層）。

用法：
    python test_main.py                      # 依劇情順序播放全部對話
    python test_main.py alchemy_failed       # 只播放指定對話
    python test_main.py puzzle_fail ending_succeed   # 依序播放多段
    python test_main.py --list               # 列出所有對話 id

播放中按 SPACE 換句；每段結束後自動接下一段。
"""
import ctypes
import sys

try:
    ctypes.windll.user32.SetProcessDPIAware()   # 避免 Windows 縮放讓視窗超出螢幕
except Exception:
    pass

import pygame

from scenes.dialogue_scene import DIALOGUE_DIR, SCREEN_H, SCREEN_W, _resolve_dialogue, play_dialogue

# 劇情順序（id 不含 dialogue_ 前綴）。fishing_item_texts 只有物品說明、沒有對話，所以不列入。
STORY_ORDER = [
    "crash",
    "confrontation",
    "puzzle_find_room",
    "puzzle_wrong",
    "puzzle_find_room_correct",
    "puzzle_succeed",
    "puzzle_fail",
    "fishing_intro",
    "fishing_quit",
    "alchemy_find_clue",
    "alchemy_device",
    "alchemy_wrong_procedure",
    "alchemy_succeed",
    "ending_succeed",
    "alchemy_failed",
]


def main():
    args = sys.argv[1:]

    if "--list" in args:
        print("可用對話：")
        for p in sorted(DIALOGUE_DIR.glob("*.json")):
            print("  ", p.stem.removeprefix("dialogue_"))
        return

    ids = args or STORY_ORDER

    pygame.init()
    pygame.display.set_mode((SCREEN_W, SCREEN_H), pygame.SCALED | pygame.RESIZABLE)
    pygame.display.set_caption("Dialogue Test")

    for dlg_id in ids:
        try:
            _resolve_dialogue(dlg_id)
        except FileNotFoundError as e:
            print(f"--- 跳過：{e}")
            continue
        print(f"--- 播放：{dlg_id}")
        play_dialogue(dlg_id)

    print("--- 測試結束 ---")
    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()