This directory stores piece recognition templates for `Chess.app`'s default theme.

Run the following command to generate template files automatically:

```bash
python -m src.main calibrate --bot-color white --board-bottom white --bootstrap-templates
```

Generated files include:

- `manifest.json`
- `empty_light.png`
- `empty_dark.png`
- `piece_*.png`

If you change the `Chess.app` theme or window size, regenerate the templates.
