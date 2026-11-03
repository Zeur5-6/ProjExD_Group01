import math
import os
import random
import sys
import pygame as pg

# ============================================================
# 1. ゲーム全体の設定：数値を変えると難易度や表示が変わる
# ============================================================

WIDTH = 1100
HEIGHT = 650
FPS = 50
GAME_OVER_DURATION = 3000  # ミリ秒（3秒）
PLAYER_BULLET_SIZE = (38, 38)  # 自機の弾を少し大きく
ENEMY_SHOOT_INTERVAL = (65, 115)  # 敵の発射間隔（フレーム）

GROUND_Y = 550
# 地面から確実に飛び乗れる高さだけに足場を生成
# 1段目は単発ジャンプの限界(約133px)付近、2段目はその約2倍まで
LOW_PLATFORM_HEIGHT = (115, 125)
HIGH_PLATFORM_HEIGHT = (205, 250)
PLATFORM_GAP_RANGE = (60, 180)  # 足場を置く場合の通常の隙間
PLATFORM_EMPTY_CHANCE = 0.32  # 約32%の確率で足場を置かず空白区間にする
PLATFORM_EMPTY_LENGTH = (320, 650)  # 空白区間の長さ（px）
PLATFORM_WIDTH_RANGE = (170, 250)
GENERATE_AHEAD = WIDTH + 500
CLEANUP_BEHIND = 800
MAX_CAMERA_BACKTRACK = 400  # カメラが戻れる最大距離
LEFT_CAMERA_MARGIN = 250  # 左へ移動した際にカメラが追い始める位置
ENEMY_SPAWN_INTERVAL = 5000  # ミリ秒
ENEMIES_PER_WAVE = (1, 3)
MAX_ENEMIES = 9

# 画像ファイルの参照先を、このPythonファイルのあるフォルダに固定する
os.chdir(os.path.dirname(os.path.abspath(__file__)))


# ============================================================
# 2. 共通関数：画面内判定・敵弾の方向計算
# ============================================================


def check_bound(obj_rct: pg.Rect) -> tuple[bool, bool]:
    """
    オブジェクトが画面内かを判定する
    """
    yoko = 0 <= obj_rct.left and obj_rct.right <= WIDTH
    tate = 0 <= obj_rct.top and obj_rct.bottom <= HEIGHT
    return yoko, tate


def calc_orientation(org: pg.Rect, dst: pg.Rect) -> tuple[float, float]:
    """
    orgからdstへの単位方向ベクトルを返す
    """
    dx = dst.centerx - org.centerx
    dy = dst.centery - org.centery
    norm = math.hypot(dx, dy)

    if norm == 0:
        return 0.0, 0.0

    return dx / norm, dy / norm


# ============================================================
# 3. 足場：下キーですり抜けられる一方通行の足場
# ============================================================
class Platform(pg.sprite.Sprite):
    """
    下キーですり抜けられる足場
    """

    def __init__(self, x: int, y: int, width: int):
        super().__init__()
        self.image = pg.Surface((width, 20))
        self.image.fill((130, 90, 55))
        self.rect = self.image.get_rect(topleft=(x, y))


