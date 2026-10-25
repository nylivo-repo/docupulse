DocuPulse branding: replace these files with your own, keeping the same names. No rebuild is needed:
copy them into frontend/dist/branding/ (or this folder before a build), then reload the page (Ctrl+F5).

  logo.svg              Logo in the sidebar, sign-in page and password screen. Square, shown at 38 px.
                        SVG preferred; a PNG of at least 256 x 256 also works (set brand.logo in config.js
                        to "branding/logo.png").
  favicon.svg           Browser-tab icon for modern browsers. Square SVG, readable at 16 px.
  favicon.ico           Browser-tab icon for older browsers: 16, 32 and 48 px in one .ico file.
  icons/icon-<n>.png    App icons (installed app, Start menu, home screen): 16, 32, 48, 72, 96, 128, 144, 152,
                        192, 384, 512 px. Transparent corners are fine (rounded tile or any shape).
  icons/maskable-192.png, maskable-512.png
                        Android adaptive icons: square, background colour to the edges, logo inside the
                        middle 80 % (the launcher cuts its own circle/squircle).
  icons/apple-touch-icon.png
                        iPhone/iPad home screen, 180 x 180, no transparency (iOS rounds the corners).

Name and tagline: brand in config.js. Installed-app name and colours: manifest.webmanifest
(name, short_name, theme_color, background_color).

Tools: any image editor; or from one 1024 px PNG, e.g. ImageMagick:
  magick logo-1024.png -resize 512x512 icons/icon-512.png      (repeat per size)
  magick logo-1024.png -define icon:auto-resize=48,32,16 favicon.ico
