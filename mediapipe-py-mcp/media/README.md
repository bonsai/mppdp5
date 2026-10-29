# media

Drop pose images here (`.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`) and the MCP
tools will find them:

- `mp_list_media` lists what is here.
- `mp_analyze_image` / `mp_emit_osc` read one file by name.

Notes:

- Files here are **your data** and are git-ignored (`media/*`, except this
  README). Do not commit personal photos.
- Images are read only; nothing is written back. Camera frames are never saved.
- Set `MP_MEDIA_ROOT` to point at a different directory entirely.
