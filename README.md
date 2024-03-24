# Tk Image Viewer

An image viewer that supports arrow keys, HEIC, WebP, foreign characters, long paths, and zip. Unlike IrfanView 64 4.54, JPEGView 1.0.37, and SumatraPDF v3.5.2 64-bit.

```pre
usage: tk_image_viewer [-h] [--fullscreen] [--geometry WxH+X+Y] [--quality N] [--resize [N]] [--slideshow [ms]] [--transpose N] [--update [ms]] [-v] [path]

positional arguments:
  path

options:
  -h, --help            show this help message and exit
  --fullscreen, -f      run fullscreen
  --geometry WxH+X+Y, -g WxH+X+Y
                        set window geometry, eg -g +0+-999
  --quality N, -q N     set antialiasing level (0-5, default 0)
  --resize [N], -r [N]  resize image to fit window (0-3: none, all, big, small. default 1)
  --slideshow [ms], -s [ms]
                        switch to next image every N ms (default 4000)
  --transpose N, -t N   transpose 0-6 flip_left_right, flip_top_bottom, rotate_90, rotate_180, rotate_270, transpose, transverse
  --update [ms], -u [ms]
                        update interval (default 4000)
  -v, --verbose         set log level
```

Binds:

```pre
Escape q - Close fullscreen or app.
F1 h - Show help.
F11 Return f - Toggle fullscreen.
Left Right Up Down Key-1 x - Go to next or previous file.
MouseWheel Button-4 Button-5 - Handle mouse events.
o - Open a file using the filepicker.
s - Save a file using the filepicker.
F5 u - Refresh path info.
b c - Set background color.
Control-MouseWheel minus plus equal - Zoom.
Alt-MouseWheel Alt-minus Alt-plus Alt-equal - Zoom text of overlays.
r - Change type of window fitting.
a - Toggle animation.
Pause - Toggle slideshow.
t - Increment transpose.
T - Decrement transpose.
v - Set verbosity.
i - Toggle info overlay.
Delete - Delete file.
```
