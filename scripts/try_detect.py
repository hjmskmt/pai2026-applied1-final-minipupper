"""1枚の画像で物体検出を試す（ROS なし）。

dev コンテナの pixi shell で、作業場所は /data/vision（重みファイルがここに落ちる）:
  cd /data/vision
  python /workspace/scripts/try_detect.py momonga.png                       # YOLO11n（COCO の80クラス）
  python /workspace/scripts/try_detect.py momonga.png --conf 0.05           # 弱い候補も表示
  python /workspace/scripts/try_detect.py momonga.png --words "white plush toy" "stuffed animal"  # YOLO-World
"""
import argparse

from ultralytics import YOLO


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('image')
    ap.add_argument('--conf', type=float, default=0.25, help='これ未満の確からしさの候補は捨てる')
    ap.add_argument('--words', nargs='+', help='指定すると YOLO-World で、この言葉の物を探す')
    ap.add_argument('--out', default='result.jpg', help='枠を描いた画像の保存先')
    args = ap.parse_args()

    if args.words:
        model = YOLO('yolov8s-worldv2.pt')
        model.set_classes(args.words)
    else:
        model = YOLO('yolo11n.pt')

    r = model(args.image, conf=args.conf)[0]
    for c, p, b in zip(r.boxes.cls, r.boxes.conf, r.boxes.xyxy):
        x1, y1, x2, y2 = (int(v) for v in b)
        print(f'{r.names[int(c)]:20s} {float(p):.2f}  bbox=({x1},{y1})-({x2},{y2})  中心x={(x1 + x2) // 2}')
    r.save(filename=args.out)  # 枠を描いた画像


if __name__ == '__main__':
    main()
