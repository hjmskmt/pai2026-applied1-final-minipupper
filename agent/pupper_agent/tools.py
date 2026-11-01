"""Claude に渡すツールの定義と実行。

速度や角度の上限は robot.py の Limits でかける。ここでは「方向・割合」を実際の値に直すだけ。
"""

import json
import math

from .robot import RobotBase

# direction → (vx, vy, wz) の向き。大きさは Limits の上限 × speed
DIRECTIONS = {
    "forward": (1, 0, 0),
    "backward": (-1, 0, 0),
    "left": (0, 1, 0),        # 横歩き（ROS は y が左）
    "right": (0, -1, 0),
    "turn_left": (0, 0, 1),   # その場で反時計回り
    "turn_right": (0, 0, -1),
}

TOOLS = [
    {
        "name": "move",
        "description": (
            "ロボット犬を指定した方向に一定時間歩かせる。歩き終わると自動で止まる。"
            "1回の呼び出しは最大5秒。長く歩かせたいときは複数回呼ぶ。"
            "旋回の速さは最大約45°/秒なので、90°回るなら speed=1.0 で約2秒。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": list(DIRECTIONS),
                    "description": "forward/backward=前後, left/right=横歩き, turn_left/turn_right=その場で旋回",
                },
                "seconds": {"type": "number", "description": "歩く時間（秒、0〜5）"},
                "speed": {
                    "type": "number",
                    "description": "最大速度に対する割合（0.1〜1.0）。指定がなければ 0.5",
                },
            },
            "required": ["direction", "seconds", "speed"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "move_distance",
        "description": (
            "ロボット犬を指定した方向にまっすぐ、指定した距離だけ歩かせる。"
            "オドメトリで進んだ距離を測りながら歩き、届いたら止まる。"
            "「30cm 進んで」のように距離で指示されたときは move ではなくこちらを使う。"
            "1回の呼び出しは最大0.5m。それより長いときは、0.5m ずつ複数回呼ぶ。"
            "旋回はできないので、向きを変えるときは move の turn_left / turn_right を使う。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "direction": {
                    "type": "string",
                    "enum": ["forward", "backward", "left", "right"],
                    "description": "forward/backward=前後, left/right=横歩き",
                },
                "meters": {"type": "number", "description": "進む距離（m、0〜0.5）"},
                "speed": {
                    "type": "number",
                    "description": "最大速度に対する割合（0.1〜1.0）。指定がなければ 1.0（遅いと、時間の上限までに着かないことがある）",
                },
            },
            "required": ["direction", "meters", "speed"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "set_pose",
        "description": (
            "その場で体の姿勢を変える（歩かない）。首をかしげる・伏せる・見上げるなど。"
            "角度は度で、roll=左右の傾き（正で右に傾く）、pitch=前後（正で頭が下がる）、"
            "yaw=左右を向く（正で左）。各 ±17° まで。height は標準からの高さ（cm、±3）。"
            "元に戻すときは全部 0。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "roll_deg": {"type": "number"},
                "pitch_deg": {"type": "number"},
                "yaw_deg": {"type": "number"},
                "height_cm": {"type": "number"},
            },
            "required": ["roll_deg", "pitch_deg", "yaw_deg", "height_cm"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "approach",
        "description": (
            "カメラで目的の物を探し、その物の方向へ歩いて、手前（約25cm）で止まる。"
            "「〇〇のところまで行って」のように、物に向かって歩く指示のときに使う。"
            "物は今カメラに写っている必要がある。見えなければ「見失った」と返るので、"
            "move の turn_left / turn_right で少し向きを変えてから、もう一度呼ぶ。最大30秒。"
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "target": {
                    "type": "string",
                    "description": (
                        "探す物を、物体検出（YOLO-World）が分かりやすい短い英語の一般名詞で。"
                        "キャラクター名や固有名詞は見た目の説明に直す（例：モモンガのぬいぐるみ → white plush toy、"
                        "赤いコップ → red cup）"
                    ),
                },
            },
            "required": ["target"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "name": "stop",
        "description": "すぐに歩くのをやめて止まる。",
        "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        "strict": True,
    },
]


def execute(robot: RobotBase, name: str, args: dict) -> str:
    """ツールを実行して、Claude に返す結果の文字列を作る。失敗は例外で知らせる。"""
    if name == "move":
        sx, sy, sz = DIRECTIONS[args["direction"]]
        speed = min(max(float(args["speed"]), 0.1), 1.0)
        lim = robot.limits
        return robot.move(
            sx * lim.max_linear * speed,
            sy * lim.max_linear * speed,
            sz * lim.max_angular * speed,
            float(args["seconds"]),
        )
    if name == "move_distance":
        sx, sy, _ = DIRECTIONS[args["direction"]]
        speed = min(max(float(args["speed"]), 0.1), 1.0)
        lim = robot.limits
        return robot.move_distance(
            sx * lim.max_linear * speed,
            sy * lim.max_linear * speed,
            float(args["meters"]),
        )
    if name == "set_pose":
        return robot.set_pose(
            math.radians(float(args["roll_deg"])),
            math.radians(float(args["pitch_deg"])),
            math.radians(float(args["yaw_deg"])),
            float(args["height_cm"]) / 100.0,
        )
    if name == "approach":
        return robot.approach(str(args["target"]).strip())
    if name == "stop":
        return robot.stop()
    raise ValueError(f"知らないツール: {name} {json.dumps(args, ensure_ascii=False)}")
