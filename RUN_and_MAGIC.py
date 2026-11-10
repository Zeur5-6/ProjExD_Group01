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
AOE_MAX_USES = 3 #使用上限
AOE_RADIUS = 500 #半径
AOE_EFFECT_FRAMES = 25  # 重力場の円が広がりきるまでのフレーム数
MP_ICON_SIZE = (26, 32)  # MPアイコンの表示サイズ（px）

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

    def __init__(self, x: int, y: int, width: int) -> None:
        super().__init__()
        self.image = pg.Surface((width, 20))
        self.image.fill((130, 90, 55))
        self.rect = self.image.get_rect(topleft=(x, y))

    def get_image(self) -> pg.Surface:
        """image を取得する。"""
        return self.image

    def get_rect(self) -> pg.Rect:
        """rect を取得する。"""
        return self.rect


    # 外部のクラス・共通関数から参照する際のgetter
    def get_image(self) -> pg.Surface:
        """image を取得する。"""
        return self.image

    def get_rect(self) -> pg.Rect:
        """rect を取得する。"""
        return self.rect


# ============================================================
# 4. プレイヤー：左右移動・ジャンプ・落下・足場の着地
# ============================================================
class Player(pg.sprite.Sprite):
    """
    プレイヤー（魔法使い）
    """

    delta: dict[int, tuple[int, int]] = {
        pg.K_LEFT: (-1, 0),
        pg.K_RIGHT: (+1, 0),
    }

    def __init__(self, xy: tuple[int, int]) -> None:
        super().__init__()

        self.on_ground = False
        self.can_double_jump = False
        
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
        self.current_platform: Platform | None = None
        self.shoot_cooldown: int = 0
        self.aoe_uses = AOE_MAX_USES  # AOEの使用回数を初期化
        

        self.teleportation_timer = 0 # テレポートクールダウン用タイマー
        self.invincible_timer = 0 # テレポート直後の無敵用のタイマー

    # 外部のクラス・共通関数から参照する際のgetter
    def get_imgs(self) -> dict[tuple[int, int], pg.Surface]:
        """imgs を取得する。"""
        return self.imgs
    def get_dire(self) -> tuple[int, int]:
        """dire を取得する。"""
        return self.dire

    def get_facing(self) -> int:
        """facing を取得する。"""
        return self.facing

    def get_image(self) -> pg.Surface:
        """image を取得する。"""
        return self.image

    def get_rect(self) -> pg.Rect:
        """rect を取得する。"""
        return self.rect

    def get_speed(self) -> int:
        """speed を取得する。"""
        return self.speed

    def get_vy(self) -> float:
        """vy を取得する。"""
        return self.vy

    def get_gravity(self) -> float:
        """gravity を取得する。"""
        return self.gravity

    def get_jump_power(self) -> int:
        """jump_power を取得する。"""
        return self.jump_power

    def get_on_ground(self) -> bool:
        """on_ground を取得する。"""
        return self.on_ground

    def get_y(self) -> float:
        """y を取得する。"""
        return self.y

    def get_drop_timer(self) -> int:
        """drop_timer を取得する。"""
        return self.drop_timer

    def get_current_platform(self) -> Platform | None:
        """current_platform を取得する。"""
        return self.current_platform

    def get_shoot_cooldown(self) -> int:
        """shoot_cooldown を取得する。"""
        return self.shoot_cooldown

    def can_shoot(self) -> bool:
        """射撃可能か判定する。"""
        return self.shoot_cooldown == 0

    def start_shoot_cooldown(self) -> None:
        """発射後の待機時間を設定する。"""
        self.shoot_cooldown = 10
    
    def get_aoe_uses(self) -> int:
        """AOEの残り使用回数を取得する。"""
        return self.aoe_uses
    
    def use_aoe(self) -> bool:
        """AOEを使用し、残り使用回数を減らす。使用可能な場合はTrueを返す。"""
        if self.aoe_uses > 0:
            self.aoe_uses -= 1
            return True
        return False

    def clamp_to_camera(self, camera_x: int) -> None:
        """カメラ左端から出ないよう位置を補正する。"""
        if self.rect.left < camera_x:
            self.rect.left = camera_x

    def update(
        self,
        key_lst: pg.key.ScancodeWrapper,
        platforms: pg.sprite.Group,
        jump_pressed: bool = False,
    ) -> None:
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
            self.can_double_jump = True 
            #地面に着地しているとき、ダブルジャンプが可能になる
        elif jump_pressed and not self.on_ground and self.can_double_jump:
            self.vy = self.jump_power
            self.can_double_jump = False
            # ダブルジャンプを使ったら、もう一度ジャンプできないようにする

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
            self.can_double_jump = True

        # 足場との当たり判定
        elif self.vy >= 0 and self.drop_timer == 0:
            for platform in platforms:
                if (
                    self.rect.right > platform.get_rect().left
                    and self.rect.left < platform.get_rect().right
                    and old_bottom <= platform.get_rect().top
                    and self.rect.bottom >= platform.get_rect().top
                ):
                    self.rect.bottom = platform.get_rect().top
                    self.y = float(self.rect.y)
                    self.vy = 0
                    self.on_ground = True
                    self.current_platform = platform
                    self.can_double_jump = False
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

    def teleportation(self, key_lst):
            """
            テレポート機能
            Cキーと左右どちらかのキーが押されている場合、押されている方向に150ピクセルテレポートする
            また、テレポート直後は無敵になり触れた敵を倒す
            引数 key_lst: 押下されているキーのリストを取得
            """
    
            if self.teleportation_timer == 0:
                if key_lst[pg.K_c] and key_lst[pg.K_LEFT]:  # 左が押されている場合
                    self.rect.x -= 150
                    self.rect.left = max(0, self.rect.left)  # 画面外に出ないように上限を0に
                    self.teleportation_timer = 100  # 連続でテレポートできないようにクールダウンを設ける
                    self.invincible_timer = 10  # テレポート先で敵や弾と接触してもいいように無敵にする
                elif key_lst[pg.K_c] and key_lst[pg.K_RIGHT]:  # 右が押されている場合
                    self.rect.x += 150
                    self.teleportation_timer = 100
                    self.invincible_timer = 10
            else:
                self.teleportation_timer -=1
                self.invincible_timer -=1


