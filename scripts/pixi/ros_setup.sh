# pixi の環境を有効にしたとき、colcon でビルドしたワークスペースも読み込む
if [ -f /ros_ws/install/setup.sh ]; then
  . /ros_ws/install/setup.sh
fi
