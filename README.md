# Basketsnakker

Listen to a live basketball match with deterministic, rule-based commentary:

```console
uv sync
uv run basketsnakker 8426773
```

The `match_id` is the match identifier to subscribe to. Commentary is spoken
using the platform's text-to-speech implementation unless `--silent` is used.
Use `--language en` for English commentary and TTS (the default is Norwegian).

## With LLM commentary

LLM commentary uses the [Datasette `llm` Python API](https://llm.datasette.io/)
with the GPT4All plugin and the local
`qwen2-1_5b-instruct-q4_0` model. Install the `llm` CLI and its plugin:

```console
uv tool install llm
llm install llm-gpt4all
```

The project also installs `llm` and `llm-gpt4all` into its `uv` environment.
The application resolves the model with `llm.get_model()` and generates each
batch with `model.prompt(...).text()`.

Confirm that the plugin exposes the model:

```console
uv run llm models list
```

GPT4All downloads the roughly 894 MB model automatically on first use and
stores it in its local model cache.

Then run the local launcher:

```console
./run_local.sh 8426773
```

The launcher syncs dependencies and verifies that the selected model can be
resolved by the Python API. It accepts the following optional arguments:

```console
./run_local.sh <match_id> [model] [language] [window_ms] [--silent]
```

For example, use another model, English, and a one-second batching window:

```console
./run_local.sh 8426773 qwen2-1_5b-instruct-q4_0 en 1000
```

The equivalent direct command is:

```console
uv run basketsnakker 8426773 --use-llm \
	--llm-model qwen2-1_5b-instruct-q4_0 --llm-window-ms 1200
```

`--llm-window-ms` controls how long events are collected before one combined
commentary line is generated. Smaller values reduce latency; larger values can
produce more coherent lines for related events.

## Without an LLM

Do not pass `--use-llm`. The default commentary engine uses the built-in
deterministic commentary and does not require the `llm` plugin or a downloaded
language model:

```console
uv run basketsnakker 8426773
```

To run without audio output:

```console
uv run basketsnakker 8426773 --silent
```

List every locally recorded game that has cached metadata:

```console
uv run basketsnakker --list-games
```

Generate missing summaries for completed games and show the updated overview:

```console
uv run basketsnakker --generate-missing-summaries
```

A game is marked complete only when its recorded event logs contain the match
end event. Summaries are never generated for incomplete recordings.