# ============================================================
# 5. 自機の弾：Spaceキーで生成され、向いている方向へ進む
# ============================================================
class PlayerBullet(pg.sprite.Sprite):
    """
    プレイヤーの弾（角度指定による斜め発射・弾幕に対応）
    """

    def __init__(self, player: Player, angle0: float = 0) -> None:
        super().__init__()

        img = pg.transform.scale(
            pg.image.load("fig/attack.png").convert_alpha(), PLAYER_BULLET_SIZE
        )
        if player.get_facing() == -1:
            img = pg.transform.flip(img, True, False)
        
        # 弾の画像回転処理
        self.image = pg.transform.rotozoom(img, -angle0 * player.get_facing(), 1.0)

        self.rect = self.image.get_rect()
        self.direction = player.get_facing()
        self.rect.center = (
            player.get_rect().centerx + self.direction * 30,
            player.get_rect().centery
        )

        self.speed = 15

        # 回転角度に応じた速度ベクトルの計算
        rad = math.radians(angle0)
        self.vx = self.speed * math.cos(rad) * self.direction
        self.vy = self.speed * math.sin(rad)
        self.x = float(self.rect.x)
        self.y = float(self.rect.y)

    # 外部のクラス・共通関数から参照する際のgetter
    def get_image(self) -> pg.Surface:
        """image を取得する。"""
        return self.image

    def get_rect(self) -> pg.Rect:
        """rect を取得する。"""
        return self.rect

    def get_direction(self) -> int:
        """direction を取得する。"""
        return self.direction

    def get_speed(self) -> int:
        """speed を取得する。"""
        return self.speed

    def update(self) -> None:
        self.x += self.vx
        self.y += self.vy
        self.rect.x = round(self.x)
        self.rect.y = round(self.y)

        # 画面外の弾はmain()でまとめて削除する


