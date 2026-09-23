# Third-party components

- **Noto Sans Thai**, Thai subset, weights 400/700/900, supplied by `@fontsource/noto-sans-thai`.
  Copyright 2022 The Noto Project Authors (https://github.com/notofonts/thai).
  Licensed under SIL Open Font License 1.1. The complete license is included in
  `app/static/fonts/OFL.txt`. Font files are served locally; no Google Fonts request is made.
- **aiohttp** and **Pillow** are installed by `requirements.txt`; their distributions include their respective licenses.
- Emoji rendering uses the browser/device's installed emoji fonts.

Node.js and Playwright are only needed for the optional browser development test.
They are not required by the application or Docker image.
