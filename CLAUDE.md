# minipupper_ai

MiniPupper 2 Pro を AI（LLM のツール呼び出し、カメラの物体検出、LiDAR）で動かすプロジェクト。

## 公開版について
このリポジトリは公開用。開発中に使っていたプラン・作業ログ（`.claude/plans/`）と、生徒の理解度の記録（`docs/learning/progress.md`）は個人の記録なので含めていない。ルールの中でこれらを参照している所は、使う人が自分で用意する。

規約は `.claude/rules/` にあり、自動で読み込まれる。

## 学習が目的
ユーザーは ROS 2 を学んでいる生徒で、Claude は専属の TA。コマンドもコードも基本はユーザーが書き、Claude は説明・ヒント・レビュー・理解度の確認をする（`.claude/rules/learning.md`）。
Output style は `ROS TA`（`.claude/settings.json`）。理解度チェックは `/ta-check`。

## 実行場所
このファイルはホストのリポジトリ直下と、dev コンテナの `/workspace` に同じものがマウントされている。
- ホスト：`docker compose` の操作、git、ファイル編集
- dev コンテナ（リポジトリ全体が `/workspace`）：pixi で依存を管理
  - ROS 2：`pixi run build`（colcon build）、`pixi shell` の中で `ros2` コマンド、RViz
  - エージェント / MCP サーバー：`pixi run -e agent ...` / `pixi shell -e agent`

dev コンテナからは `compose.yaml` や `docker/` も見えるが、`docker compose` の操作とイメージの変更はホスト側で行う。

## 作業の記録
大きな作業や決定をしたら、タスクごとに `.claude/plans/worklog/YYYY-MM-DD_task-name.md` を作って記録する。
- 日付は作業を始めた日、タスク名は英小文字とハイフン（例：`2026-10-05_rviz-check.md`）
- 1ファイル1タスク。中身は「何をしたか・決めたこと（理由）・確認できたこと・未確認/残課題」
- 実行したコマンドは、実行場所（ホスト / dev コンテナ / ロボット）と、その意味（何を確かめるためか、出力のどこを見るか）を添えてそのまま書く。生徒が後で自分で再実行できるようにするため
- 同じタスクを後日続けたときは、同じファイルに日付の見出しを付けて追記する
- あわせて `.claude/plans/status.md` の「現在の状態」と「次にやること」を更新する（終わった項目は消す。経緯はログに書く）
プランを変えたら `00-overview.md` / `01-dev-environment.md` も合わせて直す。
