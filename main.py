import sys
import pygame
from scenes.dialogue_scene import init_display, play_dialogue
from scenes.alchemy_scene import play_alchemy_chapter
from scenes.fishing_scene import play_fishing
from scenes.exam_scene import play_exam_chapter
from scenes import sfx


def main():
  import ctypes
  try:
    ctypes.windll.user32.SetProcessDPIAware()   # 避免 Windows 縮放把視窗放大到超出螢幕
  except Exception:
    pass

  # 依據當前螢幕解析度建立 16:9 自適應可縮放視窗，所有內容繪製在 1920x1080 虛擬畫布上
  screen = init_display("Visual Novel Game")
  sfx.preload()   # 先合成好所有音效，避免第一次播放時卡頓

  print("--- 遊戲開始 ---")
  

  # 依次呼叫各個章節的對話 JSON
  play_dialogue("dialogues/dialogue_crash.json")
  play_dialogue("dialogues/dialogue_confrontation.json")

  # 上機考
  #   找教室(60s) → 紙條 → 電腦密碼(120s)；失敗會回到找教室，成功獲得「文件」道具
  exam_item = play_exam_chapter()

  play_dialogue("dialogues/fishing_intro.json")
  inventory = play_fishing()                                      # 釣完所有物品、且最後一次成功才返回
  play_dialogue("dialogues/fishing_quit.json")

  # 化學館 + 結局：find_clue → device → 拖曳解謎
  #   成功 → alchemy_succeed → ending_succeed；放錯 → 扣 10 秒（第一次另播 alchemy_wrong_procedure）；時間到 → alchemy_failed
  play_alchemy_chapter([item["name"] for item in inventory])

  print("--- 遊戲結束 ---")
  pygame.quit()
  sys.exit()


if __name__ == "__main__":
  main()