"""approach を LLM なしで実機で試す（Gemini の枠を使わない）。

dev コンテナで（ロボットで bringup・LiDAR・カメラ、PC で object_detector を起動しておく）:
  cd /workspace/agent
  pixi run -e agent python check_approach.py look   # 歩かない：見えた向きと距離を表示するだけ
  pixi run -e agent python check_approach.py go     # 歩く：approach を1回（Ctrl+C で止まる）

別のターミナルからの緊急停止：ros2 topic pub --once /agent/estop std_msgs/msg/Empty
"""
import argparse
import math
import time

from pupper_agent.robot import Camera, RosRobot, range_between


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('mode', choices=['look', 'go'])
    ap.add_argument('--words', default='white plush toy')
    args = ap.parse_args()

    robot = RosRobot()
    try:
        time.sleep(1.0)  # /scan と /detections が届くのを待つ
        robot._set_target(args.words)
        if args.mode == 'go':
            print(robot.approach(args.words))
            return
        cam = Camera()
        for _ in range(40):  # 約20秒
            det = robot._get_detection()
            if det is None or det[2] > 1.0:
                print('見えない')
            else:
                x, w, _ = det
                left, right = cam.angle(x - w / 2), cam.angle(x + w / 2)
                dist = range_between(robot._get_scan(), right, left)
                dist_s = '測れない' if dist is None else f'{dist:.2f} m'
                print(f'x={x:5.0f}  向き={math.degrees(cam.angle(x)):+5.1f}°（左が+）'
                      f'  bbox={math.degrees(right):+5.1f}〜{math.degrees(left):+5.1f}°  距離={dist_s}')
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        robot.shutdown()


if __name__ == '__main__':
    main()
