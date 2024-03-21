# Tk Image Viewer

An image viewer that supports both arrow keys and WebP with foreign characters in long paths, unlike IrfanView 64 4.54 and JPEGView 1.0.37.

```cmd
usage: img_viewer.py [-h] [--fullscreen [N]] [--resize [N]] [--quality N] [--update [ms]] [--slideshow [ms]] [--transpose N] [-v] [path]

positional arguments:
  path

options:
  -h, --help            show this help message and exit
  --fullscreen [N], -f [N]
                        run in fullscreen on display N (1-?, default 1)
  --resize [N], -r [N]  resize image to fit window (0-3: none, all, big, small. default 0)
  --quality N, -q N     set antialiasing level (0-5, default 0)
  --update [ms], -u [ms]
                        update interval (default 4000)
  --slideshow [ms], -s [ms]
                        switch to next image every N ms (default 4000)
  --transpose N, -t N   transpose 0-6 flip_left_right, flip_top_bottom, rotate_90, rotate_180, rotate_270, transpose, transverse
  -v, --verbose         set log level
```