# ============================================================
# 4. プレイヤー：左右移動・ジャンプ・落下・足場の着地
#    ダブルジャンプを追加する場合は主にこのクラスを変更する
# ============================================================
class Player(pg.sprite.Sprite):
    """
    プレイヤー（魔法使い）
    """

    delta = {
        pg.K_LEFT: (-1, 0),
        pg.K_RIGHT: (+1, 0),
    }

    def __init__(self, xy: tuple[int, int]):
        super().__init__()

        img0 = pg.transform.scale(
            pg.image.load("fig/wizard.png").convert_alpha(), (60, 80)
        )
        img = pg.transform.flip(img0, True, False)

        # ドット絵は回転させず、左右反転だけで向きを表現する
        self.imgs = {
            (+1, 0): img,
            (-1, 0): img0,
        }

        self.dire = (+1, 0)
        self.facing = 1
        self.image = self.imgs[self.dire]
        self.rect = self.image.get_rect(center=xy)

        # 移動とジャンプの性能（足場生成の高さにも関係する）
        self.speed = 7
        self.vy = 0.0
        self.gravity = 0.8
        self.jump_power = -15
        self.on_ground = False

        # Rectは整数座標なので、縦位置は小数でも別に保持する
        self.y = float(self.rect.y)
        self.drop_timer = 0
        self.current_platform = None

        self.shoot_cooldown = 0

    def update(self, key_lst, platforms, jump_pressed=False):
        """
        左右移動、ジャンプ、重力、着地処理
        """
        dx = 0

        for k, mv in __class__.delta.items():
            if key_lst[k]:
                dx += mv[0]

        # 左右移動
        self.rect.x += self.speed * dx

        # マップの左右端を超えないようにする
        self.rect.left = max(0, self.rect.left)
        # 右方向にはマップの端を設けない

        # 足場から降りる
        if key_lst[pg.K_DOWN] and self.on_ground:
            if self.current_platform is not None:
                self.drop_timer = 15
                self.on_ground = False
                self.current_platform = None
                self.vy = 2

        # ジャンプ
        if jump_pressed and self.on_ground:
            self.vy = self.jump_power
            self.on_ground = False
            self.current_platform = None

        # 重力
        old_bottom = self.rect.bottom
        self.vy += self.gravity
        self.y += self.vy
        self.rect.y = round(self.y)

        self.on_ground = False
        self.current_platform = None

        # 地面との当たり判定
        if self.vy >= 0 and self.rect.bottom >= GROUND_Y:
            self.rect.bottom = GROUND_Y
            self.y = float(self.rect.y)
            self.vy = 0
            self.on_ground = True

        # 足場との当たり判定
        elif self.vy >= 0 and self.drop_timer == 0:
            for platform in platforms:
                if (
                    self.rect.right > platform.rect.left
                    and self.rect.left < platform.rect.right
                    and old_bottom <= platform.rect.top
                    and self.rect.bottom >= platform.rect.top
                ):
                    self.rect.bottom = platform.rect.top
                    self.y = float(self.rect.y)
                    self.vy = 0
                    self.on_ground = True
                    self.current_platform = platform
                    break

        if self.drop_timer > 0:
            self.drop_timer -= 1

        # ジャンプ中も直立。向きは左右だけ切り替える
        if dx != 0:
            self.facing = dx
        self.dire = (self.facing, 0)
        self.image = self.imgs[self.dire]

        if self.shoot_cooldown > 0:
            self.shoot_cooldown -= 1


# ============================================================
# 5. 自機の弾：Spaceキーで生成され、向いている方向へ進む
# ============================================================
class PlayerBullet(pg.sprite.Sprite):
    """
    プレイヤーの弾（角度指定による斜め発射に対応）
    """

    # --- 追加機能：弾幕（引数に回転角度 angle0 を追加） ---
    def __init__(self, player: Player, angle0: float = 0) -> None:
        """
        弾画像と進行方向の初期化を行う
        引数1 player: 弾を発射するPlayerインスタンス
        引数2 angle0: 発射角度（デフォルト0度）
        """
        super().__init__()

        img = pg.transform.scale(
            pg.image.load("fig/attack.png").convert_alpha(), PLAYER_BULLET_SIZE
        )
        # 左向きの場合は弾画像を反転し、発射角度に合わせて回転させる
        if player.facing == -1:
            img = pg.transform.flip(img, True, False)
        self.image = pg.transform.rotozoom(img, -angle0 * player.facing, 1.0)

        self.rect = self.image.get_rect()
        self.direction = player.facing
        self.rect.center = (
            player.rect.centerx + self.direction * 30,
            player.rect.centery
        )

        self.speed = 15

        # 回転角度からX方向・Y方向の速度を計算し、小数の座標を保持する
        rad = math.radians(angle0)
        self.vx = self.speed * math.cos(rad) * self.direction
        self.vy = self.speed * math.sin(rad)
        self.x = float(self.rect.x)
        self.y = float(self.rect.y)

    def update(self) -> None:
        """
        速度ベクトルに従って弾の座標を更新する
        """
        self.x += self.vx
        self.y += self.vy
        self.rect.x = round(self.x)
        self.rect.y = round(self.y)

        # 画面外の弾はmain()でまとめて削除する


# --- 追加機能：弾幕（一度に複数方向へビームを発射するクラス） ---
class NeoBeam:
    """
    複数方向へ広がる弾幕（ビーム）を生成するクラス
    """

    def __init__(self, bird: Player, num: int) -> None:
        """
        弾幕の初期設定を行う
        引数1 bird: 弾を発射するプレイヤーインスタンス
        引数2 num: 発射するビームの数
        """
        self.bird = bird
        self.num = num

    def gen_beams(self) -> list[PlayerBullet]:
        """
        -50°〜+51°の角度範囲で指定ビーム数分のPlayerBulletを生成しリストで返す
        戻り値: PlayerBulletインスタンスのリスト
        """
        beams: list[PlayerBullet] = []
        step = int(100 / (self.num - 1)) if self.num > 1 else 100
        for angle in range(-50, +51, step):
            beams.append(PlayerBullet(self.bird, angle))
        return beams


