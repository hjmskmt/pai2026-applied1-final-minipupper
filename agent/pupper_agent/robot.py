"""ロボットへの出力と安全制限。

安全制限は LLM のプロンプトではなく、ここで必ずかける（.claude/rules/robot-safety.md）。
- 速度は Limits の上限で切り詰める
- 1回の move は max_move_seconds まで。終わったら必ず速度0を送る
- stop() と /agent/estop（std_msgs/Empty）でいつでも止まる
"""

import math
import threading
import time
from dataclasses import dataclass


@dataclass(frozen=True)
class Limits:
    max_linear: float = 0.3     # m/s（前後・左右）
    max_angular: float = 0.8      # rad/s（その場旋回）
    max_move_seconds: float = 5.0  # 1回の move の最大時間
    max_distance: float = 0.5     # m（1回の move_distance の最大距離。何かおかしくても被害を小さくする）
    max_distance_seconds: float = 15.0  # 1回の move_distance の最大時間（/odom が来なくても必ず止まる）
    max_tilt: float = 0.3         # rad（roll / pitch / yaw、約17°）
    max_height_offset: float = 0.03  # m（標準の高さからの上下）
    publish_hz: float = 10.0      # move 中に /cmd_vel を送る周期
    max_approach_seconds: float = 30.0  # 1回の approach の最大時間
    approach_stop_distance: float = 0.25  # m（LiDAR の距離がこれ以下になったら着いたとする）
    approach_lost_seconds: float = 1.0  # s（これより長く見えなければ「見失った」として止める）


@dataclass(frozen=True)
class Camera:
    """カメラの内部パラメータ（640×480）。10/31 に実測（worklog/2026-10-31_camera.md）"""
    fx: float = 614.0  # 焦点距離（ピクセル）。D=50 cm・左右 ±15 cm に置いた中心 x の差から
    cx: float = 337.0  # 光軸が当たる x（左右対称に置いた2点の中点。画像の中心 320 より少し右）

    def angle(self, x: float) -> float:
        """画像の x（ピクセル）→ base_link での向き（rad、左がプラス）。画像の右は base_link の −y"""
        return -math.atan((x - self.cx) / self.fx)


def clamp(value: float, limit: float) -> float:
    # ROS のメッセージは int を受け付けない（AssertionError）ので必ず float にする
    return float(max(-limit, min(limit, value)))


# base_link から見た LiDAR（base_laser）の向き。pupper_bringup/launch/lidar_ld19.launch.py の TF の yaw
LASER_YAW = -1.57


def scan_index(scan, theta: float) -> int:
    """base_link で theta（rad）の方向に当たる scan.ranges の番号。"""
    # TODO(生徒) B：theta（base_link の向き）に当たる scan.ranges の番号 i を計算する
    #   1. base_link の向き → LiDAR の向き：LiDAR は base_link から LASER_YAW だけ回って付いている
    #   2. LiDAR の向き → 番号：scan.angle_min（0番の向き）と scan.angle_increment（1本ごとの角度）を使う
    #   番号が 0〜n-1 からはみ出したら、1周（n 本）を足し引きして戻す（% n）
    # （10/31 生徒の依頼で TA が実装。base_link の正面 = LiDAR の +1.57 rad は生徒が答えた）
    laser_angle = theta - LASER_YAW
    return int(round((laser_angle - scan.angle_min) / scan.angle_increment)) % len(scan.ranges)


def range_between(scan, theta_right: float, theta_left: float):
    """base_link で theta_right〜theta_left（rad、左がプラス）の間の最も近い距離（m）。測れなければ None。

    bbox の左端・右端の角度を渡す。遠い物ほど bbox が小さくなり、見る本数も自然に減る（11/1 生徒の案）。
    最小値にするのは、bbox の端に入る背景は物より遠いから。物の手前に別の物があると、そちらを拾う（11/1 生徒のメモ）。
    """
    if scan is None:
        return None
    n = len(scan.ranges)
    i_right = scan_index(scan, theta_right)
    count = int(round((theta_left - theta_right) / scan.angle_increment)) + 1  # bbox が細くても最低1本
    values = []
    for k in range(i_right, i_right + max(1, count)):  # LiDAR は左回りに番号が増える
        r = scan.ranges[k % n]
        if scan.range_min < r < scan.range_max:  # 0 や inf（測れなかった値）を除く
            values.append(r)
    return min(values) if values else None


