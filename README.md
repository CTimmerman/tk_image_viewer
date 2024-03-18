# Tk Image Viewer

An image viewer that supports both arrow keys and WebP with foreign characters in long paths.

```cmd
usage: img_viewer.py [-h] [-f FIT] [-q QUALITY] [-s [N]] [-t T] [-v] [path]

positional arguments:
  path

options:
  -h, --help            show this help message and exit
  -f FIT, --fit FIT     fit window (0-1, default 0)
  -q QUALITY, --quality QUALITY
                        set antialiasing level (0-5, default 0)
  -s [N], --slideshow [N]
                        switch to next image every N ms (default 4000)
  -t T, --transpose T   transpose 0-6 FLIP_LEFT_RIGHT, FLIP_TOP_BOTTOM, ROTATE_90, ROTATE_180, ROTATE_270, TRANSPOSE, TRANSVERSE
  -v, --verbose         set log level
```