# --- 追加機能：残機数（ライフを管理・描画するクラス） ---
class Life:
    """
    プレイヤーの残機数（ライフ）を管理し、画面右下にアイコンを描画するクラス
    """

    def __init__(self, num: int) -> None:
        """
        残機数と表示用アイコン（魔法使い画像）を初期化する
        引数 num: 初期残機数
        """
        self.num = num
        self.image = pg.transform.scale(
            pg.image.load("fig/wizard.png").convert_alpha(), (35, 45)
        )

    def update(self, screen: pg.Surface) -> None:
        """
        現在の残機数分だけ画面右下（下から50、右から50基準）にアイコンをblitする
        引数 screen: 描画対象の画面Surface
        """
        for i in range(self.num):
            rect = self.image.get_rect(
                center=(WIDTH - 50 - i * 40, HEIGHT - 50)
            )
            screen.blit(self.image, rect)


# ============================================================
# 6. 敵の弾：発射した瞬間のプレイヤー位置へ直進する
# ============================================================
class EnemyBullet(pg.sprite.Sprite):
    """
    敵が発射する弾
    """

    def __init__(self, enemy, player):
        super().__init__()

        self.image = pg.Surface((20, 20), pg.SRCALPHA)
        pg.draw.circle(self.image, (255, 60, 60), (10, 10), 10)

        self.rect = self.image.get_rect(
            center=enemy.rect.center
        )

        self.vx, self.vy = calc_orientation(
            enemy.rect, player.rect
        )

        self.x = float(self.rect.x)
        self.y = float(self.rect.y)
        self.speed = 6

    def update(self):
        self.x += self.vx * self.speed
        self.y += self.vy * self.speed

        self.rect.x = round(self.x)
        self.rect.y = round(self.y)

        if self.rect.bottom < 0 or self.rect.top > HEIGHT:
            self.kill()


# ============================================================
# 7. 敵：ランダムに左右へ動き、一定間隔で弾を撃つ
# ============================================================
class Enemy(pg.sprite.Sprite):
    """
    ランダムに左右移動する敵
    """

    def __init__(self, x: int, y: int):
        super().__init__()

        self.image = pg.transform.scale(
            pg.image.load("fig/ghost.png").convert_alpha(), (65, 65)
        )

        self.rect = self.image.get_rect(
            midbottom=(x, y)
        )

        self.speed = random.choice([-2, 2])
        self.move_timer = random.randint(30, 100)
        self.shoot_timer = random.randint(*ENEMY_SHOOT_INTERVAL)


    def update(self):
        self.move_timer -= 1
        self.shoot_timer -= 1

        if self.move_timer <= 0:
            self.speed = random.choice([-2, 0, 2])
            self.move_timer = random.randint(30, 100)

        self.rect.x += self.speed

        if self.rect.left < 0:
            self.rect.left = 0
            self.speed = abs(self.speed) or 2