class RobotBase:
    """move / set_pose / stop の共通部分（制限と時間管理）。出力だけ子クラスが実装する。"""

    def __init__(self, limits: Limits = Limits()):
        self.limits = limits
        self._stop_event = threading.Event()

    # ---- 子クラスが実装する出力 ----
    def _publish_velocity(self, vx: float, vy: float, wz: float) -> None:
        raise NotImplementedError

    def _publish_pose(self, roll: float, pitch: float, yaw: float, height: float) -> None:
        raise NotImplementedError

    def _get_position(self):
        """最新の位置 (x, y)（m）。まだ /odom が来ていなければ None。"""
        raise NotImplementedError

    def _set_target(self, words: str) -> str:
        """検出ノードに探す物を設定する。失敗したら例外。"""
        raise NotImplementedError

    def _get_detection(self):
        """最新の検出 (bbox の中心 x, bbox の幅（ピクセル）, 受け取ってからの秒数)。一度も見えていなければ None。"""
        raise NotImplementedError

    def _get_scan(self):
        """最新の /scan（sensor_msgs/LaserScan）。まだ来ていなければ None。"""
        raise NotImplementedError

    # ---- ツールから呼ぶ操作 ----
    def move(self, vx: float, vy: float, wz: float, seconds: float) -> str:
        lim = self.limits
        vx, vy, wz = clamp(vx, lim.max_linear), clamp(vy, lim.max_linear), clamp(wz, lim.max_angular)
        seconds = max(0.0, min(seconds, lim.max_move_seconds))

        self._stop_event.clear()
        period = 1.0 / lim.publish_hz
        deadline = time.monotonic() + seconds
        try:
            # 歩行コントローラは指令が途切れると止まるとは限らないので、動作中は送り続ける
            while time.monotonic() < deadline and not self._stop_event.is_set():
                self._publish_velocity(vx, vy, wz)
                time.sleep(period)
        finally:
            # 例外や Ctrl+C でも必ず止める
            self._publish_velocity(0.0, 0.0, 0.0)

        if self._stop_event.is_set():
            return "緊急停止で中断しました"
        return f"完了: vx={vx:.2f} m/s, vy={vy:.2f} m/s, wz={wz:.2f} rad/s を {seconds:.1f} 秒"

    def move_distance(self, vx: float, vy: float, distance: float) -> str:
        """/odom で進んだ距離を測りながら、distance（m）進んだら止まる（フィードバック制御）。"""
        lim = self.limits
        vx, vy = clamp(vx, lim.max_linear), clamp(vy, lim.max_linear)
        distance = max(0.0, min(distance, lim.max_distance))

        start = self._get_position()
        if start is None:
            raise RuntimeError("/odom がまだ届いていないので、距離を測れません")

        self._stop_event.clear()
        period = 1.0 / lim.publish_hz
        deadline = time.monotonic() + lim.max_distance_seconds
        traveled = 0.0
        try:
            while time.monotonic() < deadline and not self._stop_event.is_set():
                # TODO(生徒): ここがフィードバック制御の中心。
                #   1. 今の位置 self._get_position() と start から、進んだ距離 traveled を計算する
                #   2. 目標 distance に届いたら、ループを抜ける
                #   3. 届いていなければ、self._publish_velocity(...) で歩き続ける
                # ヒント：start も今の位置も (x, y) のタプル。距離は math.hypot(dx, dy)
                #         送る速度は move() と同じ（vx, vy, 旋回はしないので wz=0.0
                xs, ys = start
                xnow, ynow = self._get_position()
                traveled = math.hypot(xnow-xs, ynow-ys)
                if  traveled >= distance:
                    break
                self._publish_velocity(vx, vy, 0.0)
                time.sleep(period)
        finally:
            # 例外や Ctrl+C でも必ず止める
            self._publish_velocity(0.0, 0.0, 0.0)

        if self._stop_event.is_set():
            return f"緊急停止で中断しました（{traveled:.2f} m 進んだところ）"
        if traveled < distance:
            return (f"時間切れで止めました: {distance:.2f} m のうち {traveled:.2f} m 進み、残り {distance - traveled:.2f} m。"
                    "続けるかどうかをユーザーに確認してください")
        return f"完了: {traveled:.2f} m 進みました（目標 {distance:.2f} m）"

    def approach(self, words: str, camera: Camera = Camera()) -> str:
        """カメラで words の物を探し、その方向へ歩いて、LiDAR の距離が近くなったら止まる。

        毎回測り直す（ビジュアルサーボ）ので、/odom がずれていても目標からは外れにくい。
        """
        lim = self.limits
        self._set_target(words)

        self._stop_event.clear()
        period = 1.0 / lim.publish_hz
        start = time.monotonic()
        deadline = start + lim.max_approach_seconds
        result = "時間切れで止めました。目標にはまだ着いていません"
        distance = None
        try:
            while time.monotonic() < deadline and not self._stop_event.is_set():
                det = self._get_detection()
                if det is None:
                    # _set_target の直後は、まだ新しい検出が届いていない。始めてからの時間で見失ったかを判断する
                    det = (None, None, time.monotonic() - start)
                if det[2] > lim.approach_lost_seconds:
                    result = f"「{words}」が見えない（見失った）ので止めました"
                    break
                center_x, width, age = det
                if center_x is None or age > 2 * period:
                    # 1〜2回の見逃しはよくある。止まって次の検出を待つ（approach_lost_seconds までは続ける）
                    self._publish_velocity(0.0, 0.0, 0.0)
                    time.sleep(period)
                    continue

                # TODO(生徒) A：bbox の中心 x から、base_link での向き theta（rad、左がプラス）を計算する
                #   camera.fx, camera.cx を使う。画像の右は base_link の −y
                # （10/31 生徒の依頼で TA が実装。式と符号は生徒が導いた）
                theta = camera.angle(center_x)

                # bbox の左右の端の間で最も近い距離。None のこともある（物がスキャン面より低い等）
                distance = range_between(self._get_scan(), camera.angle(center_x + width / 2),
                                         camera.angle(center_x - width / 2))
                if distance is not None and distance <= lim.approach_stop_distance:
                    result = f"着きました（距離 {distance:.2f} m、向き {math.degrees(theta):+.0f}°）"
                    break

                # TODO(生徒) C：theta と distance から、送る速度 vx（前、m/s）と wz（旋回、rad/s、左がプラス）を決める
                #   考えること：向きが大きくずれているときに前へ進むか／遠いときと近いときで速さを変えるか
                #   上限は下の clamp で必ずかかる
                # （10/31 生徒の依頼で TA が実装）
                # 向きは比例制御（ずれに比例して回す）。大きくずれている（20°超）ときは前に進まず、先に向きを合わせる
                wz = 2.0 * theta
                if abs(theta) > math.radians(20):
                    vx = 0.0
                elif distance is None:
                    vx = 0.05  # 距離が測れない（遠い・台が細い等）ときは、ゆっくり近づく
                else:
                    # 止まる距離に近づくほど遅く（0.3 m 手前から減速）。遅すぎると脚が進まないので 0.03 m/s は残す
                    remaining = distance - lim.approach_stop_distance
                    vx = max(0.03, min(0.6 * lim.max_linear, 0.6 * lim.max_linear * remaining / 0.3))

                self._publish_velocity(clamp(vx, lim.max_linear), 0.0, clamp(wz, lim.max_angular))
                time.sleep(period)
        finally:
            # 例外や Ctrl+C でも必ず止める
            self._publish_velocity(0.0, 0.0, 0.0)

        if self._stop_event.is_set():
            return "緊急停止で中断しました"
        if distance is not None and "着きました" not in result:
            result += f"（最後の距離 {distance:.2f} m）"
        return result

    def set_pose(self, roll: float, pitch: float, yaw: float, height: float) -> str:
        lim = self.limits
        roll, pitch, yaw = (clamp(a, lim.max_tilt) for a in (roll, pitch, yaw))
        height = clamp(height, lim.max_height_offset)
        self._publish_pose(roll, pitch, yaw, height)
        return (f"姿勢: roll={math.degrees(roll):.0f}°, pitch={math.degrees(pitch):.0f}°, "
                f"yaw={math.degrees(yaw):.0f}°, height={height * 100:+.1f} cm")

    def stop(self) -> str:
        self._stop_event.set()
        self._publish_velocity(0.0, 0.0, 0.0)
        return "停止しました"

    def shutdown(self) -> None:
        self.stop()


