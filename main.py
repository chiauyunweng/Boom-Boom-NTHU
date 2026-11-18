import sys
import pygame
from scenes.dialogue_scene import play_dialogue


def main():
  pygame.init()

  # 建立 1920x1080 邏輯視窗，並加上 pygame.SCALED 實現等比縮放與自動填黑
  # 修改後：直接以標準 1920x1080 視窗開啟，保留縮放與視窗化能力
  screen = pygame.display.set_mode((1920, 1080), pygame.RESIZABLE)
  pygame.display.set_caption("Visual Novel Game")

  print("--- 遊戲開始 ---")

  # 依次呼叫各個章節的對話 JSON
  play_dialogue("dialogues/dialogue_crash.json")
  play_dialogue("dialogues/dialogue_confrontation.json")

  print("--- 遊戲結束 ---")
  pygame.quit()
  sys.exit()


if __name__ == "__main__":
  main()