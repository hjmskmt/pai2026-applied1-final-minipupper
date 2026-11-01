# agent

LLM/VLM エージェントと MCP サーバー（プランの A）。`compose.yaml` の `dev` サービスで `/workspace/agent` にマウントされる。
依存は `pixi.toml` の `agent` 環境（`pixi run -e agent ...` / `pixi shell -e agent`）。
