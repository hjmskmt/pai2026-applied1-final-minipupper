# PC側の開発環境（ROS 2 / エージェント）
# ROS 2 や Python ライブラリはイメージに入れず、リポジトリの pixi.toml で管理する。
# イメージにはシステムライブラリと pixi だけを入れる
FROM ubuntu:22.04

ARG PIXI_VERSION=0.81.0
ARG USERNAME=dev
ARG USER_UID=1000
ARG USER_GID=1000
ENV DEBIAN_FRONTEND=noninteractive \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8

RUN apt-get update && apt-get install -y --no-install-recommends \
      ca-certificates curl git sudo bash-completion \
      # RViz / rqt / Gazebo の表示（X11, OpenGL）。NVIDIA の GL は Container Toolkit が差し込む
      libgl1 libegl1 libglx-mesa0 libegl-mesa0 libgl1-mesa-dri \
      libxkbcommon-x11-0 libxcb-icccm4 libxcb-image0 libxcb-keysyms1 libxcb-randr0 \
      libxcb-render-util0 libxcb-shape0 libxcb-xinerama0 libxcb-xkb1 \
      # 音声（マイク・スピーカー）
      alsa-utils \
    && rm -rf /var/lib/apt/lists/*

# pixi 本体（バージョン固定）
RUN curl -fsSL https://pixi.sh/install.sh \
      | PIXI_VERSION=v${PIXI_VERSION} PIXI_HOME=/usr/local PIXI_NO_PATH_UPDATE=1 bash

# pixi の環境（.pixi）はリポジトリの中に作らず、named volume の ~/.cache に置く
COPY pixi-config.toml /etc/pixi/config.toml

# ホストと同じUID/GIDのユーザーを作り、bind mountしたファイルの所有者をそろえる
RUN groupadd --gid ${USER_GID} ${USERNAME} \
    && useradd -m -s /bin/bash --uid ${USER_UID} --gid ${USER_GID} ${USERNAME} \
    && echo "${USERNAME} ALL=(root) NOPASSWD:ALL" > /etc/sudoers.d/${USERNAME} \
    && mkdir -p /home/${USERNAME}/.cache /ros_ws/src /ros_ws/build /ros_ws/install /ros_ws/log /workspace \
    && chown -R ${USER_UID}:${USER_GID} /home/${USERNAME}/.cache /ros_ws /workspace \
    && echo 'eval "$(pixi completion --shell bash)"' >> /home/${USERNAME}/.bashrc

WORKDIR /workspace
USER ${USERNAME}