# ============================================================
# 8. 描画：ワールド座標からカメラ位置を引いて画面へ表示
# ============================================================
def draw_world(screen, camera_x, platforms):
    """
    背景、地面、足場を描画する
    """
    screen.fill((195, 225, 255))

    # 背景の目印
    start_x = max(0, (camera_x // 250) * 250)
    for x in range(start_x, camera_x + WIDTH + 250, 250):
        sx = x - camera_x
        if -100 < sx < WIDTH:
            pg.draw.rect(
                screen, (170, 205, 225),
                (sx, 250, 80, 300)
            )

    # 地面
    pg.draw.rect(
        screen, (100, 175, 95),
        (0, GROUND_Y, WIDTH, HEIGHT - GROUND_Y)
    )

    # 足場
    for platform in platforms:
        screen.blit(
            platform.image,
            platform.rect.move(-camera_x, 0)
        )


def draw_sprites(screen, group, camera_x):
    """
    ワールド座標を画面座標に変換して描画
    """
    for sprite in group:
        screen.blit(
            sprite.image,
            sprite.rect.move(-camera_x, 0)
        )


# ============================================================
# 9. ゲームオーバー：半透明の黒＋白い文字を3秒表示
# ============================================================
def show_game_over(screen: pg.Surface, clock: pg.time.Clock):
    """ゲーム画面に半透明の黒を重ね、GAME OVERを3秒間表示する。"""
    overlay = pg.Surface((WIDTH, HEIGHT), pg.SRCALPHA)
    overlay.fill((0, 0, 0, 160))
    screen.blit(overlay, (0, 0))

    font = pg.font.Font(None, 100)
    text = font.render("GAME OVER", True, (255, 255, 255))
    screen.blit(text, text.get_rect(center=(WIDTH // 2, HEIGHT // 2)))
    pg.display.update()

    start = pg.time.get_ticks()
    while pg.time.get_ticks() - start < GAME_OVER_DURATION:
        for event in pg.event.get():
            if event.type == pg.QUIT:
                return
        clock.tick(FPS)


# ============================================================
# 10. 無限マップ生成：先の足場を追加し、時々「足場なし」を作る
#     低い足場は単発ジャンプ、高い足場は低い足場から登る想定
# ============================================================
def generate_platforms(platforms, next_x, camera_x, last_was_low):
    """画面の先まで足場を作る。空白区間では足場を作らない。"""
    while next_x < camera_x + GENERATE_AHEAD:
        # 空白区間をランダムに挟む（地面は常にあるので通行可能）
        if random.random() < PLATFORM_EMPTY_CHANCE:
            next_x += random.randint(*PLATFORM_EMPTY_LENGTH)
            # 空白の直後に高い足場だけが現れないようリセット
            last_was_low = False
            continue

        width = random.randint(*PLATFORM_WIDTH_RANGE)
        # 高い足場は直前に低い足場がある場合だけ作る
        is_high = last_was_low and random.random() < 0.40
        if is_high:
            height = random.randint(*HIGH_PLATFORM_HEIGHT)
        else:
            height = random.randint(*LOW_PLATFORM_HEIGHT)

        platforms.add(Platform(next_x, GROUND_Y - height, width))

        # 低い足場→高い足場への移動距離は短めにする
        gap = random.randint(60, 105) if not is_high else random.randint(*PLATFORM_GAP_RANGE)
        next_x += width + gap
        last_was_low = not is_high

    return next_x, last_was_low


# ============================================================
# 11. 敵の無限生成：一定期間に1〜3体を時間差で出現させる
# ============================================================

def spawn_one_enemy(enemies, camera_x):
    """右端の少し先に1体だけ出現。近すぎる敵がいれば今回は見送る。"""
    if len(enemies) >= MAX_ENEMIES:
        return False
    spawn_x = camera_x + WIDTH + random.randint(80, 180)
    if any(abs(enemy.rect.centerx - spawn_x) < 180 for enemy in enemies):
        return False
    enemies.add(Enemy(spawn_x, GROUND_Y))
    return True


def schedule_enemy_wave(now):
    """5秒の間に1～3体を時間差で出現させる予約時刻を作る。"""
    count = random.randint(*ENEMIES_PER_WAVE)
    # 同時に現れないよう、最短1秒程度の間隔を取る
    offsets = sorted(random.sample(range(0, ENEMY_SPAWN_INTERVAL, 1000), count))
    return [now + offset + random.randint(0, 300) for offset in offsets]


# ============================================================
# 12. 不要オブジェクトの削除：無限プレイ時の負荷を抑える
# ============================================================
def cleanup_world(platforms, enemies, player_bullets, enemy_bullets, camera_x):
    """遠くに置き去りになったオブジェクトを削除する。"""
    left_limit = camera_x - CLEANUP_BEHIND
    right_limit = camera_x + WIDTH + 350
    for platform in platforms:
        if platform.rect.right < left_limit:
            platform.kill()
    for enemy in enemies:
        if enemy.rect.right < left_limit:
            enemy.kill()
    for group in (player_bullets, enemy_bullets):
        for bullet in group:
            if bullet.rect.right < left_limit or bullet.rect.left > right_limit:
                bullet.kill()


# ============================================================
# 13. メインループ：入力→移動→生成→射撃→当たり判定→描画
# ============================================================
def main():
    pg.display.set_caption("RUN & GUN - Endless")
    screen = pg.display.set_mode((WIDTH, HEIGHT))

    # スプライトグループ：種類ごとに更新・衝突判定を管理する
    player = Player((200, 400))
    platforms = pg.sprite.Group()
    enemies = pg.sprite.Group()
    player_bullets = pg.sprite.Group()
    enemy_bullets = pg.sprite.Group()

    # --- 追加機能：残機数（初期残機3でLifeインスタンスを生成） ---
    life = Life(3)

    # カメラは右方向に無限追従し、左へは少し戻れる
    camera_x = 0
    furthest_camera_x = 0
    next_platform_x = 350
    last_was_low = False
    next_platform_x, last_was_low = generate_platforms(platforms, next_platform_x, camera_x, last_was_low)
    last_spawn_time = pg.time.get_ticks()
    enemy_spawn_schedule = schedule_enemy_wave(last_spawn_time)
    clock = pg.time.Clock()
    running = True

    while running:
        # (1) キー入力と終了操作
        jump_pressed = False
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    running = False
                elif event.key == pg.K_UP:
                    jump_pressed = True
        if not running:
            break

        # (2) プレイヤーの移動・ジャンプ・重力
        key_lst = pg.key.get_pressed()
        player.update(key_lst, platforms, jump_pressed)
        # 右へ進むと中央付近で追従。左へ戻ると画面左寄りでカメラも戻る。
        # ただし、過去に進んだ最遠地点から400px以上はカメラを戻さない。
        if player.rect.centerx > camera_x + WIDTH // 2:
            camera_x = player.rect.centerx - WIDTH // 2
        elif player.rect.centerx < camera_x + LEFT_CAMERA_MARGIN:
            camera_x = player.rect.centerx - LEFT_CAMERA_MARGIN

        furthest_camera_x = max(furthest_camera_x, camera_x)
        camera_x = max(0, furthest_camera_x - MAX_CAMERA_BACKTRACK, camera_x)

        # カメラより左へはみ出さないようにする
        if player.rect.left < camera_x:
            player.rect.left = camera_x
        next_platform_x, last_was_low = generate_platforms(platforms, next_platform_x, camera_x, last_was_low)

        # (3) 敵の生成：5秒ごとに1〜3体を予約し、それぞれ時間差で1体ずつ生成
        now = pg.time.get_ticks()
        if now - last_spawn_time >= ENEMY_SPAWN_INTERVAL:
            last_spawn_time = now
            enemy_spawn_schedule = schedule_enemy_wave(now)
        if enemy_spawn_schedule and now >= enemy_spawn_schedule[0]:
            if spawn_one_enemy(enemies, camera_x):
                enemy_spawn_schedule.pop(0)
            else:
                # 敵同士が重ならないよう、少し待って再試行
                enemy_spawn_schedule[0] = now + 500

        # (4) 自機の射撃（クールダウン中は発射しない）
        if key_lst[pg.K_SPACE] and player.shoot_cooldown == 0:
            # --- 追加機能：弾幕（左Shiftキー同時押しで5方向ビームを発射） ---
            if key_lst[pg.K_LSHIFT]:
                neobeam = NeoBeam(player, 5)
                player_bullets.add(neobeam.gen_beams())
            else:
                player_bullets.add(PlayerBullet(player))
            player.shoot_cooldown = 10

        # (5) 敵の移動と射撃
        enemies.update()
        for enemy in enemies:
            if enemy.shoot_timer <= 0:
                # 遠くの敵からは弾を発射しない
                if camera_x - 100 <= enemy.rect.centerx <= camera_x + WIDTH + 100:
                    enemy_bullets.add(EnemyBullet(enemy, player))
                enemy.shoot_timer = random.randint(*ENEMY_SHOOT_INTERVAL)

        # (6) 弾の移動と当たり判定：弾同士は相殺、敵は一撃で倒す
        player_bullets.update()
        enemy_bullets.update()
        pg.sprite.groupcollide(player_bullets, enemy_bullets, True, True)
        pg.sprite.groupcollide(enemies, player_bullets, True, True)

        # (7) プレイヤー被弾：ライフ制（残機0でゲームオーバー）
        hit_by_bullet = bool(pg.sprite.spritecollide(player, enemy_bullets, True))
        hit_by_enemy = bool(pg.sprite.spritecollide(player, enemies, True))
        # --- 追加機能：残機数（被弾・接触時に残機を1減算し、0以下でゲームオーバー） ---
        if hit_by_bullet or hit_by_enemy:
            life.num -= 1
        game_over = life.num <= 0

        # (8) 古いオブジェクトの削除と画面描画
        cleanup_world(platforms, enemies, player_bullets, enemy_bullets, camera_x)
        draw_world(screen, camera_x, platforms)
        screen.blit(player.image, player.rect.move(-camera_x, 0))
        draw_sprites(screen, enemies, camera_x)
        draw_sprites(screen, player_bullets, camera_x)
        draw_sprites(screen, enemy_bullets, camera_x)
        # --- 追加機能：残機数（残機アイコンの描画） ---
        life.update(screen)
        pg.display.update()
        # (9) 被弾した場合はGAME OVERを表示して終了
        if game_over:
            show_game_over(screen, clock)
            running = False
        clock.tick(FPS)
    return 0


if __name__ == "__main__":
    pg.init()
    main()
    pg.quit()
    sys.exit()