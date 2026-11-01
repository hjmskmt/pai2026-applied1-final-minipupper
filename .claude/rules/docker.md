# Docker での開発ルール

- ホストPCには ROS 2・Python ライブラリ・CUDA Toolkit・pixi をインストールしない。ホストに置くのは NVIDIA ドライバ、Docker、NVIDIA Container Toolkit だけ
- PC 側のコンテナは `dev`（ROS 2 とエージェント。依存は pixi）。むやみにサービスやイメージを増やさない
- dev の依存（ROS パッケージ、Python ライブラリ）はリポジトリ直下の `pixi.toml` に書く。dev コンテナ内で `pixi add`（PyPI のみのものは `pixi add --pypi`）を使い、`pixi.lock` もコミットする。イメージの再ビルドは不要
  - `ros_ws/src` の package.xml に依存を足したら、対応する conda パッケージ（`ros-humble-<名前>`、`_` は `-`）を `pixi.toml` にも足す（rosdep は使わない）
  - `docker/dev/Dockerfile` に入れるのは、システムライブラリ（GL・X11・音声）と pixi 本体だけ。これを変えたときだけ `docker compose build dev`
- ROS 2 を使うサービスは `network_mode: host`
- 再生成できるもの（pixi の環境、colcon の build/install/log、キャッシュ類）は named volume に置き、bind mount したソースの中に作らない
- Docker のディスク使用量に気をつける。大きなイメージを取得・ビルドする前に `df -h /` と `docker system df` で空きを確認する
- 重いもの（rosbag、データセット）は `.env` の `DATA_DIR`（コンテナ内では `/data`）に置く。リポジトリの中に大きなファイルを作らない
