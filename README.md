# Tk Image Viewer

An image viewer that supports both arrow keys and WebP with foreign characters in long paths, unlike IrfanView 64 4.54 and JPEGView 1.0.37.

```pre
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

Binds:

```pre
<Escape>: close
<f>: fullscreen_toggle
<F11>: fullscreen_toggle
<Return>: fullscreen_toggle
<Left>: browse
<Right>: browse
<Up>: browse
<Down>: browse
<MouseWheel>: mouse_wheel
<Button-4>: mouse_wheel
<Button-5>: mouse_wheel
<u>: paths_update
<F5>: paths_update
<c>: set_bg
<Control-MouseWheel>: zoom
<minus>: zoom
<plus>: zoom
<equal>: zoom
<s>: slideshow_toggle
<Pause>: slideshow_toggle
<t>: transpose_inc
<T>: transpose_dec
<v>: set_verbosity
<i>: info_toggle
<Configure>: resize_handler
<Delete>: delete_file
```
