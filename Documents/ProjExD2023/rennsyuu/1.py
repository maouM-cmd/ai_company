import pygame
import sys
import random
import math

img_bg = pygame.image.load("bgimage.png")
img_player = pygame.image.load("player1.png")
img_weapon = pygame.image.load("bullet.png")
img_enemy = [
    pygame.image.load("enemy1.png"),#敵画像
    pygame.image.load("e_bullet.png")#敵の攻撃弾画像
]
img_explode = [
    None,
    pygame.image.load("explode1.png"),
    pygame.image.load("explode2.png"),
    pygame.image.load("explode3.png"),
    pygame.image.load("explode4.png"),
    pygame.image.load("explode5.png"),
    pygame.image.load("explode6.png"),
    pygame.image.load("explode7.png")
]

bg_y = 0
px = 320 #プレイヤーのX座標
py = 240 #プレイヤーのY座標
bx = 0 #弾のX座標
by = 0 #弾のY座標
t = 0 #タイマー変数
space = 0
BULLET_MAX = 100 #弾の最大値
ENEMY_MAX = 100 #敵の最大数
ENEMY_BULLET = 1
bull_n = 0
bull_x =[0]*BULLET_MAX
bull_y =[0]*BULLET_MAX
bull_f =[False]*BULLET_MAX

ebull_n = 0
ebull_x = [0]*ENEMY_MAX
ebull_y = [0]*ENEMY_MAX
ebull_a = [0]*ENEMY_MAX
ebull_f =[False]*ENEMY_MAX
ebull_f2 = [False]*ENEMY_MAX
e_list = [0]*ENEMY_MAX
e_speed = [0]*ENEMY_MAX

EFFECT_MAX = 100 #エフェクトの最大数
e_n = 0
e_l = [0]*EFFECT_MAX
e_x = [0]*EFFECT_MAX #エフェクトのX座標
e_y = [0]*EFFECT_MAX #エフェクトのY座標


def set_bullet():#弾のスタンバイ
    global bull_n
    bull_f[bull_n] = True
    bull_x[bull_n] = px-16
    bull_y[bull_n] = py-32
    bull_n = (bull_n+1)%BULLET_MAX

def move_bullet(screen):#弾を飛ばす
    for i in range(BULLET_MAX):
        if bull_f[i] == True:
            bull_y[i] = bull_y[i] - 32
            screen.blit(img_weapon,[bull_x[i],bull_y[i]])
            if bull_y[i] < 0:
                bull_f[i] = False

def move_player(screen,key):
    global px,py,space
    if key[pygame.K_UP] == 1:
        py = py - 10
        if py < 20:
            py = 20
    if key[pygame.K_DOWN] == 1:
        py = py + 10
        if py > 460:
            py = 460
    if key[pygame.K_LEFT] == 1:
        px = px - 10
        if px < 20:
            px = 20
    if key[pygame.K_RIGHT] == 1:
        px = px + 10
        if px > 620:
            px = 620
    space = (space+1)*key[pygame.K_SPACE]
    if space%5 == 1: #5フレーム毎に弾を飛ばす
        set_bullet()

    screen.blit(img_player,[px-16,py-16])
def set_enemy(x,y,a,enemy,speed):
    global ebull_n
    while True:
        if ebull_f[ebull_n] == False:
            ebull_f[ebull_n] = True
            ebull_x[ebull_n] = x
            ebull_y[ebull_n] = y
            ebull_a[ebull_n] = a
            e_list[ebull_n] = enemy
            e_speed[ebull_n] = speed
            break
        ebull_n = (ebull_n+1)%ENEMY_MAX

def move_enemy(screen):
    for i in range(ENEMY_MAX):
        if ebull_f[i] == True:
            png = e_list[i]
            ebull_x[i] = ebull_x[i] + e_speed[i]*math.cos(math.radians(ebull_a[i]))
            ebull_y[i] = ebull_y[i] + e_speed[i]*math.sin(math.radians(ebull_a[i]))
            if e_list[i] == 0 and ebull_y[i] > 100 and ebull_f2[i] == False:#弾を発射
                set_enemy(ebull_x[i],ebull_y[i],90,1,15)
                ebull_f2[i] = True
            if ebull_x[i] < -40 or ebull_x[i] > 680 or ebull_y[i] < -40 or ebull_y[i] > 520:#画面外に敵が消える
                ebull_f[i] = False
                ebull_f2[i] = False

            if e_list[i] != ENEMY_BULLET:#敵の弾以外なら
                w = img_enemy[e_list[i]].get_width()
                h = img_enemy[e_list[i]].get_height()
                r = int((w+h)/4)+8
                for n in range(BULLET_MAX):
                    if bull_f[n] == True and distance(ebull_x[i]-16,ebull_y[i]-16,bull_x[n],bull_y[n]) < r*r:
                        bull_f[n] = False
                        effect(ebull_x[i],ebull_y[i])#エフェクト発生
                        ebull_f[i] = False
                        ebull_f2[i] = False
            rz = pygame.transform.rotozoom(img_enemy[png],-180,1.0)
            screen.blit(rz,[ebull_x[i]-rz.get_width()/2,ebull_y[i]-rz.get_height()/2])

def effect(x,y):#エフェクトを描画する準備を行う関数
    global e_n
    e_l[e_n] = 1
    e_x[e_n] = x
    e_y[e_n] = y
    e_no = (e_n+1)%EFFECT_MAX

def draw_effect(screen):#エフェクトを描画する関数
    for i in range(EFFECT_MAX):
        if e_l[i] > 0:
            rz = pygame.transform.rotozoom(img_explode[e_l[i]],0,0.5)#画像を縮小させる
            screen.blit(rz,[e_x[i]-30,e_y[i]-30])
            e_l[i] = e_l[i] + 1
            if e_l[i] == 8:#使用するエフェクト用画像が7枚
                e_l[i] = 0

def distance(x1,y1,x2,y2):
    return ((x1-x2)*(x1-x2)+(y1-y2)*(y1-y2))

def main():
    global t,bg_y
    pygame.init()
    pygame.display.set_caption("シューティングゲーム")
    screen = pygame.display.set_mode((640,480))
    clock = pygame.time.Clock()

    while True:
        t=t+1
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
        bg_y = (bg_y+16)%480
        screen.blit(img_bg,[0,bg_y-480])
        screen.blit(img_bg,[0,bg_y])
        key = pygame.key.get_pressed()
        move_player(screen,key)
        move_bullet(screen)
        if t%30 == 0:#30フレームにつき敵1体出現
            set_enemy(random.randint(20,620),-10,90,0,6)
        move_enemy(screen)
        draw_effect(screen)
        pygame.display.update()
        clock.tick(30)

if __name__ == "__main__":
    main()