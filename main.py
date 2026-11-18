import sys
import pygame
from scenes.dialogue_scene import play_dialogue
from scenes.alchemy_scene import play_alchemy_chapter
from scenes.fishing_scene import play_fishing
from scenes import sfx


def main():
  import ctypes
  try:
    ctypes.windll.user32.SetProcessDPIAware()   # 避免 Windows 縮放把視窗放大到超出螢幕
  except Exception:
    pass

  pygame.init()

  # 建立 1920x1080 邏輯視窗，並加上 pygame.SCALED 實現等比縮放與自動填黑
  # 修改後：直接以標準 1920x1080 視窗開啟，保留縮放與視窗化能力
  screen = pygame.display.set_mode((1920, 1080), pygame.SCALED | pygame.RESIZABLE)
  pygame.display.set_caption("Visual Novel Game")
  sfx.preload()   # 先合成好所有音效，避免第一次播放時卡頓

  print("--- 遊戲開始 ---")
  

  # 依次呼叫各個章節的對話 JSON
  play_dialogue("dialogues/dialogue_crash.json")
  play_dialogue("dialogues/dialogue_confrontation.json")

  # 上機考
  play_dialogue("dialogues/puzzle_find_room.json")
  play_dialogue("dialogues/puzzle_wrong.json")           # 之後改為：提交錯誤時觸發
  play_dialogue("dialogues/puzzle_find_room_correct.json")
  play_dialogue("dialogues/puzzle_succeed.json")
  play_dialogue("dialogues/puzzle_fail.json")            # 之後改為：第一關重試超過五次觸發

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