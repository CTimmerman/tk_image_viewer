# Tk Image Viewer

An image viewer that supports arrow keys, HEIC, WebP, foreign characters, long paths, and zip. Unlike IrfanView 64 4.54, JPEGView 1.0.37, and SumatraPDF v3.5.2 64-bit.

On my Windows 11 it reads APNG, AVIF, AVIFS, BLP, BMP, BUFR, BW, CUR, DCX, DDS, DIB, EMF, EML, EPS, FIT, FITS, FLC, FLI, FTC, FTU, GBR, GIF, GRIB, H5, HDF, HEIC, HEICS, HEIF, HEIFS, HIF, ICB, ICNS, ICO, IIM, IM, J2C, J2K, JFIF, JP2, JPC, JPE, JPEG, JPF, JPG, JPX, JXL, MHT, MHTML, MPEG, MPG, MSP, PBM, PCD, PCX, PFM, PGM, PNG, PNM, PPM, PS, PSD, PXR, QOI, RAS, RGB, RGBA, SGI, SVG, SVGZ, TGA, TIF, TIFF, VDA, VST, WEBP, WMF, XBM, XPM, and ZIP, and writes APNG, AVIF, AVIFS, BLP, BMP, BUFR, BW, DDS, DIB, EMF, EPS, GIF, GRIB, H5, HDF, HEIC, HEICS, HEIF, HEIFS, HIF, ICB, ICNS, ICO, IM, J2C, J2K, JFIF, JP2, JPC, JPE, JPEG, JPF, JPG, JPX, JXL, MPO, MSP, PALM, PBM, PCX, PDF, PFM, PGM, PNG, PNM, PPM, PS, RGB, RGBA, SGI, TGA, TIF, TIFF, VDA, VST, WEBP, WMF, and XBM.

## Install

```cmd
install
```

Will take about 9.5 MB if the Python libs aren't already installed.

## Use

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
C - Set background color.
F F11 Return - Toggle fullscreen.
Escape - Close fullscreen or app.
H F1 - Toggle help.
I - Toggle info overlay.
A - Toggle animation.
Comma period - Browse animation frames.
Ctrl+Left Ctrl+Right Ctrl+Up Ctrl+Down - Scroll.
Ctrl+MouseWheel minus plus equal 0 - Zoom.
Q Shift+Q - Set resize quality.
R - Resize type to fit window.
T Shift+T - Transpose image.
Alt+MouseWheel Alt+Minus Alt+Plus Alt+Equal - Zoom text.
B Pause - Toggle slideshow.
X Left Right Up Down BackSpace space MouseWheel Button-4 Button-5 Home End Key-1 - Browse.
O - Set order.
D Delete - Delete file. Bypasses Trash.
P - Pick a file to open.
S - Save file as.
U F5 - Update path info.
Shift+U - Toggle autoupdate.
Ctrl+C Ctrl+Insert - Copy info to clipboard.
Ctrl+V Shift+Insert - Paste image from clipboard.
V - Set verbosity.
B1-Motion - Select area.
B2-Motion - Drag image.
Button-3 - Show menu.
L - Toggle line overlay.
```
