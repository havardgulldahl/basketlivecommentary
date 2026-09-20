# Basketsnakker

Listen to a live basketball match:

```console
uv run basketsnakker 8426773
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