class DryRunRobot(RobotBase):
    """ロボットなしで試す用。送るはずの値を表示するだけ。"""

    def __init__(self, limits: Limits = Limits()):
        super().__init__(limits)
        self._last_velocity = None
        # 位置は、送った速度をそのまま積分して作る（指令どおりに動いたことにする。向きは考えない）
        self._x = self._y = 0.0
        self._vx = self._vy = 0.0
        self._last_time = time.monotonic()

    def _publish_velocity(self, vx, vy, wz):
        self._get_position()  # 速度を変える前に、ここまでの移動を足しておく
        self._vx, self._vy = vx, vy
        # 同じ値を 10Hz で表示すると読めないので、変わったときだけ出す
        if (vx, vy, wz) != self._last_velocity:
            print(f"  [dry-run] /cmd_vel  vx={vx:.2f} vy={vy:.2f} wz={wz:.2f}")
            self._last_velocity = (vx, vy, wz)

    def _get_position(self):
        now = time.monotonic()
        dt, self._last_time = now - self._last_time, now
        self._x += self._vx * dt
        self._y += self._vy * dt
        return (self._x, self._y)

    def _publish_pose(self, roll, pitch, yaw, height):
        print(f"  [dry-run] body_pose roll={roll:.2f} pitch={pitch:.2f} yaw={yaw:.2f} height={height:+.3f}")

    # approach の dry-run：目標は「画像の x=384（少し右）、最初 1.0 m 先」に固定。前に進んだ分だけ近づく
    def _set_target(self, words):
        print(f"  [dry-run] target_words = {words!r}")
        self._x = self._y = 0.0
        return "ok"

    def _get_detection(self):
        return (384.0, 60.0, 0.0)

    def _get_scan(self):
        from types import SimpleNamespace

        x, _ = self._get_position()
        n = 450
        return SimpleNamespace(angle_min=0.0, angle_increment=2 * math.pi / n, range_min=0.02, range_max=12.0,
                               ranges=[max(0.05, 1.0 - x)] * n)


