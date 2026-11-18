import sys
import pygame


def run_minigame():
  screen = pygame.display.get_surface()
  clock = pygame.time.Clock()

  font = pygame.font.SysFont(None, 50)

  running = True
  while running:
    for event in pygame.event.get():
      if event.type == pygame.QUIT:
        pygame.quit()
        sys.exit()
      elif event.type == pygame.KEYDOWN:
        if event.key == pygame.K_RETURN:  # 按 Enter 結束小遊戲
          running = False

    screen.fill((50, 100, 150))  # 藍色背景代表小遊戲畫面
    text = font.render(
        "Mini Game 執行中... 請按 ENTER 結束返回劇情", True, (255, 255, 255)
    )
    screen.blit(text, (200, 500))

    pygame.display.flip()
    clock.tick(60)