# Tk Image Viewer

An image viewer that supports arrow keys, HEIC, WebP, foreign characters, long paths, and zip. Unlike IrfanView 64 4.54, JPEGView 1.0.37, and SumatraPDF v3.5.2 64-bit.

```pre
usage: tk_image_viewer [-h] [-f] [-g WxH+X+Y] [-o ORDER] [-q N] [-r [N]] [-s [ms]] [-t N] [-u [ms]] [-v] [path]

positional arguments:
  path

options:
  -h, --help            show this help message and exit
  -f, --fullscreen      run fullscreen
  -g WxH+X+Y, --geometry WxH+X+Y
                        set window geometry, eg -g +0+-999
  -o ORDER, --order ORDER
                        sort order. [NATURAL|string|random|mtime|ctime|size]
  -q N, --quality N     set antialiasing level (0-5, default 0)
  -r [N], --resize [N]  resize image to fit window (0-3: none, all, big, small. default 1)
  -s [ms], --slideshow [ms]
                        switch to next image every N ms (default 4000)
  -t N, --transpose N   transpose 0-6 flip_left_right, flip_top_bottom, rotate_90, rotate_180, rotate_270, transpose, transverse
  -u [ms], --update [ms]
                        update interval (default 4000)
  -v, --verbose         set log level
```

Binds:

```pre
Escape q - Close fullscreen or app.
F1 h - Show help.
F11 Return f - Toggle fullscreen.
Left Right Up Down BackSpace space MouseWheel Button-4 Button-5 Home End Key-1 x - Browse.
comma period - Browse animation frames.
p - Pick a file to open.
s - Save file as.
Delete - Delete file. Bypasses Trash.
F5 u - Update path info.
o - Set order.
b c - Set background color.
B1-Motion B2-Motion B3-Motion - Drag image around.
Ctrl-Left Ctrl-Right Ctrl-Up Ctrl-Down - Scroll.
Ctrl-MouseWheel minus plus equal 0 - Zoom.
Alt-MouseWheel Alt-minus Alt-plus Alt-equal - Zoom text.
r - Resize type to fit window.
a - Toggle animation.
Pause - Toggle slideshow.
l - Toggle line overlay.
t Shift-t - Transpose image.
i - Toggle info overlay.
Ctrl-c - Copy info to clipboard while app is running.
Ctrl-v - Paste image from clipboard.
v - Set verbosity.
```