# ============================================================
# 【追加機能】弾幕（NeoBeamクラス）：複数方向への拡散弾生成
# ============================================================
class NeoBeam:
    """
    一度に複数方向へ魔法弾を発射するクラス
    """

    def __init__(self, player: Player, num: int) -> None:
        self.player = player
        self.num = num

    def gen_beams(self) -> list[PlayerBullet]:
        """
        -50°〜+51°の角度範囲で指定数分のPlayerBulletを生成しリストで返す
        """
        beams: list[PlayerBullet] = []
        step = int(100 / (self.num - 1)) if self.num > 1 else 100
        for angle in range(-50, +51, step):
            beams.append(PlayerBullet(self.player, angle))
        return beams


# ============================================================
# 【追加機能】残機数（Lifeクラス）：プレイヤーのライフ管理・描画
# ============================================================
class Life:
    """
    プレイヤー（魔法使い）の残機数を管理し、画面右下にアイコンを描画するクラス
    """

    def __init__(self, num: int) -> None:
        self.num = num
        self.image = pg.transform.scale(
            pg.image.load("fig/wizard.png").convert_alpha(), (35, 45)
        )

    def update(self, screen: pg.Surface) -> None:
        """
        現在の残機数分だけ画面右下（下から50、右から50基準）にアイコンを描画する
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

    def __init__(self, enemy: "Enemy", player: Player) -> None:
        super().__init__()

        self.image = pg.Surface((20, 20), pg.SRCALPHA)
        pg.draw.circle(self.image, (255, 60, 60), (10, 10), 10)

        self.rect = self.image.get_rect(
            center=enemy.get_rect().center
        )

        self.vx, self.vy = calc_orientation(
            enemy.get_rect(), player.get_rect()
        )

        self.x = float(self.rect.x)
        self.y = float(self.rect.y)
        self.speed = 6


    # 外部のクラス・共通関数から参照する際のgetter
    def get_image(self) -> pg.Surface:
        """image を取得する。"""
        return self.image

    def get_rect(self) -> pg.Rect:
        """rect を取得する。"""
        return self.rect

    def get_vx(self) -> float:
        """vx を取得する。"""
        return self.vx

    def get_vy(self) -> float:
        """vy を取得する。"""
        return self.vy

    def get_x(self) -> float:
        """x を取得する。"""
        return self.x

    def get_y(self) -> float:
        """y を取得する。"""
        return self.y

    def get_speed(self) -> int:
        """speed を取得する。"""
        return self.speed

    def update(self) -> None:
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

    def __init__(self, x: int, y: int) -> None:
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

    def get_image(self) -> pg.Surface:
        """image を取得する。"""
        return self.image


    # 外部のクラス・共通関数から参照する際のgetter
    def get_image(self) -> pg.Surface:
        """image を取得する。"""
        return self.image

    def get_rect(self) -> pg.Rect:
        """rect を取得する。"""
        return self.rect

    def get_speed(self) -> int:
        """speed を取得する。"""
        return self.speed

    def get_move_timer(self) -> int:
        """move_timer を取得する。"""
        return self.move_timer

    def get_shoot_timer(self) -> int:
        """shoot_timer を取得する。"""
        return self.shoot_timer

    def can_shoot(self) -> bool:
        """敵の発射待機が終わっているか判定する。"""
        return self.shoot_timer <= 0

    def reset_shoot_timer(self) -> None:
        """次の発射までの待機時間を設定する。"""
        self.shoot_timer = random.randint(*ENEMY_SHOOT_INTERVAL)

    def update(self) -> None:
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
def draw_world(
    screen: pg.Surface, camera_x: int, platforms: pg.sprite.Group
) -> None:
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
            platform.get_image(),
            platform.get_rect().move(-camera_x, 0)
        )


def draw_sprites(
    screen: pg.Surface, group: pg.sprite.Group, camera_x: int
) -> None:
    """
    ワールド座標を画面座標に変換して描画
    """
    for sprite in group:
        screen.blit(
            sprite.get_image(),
            sprite.get_rect().move(-camera_x, 0)
        )


# ============================================================
# 9. ゲームオーバー：半透明の黒＋白い文字を3秒表示
# ============================================================
def show_game_over(screen: pg.Surface, clock: pg.time.Clock) -> None:
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
# ============================================================
def generate_platforms(
    platforms: pg.sprite.Group, next_x: int, camera_x: int, last_was_low: bool
) -> tuple[int, bool]:
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
def spawn_one_enemy(enemies: pg.sprite.Group, camera_x: int) -> bool:
    """右端の少し先に1体だけ出現。近すぎる敵がいれば今回は見送る。"""
    if len(enemies) >= MAX_ENEMIES:
        return False
    spawn_x = camera_x + WIDTH + random.randint(80, 180)
    if any(abs(enemy.get_rect().centerx - spawn_x) < 180 for enemy in enemies):
        return False
    enemies.add(Enemy(spawn_x, GROUND_Y))
    return True


def schedule_enemy_wave(now: int) -> list[int]:
    """5秒の間に1～3体を時間差で出現させる予約時刻を作る。"""
    count = random.randint(*ENEMIES_PER_WAVE)
    # 同時に現れないよう、最短1秒程度の間隔を取る
    offsets = sorted(random.sample(range(0, ENEMY_SPAWN_INTERVAL, 1000), count))
    return [now + offset + random.randint(0, 300) for offset in offsets]


# ============================================================
# 12. 不要オブジェクトの削除：無限プレイ時の負荷を抑える
# ============================================================
def cleanup_world(
    platforms: pg.sprite.Group,
    enemies: pg.sprite.Group,
    player_bullets: pg.sprite.Group,
    enemy_bullets: pg.sprite.Group,
    camera_x: int,
) -> None:
    """遠くに置き去りになったオブジェクトを削除する。"""
    left_limit = camera_x - CLEANUP_BEHIND
    right_limit = camera_x + WIDTH + 350
    for platform in platforms:
        if platform.get_rect().right < left_limit:
            platform.kill()
    for enemy in enemies:
        if enemy.get_rect().right < left_limit:
            enemy.kill()
    for group in (player_bullets, enemy_bullets):
        for bullet in group:
            if bullet.get_rect().right < left_limit or bullet.get_rect().left > right_limit:
                bullet.kill()


# ============================================================
# 13. メインループ：入力→移動→生成→射撃→当たり判定→描画
# ============================================================
def main() -> int:
    pg.display.set_caption("RUN & GUN - Endless")
    screen = pg.display.set_mode((WIDTH, HEIGHT))

    # スプライトグループ：種類ごとに更新・衝突判定を管理する
    player = Player((200, 400))
    player_collider = pg.sprite.Group(player)  # テレポート直後無敵用のプレイヤーの当たり判定
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
    mp_full = pg.transform.scale(
        pg.image.load("fig/portion.png").convert_alpha(), MP_ICON_SIZE
    )  # 残っているMP
    mp_empty = mp_full.copy()
    mp_empty.set_alpha(70)  # 使用済みのMPは薄く表示する
    aoe_timer = 0  # 重力場の円を表示する残りフレーム

    while running:
        # (1) キー入力と終了操作
        jump_pressed = False
        aoe_pressed = False
        for event in pg.event.get():
            if event.type == pg.QUIT:
                running = False
            elif event.type == pg.KEYDOWN:
                if event.key == pg.K_ESCAPE:
                    running = False
                elif event.key == pg.K_UP:
                    jump_pressed = True
                elif event.key == pg.K_x:
                    aoe_pressed = True
        if not running:
            break

        # (2) プレイヤーの移動・ジャンプ・重力
        key_lst = pg.key.get_pressed()
        player.update(key_lst, platforms, jump_pressed)
        # 右へ進むと中央付近で追従。左へ戻ると画面左寄りでカメラも戻る。
        # ただし、過去に進んだ最遠地点から400px以上はカメラを戻さない。
        player.teleportation(key_lst)

        if player.get_rect().centerx > camera_x + WIDTH // 2:
            camera_x = player.get_rect().centerx - WIDTH // 2
        elif player.get_rect().centerx < camera_x + LEFT_CAMERA_MARGIN:
            camera_x = player.get_rect().centerx - LEFT_CAMERA_MARGIN

        furthest_camera_x = max(furthest_camera_x, camera_x)
        camera_x = max(0, furthest_camera_x - MAX_CAMERA_BACKTRACK, camera_x)

        # カメラより左へはみ出さないようにする
        player.clamp_to_camera(camera_x)
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
        if key_lst[pg.K_SPACE] and player.can_shoot():
            # --- 追加機能：弾幕（左Shiftキー同時押しで5方向へ魔法弾を発射） ---
            if key_lst[pg.K_LSHIFT]:
                neobeam = NeoBeam(player, 5)
                player_bullets.add(neobeam.gen_beams())
            else:
                player_bullets.add(PlayerBullet(player))
            player.start_shoot_cooldown()

        # (5) 敵の移動と射撃
        enemies.update()
        for enemy in enemies:
            if enemy.can_shoot():
                # 遠くの敵からは弾を発射しない
                if camera_x - 100 <= enemy.get_rect().centerx <= camera_x + WIDTH + 100:
                    enemy_bullets.add(EnemyBullet(enemy, player))
                enemy.reset_shoot_timer()

        # (6) 弾の移動と当たり判定：弾同士は相殺、敵は一撃で倒す
        player_bullets.update()
        enemy_bullets.update()
        pg.sprite.groupcollide(player_bullets, enemy_bullets, True, True)
        pg.sprite.groupcollide(enemies, player_bullets, True, True)

        # (6.5) AOE攻撃：プレイヤー中心の円の中の敵と敵弾を消す
        if aoe_pressed and player.use_aoe():
            aoe_timer = AOE_EFFECT_FRAMES
            
        if aoe_timer > 0:
            aoe_r = AOE_RADIUS * (AOE_EFFECT_FRAMES - aoe_timer + 1) // AOE_EFFECT_FRAMES
            cx, cy = player.get_rect().center
            
            for enemy in enemies:
                ex, ey = enemy.get_rect().center
                if math.hypot(ex - cx, ey - cy) <= aoe_r:
                    enemy.kill()

            for bullet in enemy_bullets:
                bx, by = bullet.get_rect().center
                if math.hypot(bx - cx, by - cy) <= aoe_r:
                    bullet.kill()

        # (7) プレイヤー被弾：【追加機能】残機数管理と無敵時間の判定
        if player.invincible_timer > 0:  # テレポート直後の無敵時の処理
            pg.sprite.groupcollide(player_collider, enemy_bullets, False, True)  # 被弾した弾を消す
            pg.sprite.groupcollide(player_collider, enemies, False, True)  # 接触した敵を消す
        else:  # 無敵がない場合の被弾処理
            hit_by_bullet = bool(pg.sprite.spritecollide(player, enemy_bullets, True))
            hit_by_enemy = pg.sprite.spritecollideany(player, enemies) is not None

            if hit_by_bullet or hit_by_enemy:
                life.num -= 1
        
        game_over = life.num <= 0

        # (8) 古いオブジェクトの削除と画面描画
        cleanup_world(platforms, enemies, player_bullets, enemy_bullets, camera_x)
        draw_world(screen, camera_x, platforms)
        screen.blit(player.get_image(), player.get_rect().move(-camera_x, 0))
        draw_sprites(screen, enemies, camera_x)
        draw_sprites(screen, player_bullets, camera_x)
        draw_sprites(screen, enemy_bullets, camera_x)

        # 重力場の円：キャラクターから広がっていく
        if aoe_timer > 0:
            r = AOE_RADIUS * (AOE_EFFECT_FRAMES - aoe_timer + 1) // AOE_EFFECT_FRAMES
            center = player.get_rect().move(-camera_x, 0).center
            pg.draw.circle(screen, (150, 90, 255), center, r, 6)
            aoe_timer -= 1

        # AOEの残り回数をMPアイコンで表示
        for i in range(AOE_MAX_USES):
            icon = mp_full if i < player.get_aoe_uses() else mp_empty
            screen.blit(icon, (20 + i * 40, 15))

        
        # --- 追加機能：残機数（残機アイコンの描画） ---
        life.update(screen)
        
        pg.display.update()
        # (9) 被弾して残機が尽きた場合はGAME OVERを表示して終了
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