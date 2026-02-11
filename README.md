# Tk Image Viewer

An image viewer that supports arrow keys, HEIC, WebP, foreign characters, long paths, and archives. Unlike IrfanView 64 4.54, JPEGView 1.0.37, and SumatraPDF v3.5.2 64-bit.

On my Windows 11 it 88 formats:
APNG, AVIF, AVIFS, BLP, BMP, BUFR, BW, CUR, DCX, DDS, DIB, EMF, EML, EPS, FIT, FITS, FLC, FLI, FTC, FTU, GBR, GIF, GRIB, H5, HDF, HEIC, HEICS, HEIF, HEIFS, HIF, ICB, ICNS, ICO, IIM, IM, J2C, J2K, JFIF, JP2, JPC, JPE, JPEG, JPF, JPG, JPX, JXL, MHT, MHTML, MPEG, MPG, MSP, PBM, PCD, PCX, PFM, PGM, PNG, PNM, PPM, PS, PSD, PXR, QOI, RAS, RGB, RGBA, SGI, SVG, SVGZ, TAR, TAR.BZ2, TAR.GZ, TAR.XZ, TAR.ZST, TAR.ZSTD, TBZ2, TGA, TGZ, TIF, TIFF, TXZ, VDA, VST, WEBP, WMF, XBM, XPM, ZIP

Reads 85 formats:
APNG, AVIF, AVIFS, BLP, BMP, BUFR, BW, CUR, DCX, DDS, DIB, EMF, EML, EPS, FLC, FLI, FTC, FTU, GBR, GIF, GRIB, H5, HDF, HEIC, HEICS, HEIF, HEIFS, HIF, ICB, ICNS, ICO, IIM, IM, J2C, J2K, JFIF, JP2, JPC, JPE, JPEG, JPF, JPG, JPX, JXL, MHT, MHTML, MPEG, MPG, MSP, PBM, PCD, PCX, PFM, PGM, PNG, PNM, PPM, PS, PSD, PXR, RAS, RGB, RGBA, SGI, SVG, SVGZ, TAR, TAR.BZ2, TAR.GZ, TAR.XZ, TAR.ZST, TAR.ZSTD, TBZ2, TGA, TGZ, TIF, TIFF, TXZ, VDA, VST, WEBP, WMF, XBM, XPM, ZIP

Writes 59 formats:
APNG, AVIF, AVIFS, BLP, BMP, BUFR, BW, DDS, DIB, EMF, EPS, GIF, GRIB, H5, HDF, HEIC, HEICS, HEIF, HEIFS, HIF, ICB, ICNS, ICO, IM, J2C, J2K, JFIF, JP2, JPC, JPE, JPEG, JPF, JPG, JPX, JXL, MPO, MSP, PALM, PBM, PCX, PDF, PFM, PGM, PNG, PNM, PPM, PS, QOI, RGB, RGBA, SGI, TGA, TIF, TIFF, VDA, VST, WEBP, WMF, XBM

Saves all frames in 15 formats:
APNG, AVIF, AVIFS, GIF, HEIC, HEICS, HEIF, HEIFS, HIF, MPO, PDF, PNG, TIF, TIFF, WEBP

## Install/Update

```cmd
install
```

Will take about 9.5 MB if the Python libs aren't already installed.

To see more metadata, add the 11 MB [exiftool](https://exiftool.org/) folder path to your [PATH environment variable](https://www3.ntu.edu.sg/home/ehchua/programming/howto/Environment_Variables.html).

## Use

```pre
usage: tk_image_viewer [-h] [-b [ms]] [-f] [-g WxH+X+Y] [-m] [-n] [-o ORDER] [-q N] [-r [N]] [-t N] [-u [ms]] [-v] [-z] [path]

positional arguments:
  path

options:
  -h, --help            show this help message and exit
  -b, --browse [ms]     browse to next image every N ms (default 4000)
  -f, --fullscreen      run fullscreen
  -g, --geometry WxH+X+Y
                        set window geometry, eg -g +0+-999
  -m, --maximize        maximize window
  -n, --nofilter        try all file names
  -o, --order ORDER     sort order. [NATURAL|string|random|mtime|ctime|size]
  -q, --quality N       set antialiasing level (0-5, default 0)
  -r, --resize [N]      resize image to fit window (0-3: none, all, big, small. default 1)
  -t, --transpose N     transpose 0-6 flip_left_right, flip_top_bottom, rotate_90, rotate_180, rotate_270, transpose, transverse
  -u, --update [ms]     update interval (default 4000)
  -v, --verbose         set log level
  -z, --archives        browse archives
```

Binds:

```pre
Open file: P F2
Save as: S F12
Copy: Ctrl+C Ctrl+Insert
Paste: Ctrl+V Ctrl+Shift+V Shift+Insert
Delete: D Delete
Find: F3
No filter: N
Refresh: U F5
Autorefresh: Ctrl+U
Order: O Shift+O
Slideshow: B Pause
Browse archives: Z
Animation: A
Browse animation: Comma period
Previous/Next: Wheel
Next: Right Down PageDown space B5
Previous: Left Up PageUp B4
First: 1 Home Alt+Left
Last: End Alt+Right
Index: G F4
0 to 90% of list: Shift+0-9
Random: X
Enter folder: Return
Leave folder: BackSpace
Fullscreen: F F11 Alt+Return
Exit fullscreen or app: Escape
Zoom: 0 equal plus minus Ctrl+Wheel
Zoom text: Alt+Equal Alt+Plus Alt+Minus Alt+Wheel
Drag image: B1-Motion
Scroll: Ctrl+Left Ctrl+Right Ctrl+Up Ctrl+Down
Scroll lock: Scroll_Lock
Select area: B2-Motion Ctrl+A
Resize: R
Resize quality: Q Shift+Q
Background color: C
Transpose: T Shift+T
Line overlay: L
Verbosity: V Shift+V
Menu: B3 F10
Help: H F1
Info: I
```
