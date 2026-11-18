import sys
import pygame
from scenes.dialogue_scene import play_dialogue
from scenes.alchemy_scene import play_alchemy_chapter
from scenes.fishing_scene import play_fishing


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

  print("--- 遊戲開始 ---")
  

  # 依次呼叫各個章節的對話 JSON
  play_dialogue("dialogues/dialogue_crash.json")
  play_dialogue("dialogues/dialogue_confrontation.json")

  # TODO：解謎、釣魚關卡完成後接在這裡，並把釣到的物品傳給化學館
  caught_items = None   # None = 全部物品
  play_alchemy_chapter(caught_items)

  # 上機考
  play_dialogue("dialogues/puzzle_find_room.json")
  play_dialogue("dialogues/puzzle_wrong.json")           # 之後改為：提交錯誤時觸發
  play_dialogue("dialogues/puzzle_find_room_correct.json")
  play_dialogue("dialogues/puzzle_succeed.json")
  play_dialogue("dialogues/puzzle_fail.json")            # 之後改為：第一關重試超過五次觸發

  play_dialogue("dialogues/fishing_intro.json")
  inventory = play_fishing()                                      # 釣完所有物品、且最後一次成功才返回
  play_dialogue("dialogues/fishing_quit.json")

  # 化學館
  play_dialogue("dialogues/alchemy_find_clue.json")
  play_dialogue("dialogues/alchemy_device.json")
  play_dialogue("dialogues/alchemy_wrong_procedure.json")  # 之後改為：操作順序錯誤時觸發
  play_dialogue("dialogues/alchemy_succeed.json")

  # 結局
  play_dialogue("dialogues/ending_succeed.json")
  play_dialogue("dialogues/alchemy_failed.json")         # 之後改為：失敗結局才觸發

  print("--- 遊戲結束 ---")
  pygame.quit()
  sys.exit()


if __name__ == "__main__":
  main()