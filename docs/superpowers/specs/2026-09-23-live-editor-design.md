# Live recipe editor (split-screen preview) — design

## Goal
`python redstone_mini.py --serve` opens a local split-screen web editor: recipe
textarea on the left, live 3D preview on the right (the existing preview, with
all models/interactions), recompiling as you type.

## Launch
- `redstone_mini.py --serve [port]` (default 8000) is the only user-facing
  command. Server logic lives in a new `serve.py` module; the CLI stays thin.
- Auto-opens the browser to `http://127.0.0.1:PORT/`.

## Layout & flow
- `editor.html`: left pane = monospace textarea; right pane = preview `<iframe>`
  plus a status line and a Pause/Resume button.
- Keystroke -> 400ms debounce -> POST `/compile` (recipe body) -> response is
  the full built preview HTML -> swap `iframe.srcdoc`.
- Pause button stops auto-recompile (typing edits text only); Resume compiles
  immediately and resumes live updates.
- Status line shows `ok: N blocks` or the compiler error (e.g.
  `line 3: can't parse: ...`) with its line; preview keeps the last good build.
- Starting content is the built-in demo recipe, live on first paint.

## Server
- stdlib `http.server` only; no new dependency.
- Routes: `GET /` -> editor page; `POST /compile` -> `parse_recipe` ->
  `layout_retry(verify=True)` -> `export_html` to a temp file -> return HTML.
- Errors return HTTP 400 with the message body so the editor shows the message.
- Compile is synchronous; a big recipe blocks the single-threaded server for a
  few seconds. Acceptable: local single-user dev server
  (ponytail: one-user server; add threading if it ever matters).

## Reuse
- `export_html` is called verbatim, so every model (floor, torches, repeaters),
  the lever click, and the all-off initial paint come for free. No second
  renderer, no duplicated template.

## Bounds
- No save/export from the editor: it is a scratchpad. `python redstone_mini.py
  my.txt` remains the way to write build.html/build.mcfunction to disk.
- No auth/CORS hardening: localhost only.

## Testing
- One assert check (no framework): POST a good recipe returns 200 + HTML
  containing the preview; POST a broken recipe returns 400 + the parse error.
- Manual: run `--serve`, confirm page loads with demo, type a change, confirm
  preview updates; pause, type, confirm no recompile, resume, confirm catch-up.
