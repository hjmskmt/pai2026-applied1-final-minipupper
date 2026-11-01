# minipupper_ai

MiniPupper 2 Pro を、言葉の指示で動かすプロジェクト。

- **言葉で歩かせる**：ユーザーの文を LLM（Gemini、または Claude）が読み、ツール（`move` / `move_distance` / `set_pose` / `approach` / `stop`）を選ぶ。速度と時間の上限は LLM ではなく `agent/pupper_agent/robot.py` が必ずかける → `agent/`
- **言葉で指定した物を探して近づく（`approach`）**：ロボットのカメラ画像を PC の YOLO-World で検出（`white plush toy` のように言葉で指定）し、bbox の向きをカメラで、距離を LiDAR で測る → `ros_ws/src/pupper_vision/`、`agent/pupper_agent/robot.py`
- LiDAR（LDROBOT STL-19P / LD19 相当）の TF と起動 → `ros_ws/src/pupper_bringup/`

開発はすべて Docker コンテナ内で行い、ROS 2（Humble）とエージェントの依存は [pixi](https://pixi.sh) で管理する。

## ディレクトリ構成

```
minipupper_ai/
├── CLAUDE.md / .claude/   # Claude Code を「TA」として使うためのルール・Output style・スキル
├── pixi.toml / pixi.lock  # dev の依存（ROS 2 Humble = RoboStack、エージェント）
├── compose.yaml           # PC 側の dev コンテナ
├── .env.example           # ROS_DOMAIN_ID、API キー、DATA_DIR
├── .devcontainer/dev/     # VS Code Dev Containers
├── docker/dev/            # イメージ定義（GL/X11/音声ライブラリ + pixi）
├── agent/                 # LLM エージェント（ツール呼び出し）と approach の実機テスト
├── ros_ws/
│   ├── colcon.meta
│   └── src/
│       ├── pupper_vision/     # 物体検出ノード（YOLO-World、/image_raw/compressed → /detections）
│       ├── pupper_bringup/    # LiDAR LD19 の起動と TF（base_link → base_laser）
│       ├── mini_pupper_ros/   # 公式（submodule、ros2-dev ブランチ）
│       └── third_party/ldlidar_stl_ros2/  # LiDAR ドライバ（submodule）
├── maps/ / models/
└── scripts/
```

## 前提

- PC：NVIDIA ドライバ、Docker（compose v2）、NVIDIA Container Toolkit
- ロボット：MangDang 公式の ROS 2 Humble イメージ（bringup、カメラ、LiDAR はロボットで起動）
- GUI（RViz など）を使うときは、ホストで `xhost +SI:localuser:$USER`

## セットアップ

```bash
git clone --recursive <this repo>      # 既存クローンなら: git submodule update --init --recursive
cp .env.example .env                   # GEMINI_API_KEY、DATA_DIR などを設定（.env はコミットしない）
docker compose up -d --build dev
docker compose exec dev pixi install --all   # pixi の環境を作る（初回だけ）
```

## 使い方

```bash
docker compose exec dev bash
# ↓ dev コンテナ内（/workspace = リポジトリ）
pixi run build                              # colcon build
pixi shell                                  # ROS 2 の環境（ros2, rviz2 など）
pixi run -e agent agent-gemini              # エージェント（Gemini 版）。GEMINI_API_KEY が必要
pixi run -e agent agent                     # エージェント（Claude 版）。ANTHROPIC_API_KEY が必要
pixi run -e agent agent-gemini --dry-run    # ROS 2 に送らず、値を表示するだけ
```

approach を LLM なしで試す方法は `agent/check_approach.py` の先頭に書いてある。

## 安全

- 速度・連続動作時間の上限はツールの実装側（`robot.py` の `Limits`）でかける。プロンプトだけに頼らない
- 緊急停止：`ros2 topic pub --once /agent/estop std_msgs/msg/Empty`