class RosRobot(RobotBase):
    """ROS 2 に publish する。rclpy は dry-run では要らないので、ここで import する。"""

    def __init__(self, limits: Limits = Limits(), cmd_vel_topic: str = "/cmd_vel",
                 body_pose_topic: str = "/body_pose", odom_topic: str = "/odom"):
        super().__init__(limits)
        import rclpy
        from geometry_msgs.msg import Pose, Twist
        from nav_msgs.msg import Odometry
        from rcl_interfaces.msg import Parameter, ParameterType
        from rcl_interfaces.srv import SetParameters
        from rclpy.executors import SingleThreadedExecutor
        from rclpy.qos import qos_profile_sensor_data
        from sensor_msgs.msg import LaserScan
        from vision_msgs.msg import Detection2DArray
        from rclpy.signals import SignalHandlerOptions
        from std_msgs.msg import Empty

        self._Twist, self._Pose = Twist, Pose
        rclpy.init(signal_handler_options=SignalHandlerOptions.NO)
        self._node = rclpy.create_node("pupper_agent")
        self._cmd_pub = self._node.create_publisher(Twist, cmd_vel_topic, 10)
        self._pose_pub = self._node.create_publisher(Pose, body_pose_topic, 10)
        # 別のターミナルや音声ノードからの緊急停止：ros2 topic pub --once /agent/estop std_msgs/msg/Empty
        self._node.create_subscription(Empty, "/agent/estop", lambda _msg: self.stop(), 10)
        # /odom は報告（コントローラ / シミュレータ → ここ）。来るたびに最新の位置を上書きする
        self._position = None
        self._node.create_subscription(Odometry, odom_topic, self._on_odom, 10)
        # approach 用：検出（pupper_vision の object_detector）と LiDAR
        self._Parameter, self._ParameterType, self._SetParameters = Parameter, ParameterType, SetParameters
        self._detection = None  # (bbox の中心 x, bbox の幅, 受け取った時刻 monotonic)
        self._scan = None
        self._node.create_subscription(Detection2DArray, "/detections", self._on_detections, 10)
        self._node.create_subscription(LaserScan, "/scan", self._on_scan, qos_profile_sensor_data)
        self._param_client = self._node.create_client(SetParameters, "/object_detector/set_parameters")

        self._executor = SingleThreadedExecutor()
        self._executor.add_node(self._node)
        self._spin_thread = threading.Thread(target=self._executor.spin, daemon=True)
        self._spin_thread.start()

    def _publish_velocity(self, vx, vy, wz):
        msg = self._Twist()
        msg.linear.x, msg.linear.y, msg.angular.z = vx, vy, wz
        self._cmd_pub.publish(msg)

    def _on_odom(self, msg):
        # spin のスレッドで呼ばれる。タプルの代入は1回で入れ替わるので、読む側が途中の値を見ることはない
        p = msg.pose.pose.position
        self._position = (p.x, p.y)

    def _get_position(self):
        return self._position

    def _on_detections(self, msg):
        # 空（見えていない）のときは更新しない → 受け取ってからの秒数が増えていく
        # 時刻はロボットと PC の時計のずれを避けるため、header.stamp ではなく PC で受け取った時刻を使う
        if msg.detections:
            bbox = msg.detections[0].bbox
            self._detection = (bbox.center.position.x, bbox.size_x, time.monotonic())

    def _on_scan(self, msg):
        self._scan = msg

    def _get_detection(self):
        det = self._detection
        if det is None:
            return None
        return (det[0], det[1], time.monotonic() - det[2])

    def _get_scan(self):
        return self._scan

    def _set_target(self, words):
        """object_detector の target_words を set_parameters サービスで変える（返事を待つ）"""
        if not self._param_client.wait_for_service(timeout_sec=3.0):
            raise RuntimeError("検出ノード（object_detector）が起動していません")
        p = self._Parameter()
        p.name = "target_words"
        p.value.type = self._ParameterType.PARAMETER_STRING
        p.value.string_value = words
        req = self._SetParameters.Request(parameters=[p])
        future = self._param_client.call_async(req)
        deadline = time.monotonic() + 15.0  # 言葉を CLIP で変換するので数秒かかる
        while not future.done() and time.monotonic() < deadline:
            time.sleep(0.05)
        if not future.done():
            raise RuntimeError("検出ノードから返事がありません")
        res = future.result().results[0]
        if not res.successful:
            raise RuntimeError(f"探す物を設定できませんでした: {res.reason}")
        self._detection = None  # 前の物の検出を使わない
        return "ok"

    def _publish_pose(self, roll, pitch, yaw, height):
        msg = self._Pose()
        msg.position.z = height
        # roll/pitch/yaw → クォータニオン（ZYX の順）
        cr, sr = math.cos(roll / 2), math.sin(roll / 2)
        cp, sp = math.cos(pitch / 2), math.sin(pitch / 2)
        cy, sy = math.cos(yaw / 2), math.sin(yaw / 2)
        msg.orientation.w = cr * cp * cy + sr * sp * sy
        msg.orientation.x = sr * cp * cy - cr * sp * sy
        msg.orientation.y = cr * sp * cy + sr * cp * sy
        msg.orientation.z = cr * cp * sy - sr * sp * cy
        self._pose_pub.publish(msg)

    def shutdown(self):
        import rclpy

        self.stop()
        self._executor.shutdown()
        # spin のスレッドが終わる前にノードを壊すと C++ 側が落ちる（terminate called ...）
        self._spin_thread.join(timeout=2.0)
        self._node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
