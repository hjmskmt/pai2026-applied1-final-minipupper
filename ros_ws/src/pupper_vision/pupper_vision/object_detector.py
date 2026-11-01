"""カメラ画像から、言葉で指定した物を YOLO-World で探すノード。

  subscribe：/image_raw/compressed（sensor_msgs/CompressedImage、JPEG）。Wi-Fi の帯域が足りないため
             パラメータ compressed:=false で /image_raw（sensor_msgs/Image）
  publish  ：/detections（vision_msgs/Detection2DArray）見つからないときは空の配列
             /detections/image（sensor_msgs/Image）枠を描いた画像（RViz・動画用）
  探す物   ：パラメータ target_words（例 "white plush toy"）。変わったときだけ set_classes() する
             ros2 param set /object_detector target_words "white plush toy"

起動（dev コンテナの pixi shell）：
  ros2 run pupper_vision object_detector
"""
import cv2
import numpy as np
import rclpy
from rcl_interfaces.msg import SetParametersResult
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CompressedImage, Image
from ultralytics import YOLO
from vision_msgs.msg import Detection2D, Detection2DArray, ObjectHypothesisWithPose


class ObjectDetector(Node):
    def __init__(self):
        super().__init__('object_detector')
        self.declare_parameter('model', '/data/vision/yolov8s-worldv2.pt')
        self.declare_parameter('conf', 0.3)  # これ未満の確からしさは捨てる
        self.declare_parameter('compressed', True)  # True：JPEG で受け取る（Wi-Fi の負担が約 1/10）
        self.declare_parameter('target_words', '')  # 空のあいだは検出しない

        self.model = YOLO(self.get_parameter('model').value)
        self.has_target = False
        self.add_on_set_parameters_callback(self.on_set_parameters)

        # depth 1：処理が追いつかないときは古い画像を捨て、いちばん新しい画像だけを使う
        if self.get_parameter('compressed').value:
            self.sub = self.create_subscription(
                CompressedImage, '/image_raw/compressed', self.on_image, qos_profile_sensor_data)
        else:
            self.sub = self.create_subscription(Image, '/image_raw', self.on_image, qos_profile_sensor_data)
        self.pub = self.create_publisher(Detection2DArray, '/detections', 10)
        self.pub_image = self.create_publisher(Image, '/detections/image', 1)
        self.get_logger().info('ready（target_words を設定すると検出を始める）')

    def on_set_parameters(self, params):
        """パラメータが変わるとき（set_parameters サービス）に呼ばれる。返り値がサービスの返事になる。"""
        for p in params:
            if p.name != 'target_words':
                continue
            words = [w.strip() for w in p.value.split(',') if w.strip()]
            if not words:
                self.has_target = False
                return SetParametersResult(successful=True, reason='検出を止めた')
            try:
                self.model.set_classes(words)  # 言葉を CLIP で数値に変える（重いので変わったときだけ）
            except Exception as e:
                return SetParametersResult(successful=False, reason=str(e))
            self.has_target = True
            self.get_logger().info(f'探す物：{words}')
        return SetParametersResult(successful=True)

    def on_image(self, msg):
        if not self.has_target:
            return
        frame = to_bgr(msg)
        r = self.model(frame, conf=self.get_parameter('conf').value, verbose=False)[0]

        out = Detection2DArray()
        out.header = msg.header  # いつの画像の結果か（/scan と時刻を合わせるため）

        # TODO（生徒）：r.boxes から、publish する bbox を選んで out.detections に入れる
        #   - r.boxes.xyxy[i]：(x1, y1, x2, y2)、r.boxes.conf[i]：確からしさ、r.names[int(r.boxes.cls[i])]：言葉
        #   - 1つの Detection2D は make_detection(...) で作れる
        #   - 考えること：同じ物に枠が2つ出たら（例：0.69 と 0.36）、どれを送るか。全部送るか、1つだけか
        if len(r.boxes) != 0:
            max_conf_index = 0
            for i in range(1, len(r.boxes)):
                if r.boxes.conf[max_conf_index] < r.boxes.conf[i] :
                   max_conf_index=i
            out.detections.append(make_detection(out.header, *r.boxes.xyxy[max_conf_index].tolist(), score=r.boxes.conf[max_conf_index], label=r.names[int(r.boxes.cls[max_conf_index])])) 


        self.pub.publish(out)
        self.pub_image.publish(from_bgr(r.plot(), msg.header))


def make_detection(header, x1, y1, x2, y2, score, label):
    d = Detection2D()
    d.header = header
    d.bbox.center.position.x = (x1 + x2) / 2.0
    d.bbox.center.position.y = (y1 + y2) / 2.0
    d.bbox.size_x = float(x2 - x1)
    d.bbox.size_y = float(y2 - y1)
    h = ObjectHypothesisWithPose()
    h.hypothesis.class_id = label
    h.hypothesis.score = float(score)
    d.results.append(h)
    return d


def to_bgr(msg):
    """sensor_msgs/Image または CompressedImage → OpenCV の BGR 画像"""
    buf = np.frombuffer(msg.data, dtype=np.uint8)
    if isinstance(msg, CompressedImage):
        return cv2.imdecode(buf, cv2.IMREAD_COLOR)  # JPEG を元の画像に戻す
    if msg.encoding == 'yuv422_yuy2':
        return cv2.cvtColor(buf.reshape(msg.height, msg.width, 2), cv2.COLOR_YUV2BGR_YUY2)
    img = buf.reshape(msg.height, msg.width, 3)
    if msg.encoding == 'rgb8':
        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
    return img


def from_bgr(img, header):
    out = Image()
    out.header = header
    out.height, out.width = img.shape[:2]
    out.encoding = 'bgr8'
    out.step = out.width * 3
    out.data = np.ascontiguousarray(img).tobytes()
    return out


def main():
    rclpy.init()
    node = ObjectDetector()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
