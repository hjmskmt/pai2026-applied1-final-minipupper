---
paths:
  - "ros_ws/**"
  - "src/**"
---

# ROS 2 のルール

- ディストリビューションは Humble（ロボットの公式イメージに合わせる）。PC 側は RoboStack（`pixi.toml`）の Humble を使う
- ビルドは dev コンテナで `pixi run build`（`/ros_ws` に対して `colcon build --symlink-install`）。オプションは後ろに付ける（例：`pixi run build --packages-select pupper_bringup`）
- submodule のビルドを直したいときは、ソースを変えずに `ros_ws/colcon.meta` でパッケージごとの cmake 引数を足す
- `ros_ws/src/mini_pupper_ros` と `ros_ws/src/third_party/*` は git submodule。直接編集しない。挙動を変えたいときは自作パッケージで launch や設定を上書きする
- 自作パッケージは `ros_ws/src/` 直下に `pupper_` で始まる名前で作る（例：`pupper_bringup`, `pupper_nav`, `pupper_policy`）
- PC とロボットは `.env` の `ROS_DOMAIN_ID` を合わせる。RMW もロボット側（公式イメージはデフォルトの Fast DDS）に合わせる
- SLAM の地図は `/maps`（リポジトリの `maps/`）に保存する
