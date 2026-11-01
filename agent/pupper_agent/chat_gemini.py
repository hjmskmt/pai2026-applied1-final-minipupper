"""テキストで指示して、Gemini が function calling でロボット犬を動かす対話ループ（chat.py の Gemini 版）。

  pixi run -e agent agent-gemini --dry-run   # ロボットなしで試す（送る値を表示するだけ）
  pixi run -e agent agent-gemini             # ROS 2 に publish する

API キーは環境変数 GEMINI_API_KEY（Google AI Studio で無料で作れる）。
無料枠では、送った内容が Google の改善に使われることがある。

止め方は chat.py と同じ：
  - 「ストップ」「stop」と入力 → Gemini を通さずにその場で止める
  - 動作中に Ctrl+C → 止めて入力待ちに戻る（もう一度 Ctrl+C で終了）
  - 別のターミナルから：ros2 topic pub --once /agent/estop std_msgs/msg/Empty
"""

import argparse

from google import genai
from google.genai import errors, types

from .chat import STOP_WORDS, SYSTEM_PROMPT
from .robot import DryRunRobot, Limits, RobotBase, RosRobot
from .tools import TOOLS, execute
import time

MODEL = "gemini-3.8-flash"  # 無料枠あり

# tools.py の定義（Claude 形式）を Gemini 形式に直す。中身（名前・説明・引数）は同じ
GEMINI_TOOLS = [types.Tool(function_declarations=[
    types.FunctionDeclaration(
        name=t["name"],
        description=t["description"],
        parameters_json_schema=t["input_schema"],
    )
    for t in TOOLS
])]


class Agent:
    def __init__(self, robot: RobotBase, model: str = MODEL):
        self.robot = robot
        self.model = model
        self.client = genai.Client()
        self.config = types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            tools=GEMINI_TOOLS,
            # SDK に勝手にツールを実行させない。実行は自分で書く（Ctrl+C や安全制限を自分で扱うため）
            automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
        )
        self.contents = []
        # Ctrl+C で中断したツールの結果。次のユーザー発言と一緒に送る（function_call に必ず結果を返すため）
        self.pending_results = []

    def ask(self, text: str) -> None:
        self.contents.append(types.Content(
            role="user",
            parts=[*self.pending_results, types.Part.from_text(text=text)],
        ))
        self.pending_results = []

        counter_generate_content=0
        while True:
            t0 = time.perf_counter()     # 今の時刻（秒、小数あり）
            response = self.client.models.generate_content(
                model=self.model, contents=self.contents, config=self.config,
            )
            counter_generate_content +=1
            print(f"t1: {time.perf_counter() - t0:.1f} 秒")
            print(f"count: {counter_generate_content}")
            content = response.candidates[0].content
            self.contents.append(content)

            for part in content.parts or []:
                if part.text and part.text.strip() and not part.thought:
                    print(f"pupper> {part.text.strip()}")

            if not response.function_calls:
                return  # ツールを呼ばなかった＝返事だけで終わり

            self.contents.append(types.Content(role="user", parts=self._run_tools(response.function_calls)))
            print(f"t2: {time.perf_counter() - t0:.1f} 秒")

    def _run_tools(self, function_calls) -> list:
        results = []
        try:
            for fc in function_calls:
                print(f"  -> {fc.name}({dict(fc.args or {})})")
                # 結果は output、失敗は error のキーで返す（FunctionResponse の約束）

                try:
                    out = execute(self.robot, fc.name, fc.args)
                    response={"output":out}
                except Exception as e:
                    response={"error":str(e)}
                print(f"  {response}")
                results.append(types.Part.from_function_response(
                    name=fc.name, response=response
                            ))

        except KeyboardInterrupt:
            self.robot.stop()
            done = len(results)
            results += [types.Part.from_function_response(
                            name=fc.name, response={"error": "ユーザーが Ctrl+C で中断しました"})
                        for fc in function_calls[done:]]
            self.pending_results = results
            raise
        return results

    def recover_from_interrupt(self) -> None:
        """API 呼び出し中の中断や API エラーのあと、会話の末尾を次に送れる形に戻す。"""
        if self.contents and self.contents[-1].role == "user":
            last = self.contents.pop()
            # ツール結果は捨てられない（直前の function_call に対応する）ので、次の発言と一緒に送る
            self.pending_results = [p for p in last.parts if p.function_response]


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
    print(f"Mini Pupper エージェント（{args.model}） [{mode}]  上限: {limits.max_linear} m/s, "
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
            except errors.APIError as e:  # 429 は無料枠の回数制限
                print(f"  API エラー {e.code}: {e.message}")
                agent.recover_from_interrupt()
    except KeyboardInterrupt:
        print()
    finally:
        robot.shutdown()


if __name__ == "__main__":
    main()
