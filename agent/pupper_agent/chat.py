"""テキストで指示して、Claude が tool use でロボット犬を動かす対話ループ。

  pixi run -e agent agent --dry-run   # ロボットなしで試す（送る値を表示するだけ）
  pixi run -e agent agent             # ROS 2 に publish する（ロボットで bringup しておく）

止め方：
  - 「ストップ」「stop」と入力 → Claude を通さずにその場で止める
  - 動作中に Ctrl+C → 止めて入力待ちに戻る（もう一度 Ctrl+C で終了）
  - 別のターミナルから：ros2 topic pub --once /agent/estop std_msgs/msg/Empty
"""

import argparse
import json

import anthropic

from .robot import DryRunRobot, Limits, RobotBase, RosRobot
from .tools import TOOLS, execute

MODEL = "claude-opus-5-5"
STOP_WORDS = {"ストップ", "すとっぷ", "止まれ", "とまれ", "止まって", "stop"}

SYSTEM_PROMPT = """\
あなたは四足歩行のロボット犬 Mini Pupper 2 Pro の頭脳です。ユーザーの日本語の指示を、ツール（move / move_distance / set_pose / approach / stop）で実行します。

- 体は約 21×11 cm と小さく、ゆっくり歩きます。前を向いたカメラと LiDAR があり、approach で目的の物まで歩けます（それ以外では周りは見えていません）
- 距離で指示されたら move_distance を使ってください（オドメトリで測って止まります）。時間で指示されたら move を使います
- 実際の移動量はツールの結果に書かれた値だけを伝えてください。結果にないことは推測で言わないでください
- ツールが「時間切れ」「緊急停止」で止まったときは、勝手に続きを歩かないでください。残りを歩くかどうかをユーザーに聞いてください
- 指示があいまいなときや危なそうなときは、短く・遅く動くか、確認してから動いてください
- 「おすわり」「首をかしげて」などの仕草は set_pose で表現してください。終わったら必要に応じて元の姿勢に戻します
- 返答は日本語で短く。何をしたかを一言で伝えてください
"""


class Agent:
    def __init__(self, robot: RobotBase, model: str = MODEL):
        self.robot = robot
        self.model = model
        self.client = anthropic.Anthropic()
        self.messages = []
        # Ctrl+C で中断したツールの結果。次のユーザー発言と一緒に送る（tool_use に必ず結果を返すため）
        self.pending_results = []

    def ask(self, text: str) -> None:
        self.messages.append({
            "role": "user",
            "content": [*self.pending_results, {"type": "text", "text": text}],
        })
        self.pending_results = []

        while True:
            response = self.client.beta.messages.create(
                model=self.model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                tools=TOOLS,
                messages=self.messages,
                output_config={"effort": "low"},  # 短い指示を素早く実行したいので low
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
            self.messages.append({"role": "assistant", "content": response.content})

            for block in response.content:
                if block.type == "text" and block.text.strip():
                    print(f"pupper> {block.text.strip()}")

            if response.stop_reason == "refusal":
                print("pupper> （この依頼は実行できませんでした）")
                return
            if response.stop_reason != "tool_use":
                return  # end_turn / max_tokens など

            self.messages.append({"role": "user", "content": self._run_tools(response.content)})

    def _run_tools(self, content) -> list:
        tool_uses = [b for b in content if b.type == "tool_use"]
        results = []
        try:
            for block in tool_uses:
                print(f"  -> {block.name}({json.dumps(block.input, ensure_ascii=False)})")
                try:
                    out = execute(self.robot, block.name, block.input)
                    results.append({"type": "tool_result", "tool_use_id": block.id, "content": out})
                except Exception as e:  # 入力の不備などは Claude に返して直してもらう
                    results.append({"type": "tool_result", "tool_use_id": block.id,
                                    "content": f"エラー: {e}", "is_error": True})
                print(f"     {results[-1]['content']}")
        except KeyboardInterrupt:
            self.robot.stop()
            done = {r["tool_use_id"] for r in results}
            results += [{"type": "tool_result", "tool_use_id": b.id,
                         "content": "ユーザーが Ctrl+C で中断しました", "is_error": True}
                        for b in tool_uses if b.id not in done]
            self.pending_results = results
            raise
        return results

    def recover_from_interrupt(self) -> None:
        """API 呼び出し中の中断や API エラーのあと、会話の末尾を次に送れる形に戻す。"""
        if self.messages and self.messages[-1]["role"] == "user":
            last = self.messages.pop()
            # ツール結果は捨てられない（直前の tool_use に対応する）ので、次の発言と一緒に送る
            self.pending_results = [c for c in last["content"] if c.get("type") == "tool_result"]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--dry-run", action="store_true", help="ROS 2 に送らず、値を表示するだけ")
    parser.add_argument("--cmd-vel-topic", default="/cmd_vel")
    parser.add_argument("--body-pose-topic", default="/body_pose")
    parser.add_argument("--odom-topic", default="/odom")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()

    limits = Limits()
    if args.dry_run:
        robot = DryRunRobot(limits)
    else:
        robot = RosRobot(limits, args.cmd_vel_topic, args.body_pose_topic, args.odom_topic)
    agent = Agent(robot, args.model)

    mode = "dry-run" if args.dry_run else f"ROS 2（{args.cmd_vel_topic}, {args.body_pose_topic}）"
    print(f"Mini Pupper エージェント [{mode}]  上限: {limits.max_linear} m/s, "
          f"{limits.max_angular} rad/s, 1回 {limits.max_move_seconds} 秒")
    print("「ストップ」で停止、Ctrl+C で中断、Ctrl+D で終了")

    try:
        while True:
            try:
                text = input("you> ").strip()
            except EOFError:
                break
            if not text:
                continue
            if text.lower() in STOP_WORDS:
                print(f"  {robot.stop()}")
                continue
            try:
                agent.ask(text)
            except KeyboardInterrupt:
                print("\n  中断しました（ロボットは停止）")
                agent.recover_from_interrupt()
            except anthropic.APIConnectionError as e:
                print(f"  API に接続できません: {e}")
                agent.recover_from_interrupt()
            except anthropic.RateLimitError:
                print("  レート制限です。少し待ってからもう一度")
                agent.recover_from_interrupt()
            except anthropic.APIStatusError as e:
                print(f"  API エラー {e.status_code}: {e.message}")
                agent.recover_from_interrupt()
    except KeyboardInterrupt:
        print()
    finally:
        robot.shutdown()


if __name__ == "__main__":
    main()
