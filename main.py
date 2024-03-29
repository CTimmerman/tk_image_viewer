# pylint: disable=consider-using-f-string, global-statement, too-many-boolean-expressions, unused-argument
"""Tk Image Viewer
by Cees Timmerman
2024-03-17 First version.
2024-03-23 Save stuff.
2024-03-24 Zip and multiframe image animation support.
2024-03-27 Set sort order. Support EML, MHT, MHTML.
"""
import base64
import enum
import functools
import logging
import os
import pathlib
import re
import time
import tkinter
import zipfile
from io import BytesIO
from random import randint
from tkinter import filedialog, messagebox

from PIL import ExifTags, Image, ImageTk, IptcImagePlugin, TiffTags
from PIL.Image import Transpose
from pillow_heif import register_heif_opener  # type: ignore


class Fits(enum.IntEnum):
    """Types of window fitting."""

    NONE = 0
    ALL = 1
    BIG = 2
    SMALL = 3


ANIMATION_ON = True
BG_COLORS = ["black", "gray10", "gray50", "white"]
BG_INDEX = -1
FIT = 0
FONT_SIZE = 14
IMAGE: Image.Image | None = None
IM_FRAME = 0
INFO: dict = {}
QUALITY = Image.Resampling.NEAREST  # 0
REFRESH_INTERVAL = 0
SCALE = 1.0
SCALE_MIN = 0.001
SCALE_MAX = 40.0
SCALE_TEXT = 1.0
SHOW_INFO = False
SORTS = "natural string ctime mtime size".split()
SORT = "natural"
TITLE = __doc__.split("\n", 1)[0]
TRANSPOSE_INDEX = -1
VERBOSITY_LEVELS = [
    logging.CRITICAL,
    logging.ERROR,
    logging.WARN,
    logging.INFO,
    logging.DEBUG,
]
VERBOSITY = logging.WARNING
WINDOW_SIZE = ""
ZIP_INDEX = 0
paths: list[str] = []
path_index: int = 0

# Add a handler to stream to sys.stderr warnings from all modules.
logging.basicConfig(format="%(levelname)s: %(message)s")
# Add a logging namespace.
log = logging.getLogger(TITLE)

register_heif_opener()


def log_this(func):
    """Decorator to log function calls."""

    @functools.wraps(func)  # Too keep signature.
    def inner(*args, **kwargs):
        log.debug("Calling %s with %s, %s", func.__name__, args, kwargs)
        return func(*args, **kwargs)

    return inner


def animation_toggle(event=None):
    """Toggle animation."""
    global ANIMATION_ON
    ANIMATION_ON = not ANIMATION_ON
    if ANIMATION_ON:
        toast("Starting animation.")
        im_resize(ANIMATION_ON)
    else:
        toast("Stopping animation.")


@log_this
def browse(event=None):
    """Go to next or previous file."""
    global path_index, ZIP_INDEX

    new_index = path_index

    if "Names" in INFO:
        new_index = ZIP_INDEX

    k = event.keysym if event else "Next"
    if k == "1":
        new_index = 0
    elif k == "x":
        new_index = randint(0, len(paths) - 1)
    elif k in ("Left", "Up", "Button-4"):
        new_index -= 1
    else:
        new_index += 1

    if "Names" in INFO:
        if new_index < 0:
            new_index = path_index - 1
        elif new_index >= len(INFO["Names"]):
            new_index = path_index + 1
        else:
            ZIP_INDEX = new_index
            image_load()
            return

    if new_index < 0:
        new_index = len(paths) - 1
    if new_index >= len(paths):
        new_index = 0

    path_index = new_index
    ZIP_INDEX = 0
    image_load()


@log_this
def close(event=None):
    """Close fullscreen or app."""
    if root.overrideredirect():
        fullscreen_toggle()
    else:
        event.widget.withdraw()
        event.widget.quit()


@log_this
def debug_keys(event=None):
    """Show all keys."""


def delete_file(event=None):
    """Delete file."""
    path = paths[path_index]
    msg = f"Delete? {path}"
    log.warning(msg)
    answer = messagebox.askyesno("Delete file?", f"Delete {path}?")
    if answer is True:
        log.warning("Deleting %s", path)
        paths_update()


def help_handler(event=None):
    """Show help."""
    global SHOW_INFO
    SHOW_INFO = not SHOW_INFO
    if SHOW_INFO:
        msg = f"{TITLE}\nBinds:\n" + "\n".join(
            f"{keys} - {fun.__doc__}" for fun, keys in binds if "Configure" not in keys
        )
        log.debug(msg)
        INFO_OVERLAY.config(text=msg)
        INFO_OVERLAY.lift()
    else:
        INFO_OVERLAY.lower()


def set_stats(path):
    """Set stats."""
    global INFO
    stats = os.stat(path)
    log.debug("Stat: %s", stats)
    INFO = {
        # "Path": pathlib.Path(path),
        "Size": f"{stats.st_size:,} B",
        "Accessed": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats.st_atime)),
        "Modified": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(stats.st_mtime)),
        "Created": time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(
                stats.st_birthtime if hasattr(stats, "st_birthtime") else stats.st_ctime
            ),
        ),
    }


def load_mhtml(path):
    """Load EML/MHT/MHTML."""
    global IMAGE
    with open(path, "r", encoding="utf8") as f:
        mhtml = f.read()
    boundary = re.search('boundary="(.+)"', mhtml).group(1)
    parts = mhtml.split(boundary)[1:-1]
    INFO["Names"] = []
    new_parts = []
    for p in parts:
        meta, data = p.split("\n\n", maxsplit=1)
        m = meta.lower()
        if "\ncontent-transfer-encoding: base64" not in m:
            continue
        if "\ncontent-type:" in m and "\ncontent-type: image" not in m:
            continue
        name = sorted(meta.strip().split("\n"))[0].split("/")[-1]
        INFO["Names"].append(name)
        new_parts.append(data)
    data = new_parts[ZIP_INDEX]
    try:
        im_file = BytesIO(base64.standard_b64decode(data.rstrip()))
        IMAGE = Image.open(im_file)
    except ValueError as ex:
        log.error("Failed to split mhtml: %s", ex)
        log.error("DATA %r", data[:180])
        im_file.seek(0)
        log.error("DECODED %s", im_file.read()[:80])


def load_zip(path):
    """Load a zip file."""
    global IMAGE
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        INFO["Names"] = names
        log.debug("Loading name index %s", ZIP_INDEX)
        # pylint: disable=consider-using-with
        IMAGE = Image.open(zf.open(names[ZIP_INDEX]))


def image_load(path=None):
    """Load image."""
    global IMAGE

    if not path:
        path = paths[path_index]

    msg = f"{path_index+1}/{len(paths)} "
    log.debug("Loading %s%s", msg, path)

    err_msg = ""
    try:
        set_stats(path)
        if path.suffix == ".zip":
            load_zip(path)
        elif path.suffix in (".eml", ".mht", ".mhtml"):
            load_mhtml(path)
        else:
            IMAGE = Image.open(path)
        log.debug("Cached %s PIL_IMAGE", IMAGE.size)
        if hasattr(IMAGE, "n_frames"):
            INFO["Frames"] = IMAGE.n_frames
        INFO.update(**IMAGE.info)
        for k, v in INFO.items():
            log.debug(
                "%s: %s",
                k,
                str(v)[:80] + "..." if len(str(v)) > 80 else v,
            )
        im_resize(ANIMATION_ON)
    except (
        tkinter.TclError,
        IOError,
        MemoryError,
        EOFError,
        ValueError,
        BufferError,
        OSError,
    ) as ex:
        err_msg = str(ex)
        log.error(err_msg)
        IMAGE = None
        msg = f"{msg} {err_msg} {path}"
        IMAGE_WIDGET.config(image="", text=msg)
        IMAGE_WIDGET.im = None
        INFO_OVERLAY.config(text=msg)
        root.title(msg + " - " + TITLE)


def get_fit_ratio():
    """Get fit ratio."""
    ratio = 1.0
    w = root.winfo_width()
    h = root.winfo_height()
    im_w, im_h = IMAGE.size
    if (
        ((FIT == Fits.ALL) and (im_w != w or im_h != h))
        or ((FIT == Fits.BIG) and (im_w > w or im_h > h))
        or ((FIT == Fits.SMALL) and (im_w < w and im_h < h))
    ):
        ratio = min(w / im_w, h / im_h)
    return ratio


def im_fit(im):
    """Fit image to window."""
    ratio = get_fit_ratio()
    if ratio != 1.0:
        w, h = im.size
        im = im.resize((int(w * ratio), int(h * ratio)), QUALITY)
    return im


def im_scale(im):
    """Scale image."""
    global SCALE
    log.debug("Scaling to %s", SCALE)
    im_w, im_h = im.size
    ratio = SCALE * get_fit_ratio()
    try:
        new_w = int(ratio * im_w)
        new_h = int(ratio * im_h)
        if new_w < 1 or new_h < 1:
            log.error("Too small. Scaling up.")
            SCALE = max(SCALE_MIN, min(SCALE * 1.1, SCALE_MAX))
            im = im_scale(im)
        else:
            im = IMAGE.resize((new_w, new_h), QUALITY)
    except MemoryError as ex:
        log.error("Out of memory. Scaling down. %s", ex)
        SCALE = max(SCALE_MIN, min(SCALE * 0.9, SCALE_MAX))

    return im


def im_resize(loop=False):
    """Resize image."""
    global IM_FRAME
    if not IMAGE:
        return

    im = IMAGE.copy()

    if FIT:
        im = im_fit(IMAGE)

    if SCALE != 1:
        im = im_scale(IMAGE)

    if TRANSPOSE_INDEX != -1:
        log.debug("Transposing %s", Transpose(TRANSPOSE_INDEX))
        im = im.transpose(TRANSPOSE_INDEX)

    im_show(im)

    if loop and hasattr(IMAGE, "n_frames") and IMAGE.n_frames > 1:
        IM_FRAME = (IM_FRAME + 1) % IMAGE.n_frames
        try:
            IMAGE.seek(IM_FRAME)
        except EOFError as ex:
            log.error("IMAGE EOF. %s", ex)
        duration = INFO["duration"] if "duration" in INFO else 100
        log.debug("Duration %s", duration)
        root.after(duration, im_resize, ANIMATION_ON)


@log_this
def im_show(im):
    """Show PIL image in Tk image widget."""
    global SCALE
    try:
        tkim = ImageTk.PhotoImage(im)  # , format=fmt)
        IMAGE_WIDGET.config(image=tkim, text="")  # Set it.
        IMAGE_WIDGET.tkim = tkim  # Keep it. Why isn't this built in?!
    except MemoryError as ex:
        log.error("Out of memory. Scaling down. %s", ex)
        SCALE = max(SCALE_MIN, min(SCALE * 0.9, SCALE_MAX))
        return

    zip_info = (
        f" {ZIP_INDEX + 1}/{len(INFO['Names'])} {INFO['Names'][ZIP_INDEX]}"
        if "Names" in INFO
        else ""
    )
    msg = (
        f"{path_index+1}/{len(paths)}{zip_info} {'%sx%s' % IMAGE.size}"
        f" @ {'%sx%s' % im.size} {paths[path_index]}"
    )
    root.title(msg + " - " + TITLE)
    INFO_OVERLAY.configure(text=msg + "\n" + info_get())


def info_get() -> str:
    """Get image info."""
    msg = "\n".join(
        f"{k}: {(str(v)[:80] + '...') if len(str(v)) > 80 else v}"
        for k, v in INFO.items()
    )
    if not IMAGE:
        return msg

    # Image File Directories (IFD)
    if hasattr(IMAGE, "tag_v2"):
        meta_dict = {TiffTags.TAGS_V2[key]: IMAGE.tag_v2[key] for key in IMAGE.tag_v2}
        print(meta_dict)

    # Exchangeable Image File (EXIF)
    # Workaround from https://github.com/python-pillow/Pillow/issues/5863
    if hasattr(IMAGE, "_getexif"):
        exif = IMAGE._getexif()  # pylint: disable=protected-access
        if exif:
            msg += "\nEXIF:"
            for key, val in exif.items():
                if key in ExifTags.TAGS:
                    msg += f"\n{ExifTags.TAGS[key]}: {val}"
                else:
                    msg += f"\nUnknown EXIF tag {key}: {val}"

        # Image File Directory (IFD)
        exif = IMAGE.getexif()
        for k in ExifTags.IFD:
            try:
                msg += f"\nIFD tag {k}: {ExifTags.IFD(k)}: {exif.get_ifd(k)}"
            except KeyError:
                log.debug("IFD not found. %s", k)

    iptc = IptcImagePlugin.getiptcinfo(IMAGE)
    if iptc:
        msg += "\nIPTC:"
        for k, v in iptc.items():
            msg += "\nKey:{} Value:{}".format(k, repr(v))

    return msg


def info_toggle(event=None):
    """Toggle info overlay."""
    global SHOW_INFO
    SHOW_INFO = not SHOW_INFO
    if SHOW_INFO:
        INFO_OVERLAY.lift()
        log.debug("Showing info:\n%s", INFO_OVERLAY["text"])
    else:
        INFO_OVERLAY.lower()


@log_this
def mouse_handler(event=None):
    """Handle mouse events."""
    if event.num == 5 or event.delta < 0:
        root.event_generate("<Down>")
    if event.num == 4 or event.delta > 0:
        root.event_generate("<Up>")


SUPPORTED_FILES: list = []


def set_supported_files():
    """Set supported files. TODO: Distinguish between openable and saveable."""
    global SUPPORTED_FILES
    exts = Image.registered_extensions()
    exts[".eml"] = "EML"
    exts[".mht"] = "MHT"
    exts[".mhtml"] = "MHTML"
    exts[".zip"] = "ZIP"

    type_exts = {}
    for k, v in exts.items():
        type_exts.setdefault(v, []).append(k)

    SUPPORTED_FILES = [
        ("All supported files", " ".join(sorted(list(exts)))),
        ("All files", "*"),
        ("Archives", ".eml .mht .mhtml .zip"),
        *sorted(type_exts.items()),
    ]


set_supported_files()


@log_this
def path_open(event=None):
    """Pick a file to open."""
    filename = filedialog.askopenfilename(filetypes=SUPPORTED_FILES)
    if filename:
        paths_update(None, filename)


@log_this
def path_save(event=None):
    """Save file as."""
    if "Names" in INFO:
        p = pathlib.Path(str(paths[path_index]) + "." + INFO["Names"][ZIP_INDEX])
    else:
        p = paths[path_index]

    print("Image info to be saved:", IMAGE.info)
    filename = filedialog.asksaveasfilename(
        initialfile=p.absolute(), defaultextension=p.suffix, filetypes=SUPPORTED_FILES
    )
    if filename:
        log.info("Saving %s", filename)
        try:
            IMAGE.save(
                filename,
                # dpi=INFO.get("dpi", b""),
                # exif=INFO.get("exif", b""),
                # icc_profile=INFO.get("icc_profile", b""),
                **IMAGE.info,
                optimize=True,
                # save_all=True,
            )
            paths_update()
            toast(f"Saved {filename}")
        except (IOError, KeyError, TypeError, ValueError) as ex:
            msg = f"Failed to save as {filename}. {ex}"
            log.error(msg)
            toast(msg, fg="red")


@log_this
def paths_update(event=None, path=None):
    """Refresh path info."""
    global paths, path_index
    if not path:
        path = paths[path_index]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent

    log.debug("Reading %s...", p)
    paths = list(p.glob("*"))
    log.debug("Found %s files.", len(paths))

    log.debug("Filter?")
    log.debug("Sorting %s", SORT)

    for s in SORT.split(","):
        if s == "natural":
            paths.sort(
                key=lambda s: [
                    int(t) if t.isdigit() else t.lower()
                    for t in re.split(r"(\d+)", str(s))
                ]
            )
        elif s == "ctime":
            paths.sort(key=os.path.getmtime)
        elif s == "mtime":
            paths.sort(key=os.path.getmtime)
        elif s == "size":
            paths.sort(key=os.path.getsize)
        elif s == "string":
            paths.sort()

    try:
        path_index = paths.index(pathlib.Path(path))
    except ValueError as ex:
        log.error("paths_update %s", ex)

    image_load()


def update_loop():
    """Autoupdate paths."""
    if REFRESH_INTERVAL:
        paths_update()
        root.after(REFRESH_INTERVAL, update_loop)


def resize_handler(event):
    """Handle Tk resize event."""
    global WINDOW_SIZE
    new_size = root.winfo_geometry().split("+", maxsplit=1)[0]
    if WINDOW_SIZE != new_size:
        log.debug("%s", f"{WINDOW_SIZE} -> {new_size}")
        log.debug(INFO_OVERLAY.winfo_geometry())
        IMAGE_WIDGET.config(wraplength=event.width)
        INFO_OVERLAY.config(wraplength=event.width)
        STATUS_OVERLAY.config(wraplength=event.width)
        if WINDOW_SIZE and FIT:
            im_resize()
        WINDOW_SIZE = new_size


@log_this
def set_bg(event=None):
    """Set background color."""
    global BG_INDEX
    BG_INDEX += 1
    if BG_INDEX >= len(BG_COLORS):
        BG_INDEX = 0
    bg = BG_COLORS[BG_INDEX]
    root.config(background=bg)
    IMAGE_WIDGET.config(background=bg)


@log_this
def set_order(event=None):
    """Set order."""
    global SORT
    i = SORTS.index(SORT) if SORT in SORTS else "natural"
    i = (i + 1) % len(SORTS)
    SORT = SORTS[i]
    log.info("Sort %s", SORT)
    toast("Sort: " + SORT)
    paths_update()


@log_this
def set_verbosity(event=None):
    """Set verbosity."""
    global VERBOSITY
    VERBOSITY -= 10
    if VERBOSITY < 10:
        VERBOSITY = logging.CRITICAL

    logging.basicConfig(level=VERBOSITY)  # Show up in nested shells in Windows 11.
    log.setLevel(VERBOSITY)
    # print("Log level %s" % logging.getLevelName(VERBOSITY))


def slideshow_run(event=None):
    """Run slideshow."""
    if SLIDESHOW_ON:
        browse()
        root.after(SLIDESHOW_PAUSE, slideshow_run)


def slideshow_toggle(event=None):
    """Toggle slideshow."""
    global SLIDESHOW_ON
    SLIDESHOW_ON = not SLIDESHOW_ON
    if SLIDESHOW_ON:
        toast("Starting slideshow.")
        root.after(SLIDESHOW_PAUSE, slideshow_run)
    else:
        toast("Stopping slideshow.")


def toast(msg: str, ms: int = 2000, fg="#00FF00"):
    """Temporarily show a status message."""
    STATUS_OVERLAY.config(text=msg, fg=fg)
    STATUS_OVERLAY.lift()
    root.after(ms, STATUS_OVERLAY.lower)


@log_this
def transpose_inc(event=None):
    """Increment transpose."""
    global TRANSPOSE_INDEX
    TRANSPOSE_INDEX += 1
    if TRANSPOSE_INDEX >= len(Transpose):
        TRANSPOSE_INDEX = -1
    if TRANSPOSE_INDEX >= 0:
        toast(f"Transpose: {Transpose(TRANSPOSE_INDEX).name}")
    im_resize()


@log_this
def transpose_dec(event=None):
    """Decrement transpose."""
    global TRANSPOSE_INDEX
    TRANSPOSE_INDEX -= 1
    if TRANSPOSE_INDEX < -1:
        TRANSPOSE_INDEX = len(Transpose) - 1
    if TRANSPOSE_INDEX >= 0:
        toast(f"Transpose: {Transpose(TRANSPOSE_INDEX).name}")
    im_resize()


@log_this
def fit_handler(event):
    """Resize type to fit window."""
    global FIT
    FIT = (FIT + 1) % len(Fits)
    toast(Fits(FIT))
    im_resize()


@log_this
def fullscreen_toggle(event=None):
    """Toggle fullscreen."""
    if not root.overrideredirect():
        root.old_geometry = root.geometry()
        root.old_state = root.state()
        log.debug("Old widow geometry: %s", root.old_geometry)
        root.overrideredirect(True)
        root.state("zoomed")
    else:
        root.overrideredirect(False)
        root.state(root.old_state)
        if root.state() == "normal":
            new_geometry = (
                # Happens when window wasn't visible yet.
                "300x200+300+200"
                if root.old_geometry.startswith("1x1")
                else root.old_geometry
            )
            log.debug("Restoring geometry: %s", new_geometry)
            root.geometry(new_geometry)
    # Keeps using display 1
    # root.attributes("-fullscreen", not root.attributes("-fullscreen"))


@log_this
def zoom(event):
    """Zoom."""
    global SCALE
    k = event.keysym if event else "plus"
    if event.num == 5 or event.delta < 0:
        k = "plus"
    if event.num == 4 or event.delta > 0:
        k = "minus"
    if k == "plus":
        SCALE *= 1.1
    elif k == "minus":
        SCALE *= 0.9
    else:
        SCALE = 1
    SCALE = max(SCALE_MIN, min(SCALE, SCALE_MAX))
    im_resize()


@log_this
def zoom_text(event):
    """Zoom text of overlays."""
    global SCALE_TEXT
    k = event.keysym if event else "plus"
    if event.num == 5 or event.delta < 0:
        k = "plus"
    if event.num == 4 or event.delta > 0:
        k = "minus"
    if k == "plus":
        SCALE_TEXT *= 1.1
    elif k == "minus":
        SCALE_TEXT *= 0.9
    else:
        SCALE_TEXT = 1
    SCALE_TEXT = max(0.1, min(SCALE_TEXT, 20))
    new_font_size = int(FONT_SIZE * SCALE_TEXT)
    new_font_size = max(1, min(new_font_size, 200))

    log.info("Text scale: %s New font size: %s", SCALE_TEXT, new_font_size)

    IMAGE_WIDGET.config(font=("Consolas", new_font_size))
    INFO_OVERLAY.config(font=("Consolas", new_font_size))
    STATUS_OVERLAY.config(font=("Consolas", new_font_size * 2))


root = tkinter.Tk()
root.title(TITLE)
screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
geometry = f"{screen_w // 2}x{screen_h // 2}+100+100"
root.geometry(geometry)
SLIDESHOW_ON = False
SLIDESHOW_PAUSE = 4000
STATUS_OVERLAY = tkinter.Label(
    root,
    text="status",
    font=("Consolas", FONT_SIZE * 2),
    fg="#00FF00",
    bg="black",
    wraplength=screen_w,
    anchor="center",
    justify="center",
)
STATUS_OVERLAY.place(x=0, y=0)
INFO_OVERLAY = tkinter.Label(
    root,
    text="status",
    font=("Consolas", FONT_SIZE),
    fg="yellow",
    bg="black",
    wraplength=screen_w,
    anchor="nw",
    justify="left",
)
INFO_OVERLAY.place(x=0, y=0)
IMAGE_WIDGET = tkinter.Label(
    root,
    compound="center",
    fg="red",
    font=("Consolas", FONT_SIZE),
    width=screen_w,
    height=screen_h,
    wraplength=int(screen_w / 2),
)
IMAGE_WIDGET.place(x=0, y=0, relwidth=1, relheight=1)

set_bg()

root.bind_all("<Key>", debug_keys)

binds = [
    (close, "Escape q"),
    (help_handler, "F1 h"),
    (fullscreen_toggle, "F11 Return f"),
    (browse, "Left Right Up Down Key-1 x"),
    (mouse_handler, "MouseWheel Button-4 Button-5"),
    (path_open, "p"),
    (path_save, "s"),
    (delete_file, "Delete"),
    (paths_update, "F5 u"),
    (set_order, "o"),
    (set_bg, "b c"),
    (zoom, "Control-MouseWheel minus plus equal"),
    (zoom_text, "Alt-MouseWheel Alt-minus Alt-plus Alt-equal"),
    (fit_handler, "r"),
    (animation_toggle, "a"),
    (slideshow_toggle, "Pause"),
    (transpose_inc, "t"),
    (transpose_dec, "T"),
    (info_toggle, "i"),
    (set_verbosity, "v"),
    (resize_handler, "Configure"),
]


def main(args):
    """Main function."""
    global FIT, QUALITY, REFRESH_INTERVAL, SLIDESHOW_PAUSE, SORT, TRANSPOSE_INDEX, VERBOSITY

    if args.verbose:
        VERBOSITY = VERBOSITY_LEVELS[min(len(VERBOSITY_LEVELS) - 1, 1 + args.verbose)]
        set_verbosity()

    log.debug("Args: %s", args)

    FIT = args.resize or 0
    QUALITY = [
        Image.Resampling.NEAREST,
        Image.Resampling.BOX,
        Image.Resampling.BILINEAR,
        Image.Resampling.HAMMING,
        Image.Resampling.BICUBIC,
        Image.Resampling.LANCZOS,
    ][args.quality]
    TRANSPOSE_INDEX = args.transpose

    # Needs visible window so wait for mainloop.
    root.after(100, paths_update, None, args.path)

    if args.fullscreen:
        root.after(500, fullscreen_toggle)

    if args.geometry:
        root.geometry(args.geometry)

    if args.order:
        SORT = args.order

    if args.update:
        REFRESH_INTERVAL = args.update
        root.after(REFRESH_INTERVAL, update_loop)

    if args.slideshow:
        SLIDESHOW_PAUSE = args.slideshow
        slideshow_toggle()

    for b in binds:
        func = b[0]
        for event in b[1].split(" "):
            root.bind(f"<{event}>", func)
    root.mainloop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="tk_image_viewer",
        description="An image viewer that supports both arrow keys and "
        + "WebP with foreign characters in long paths.",
    )
    parser.add_argument("path", default=os.getcwd(), nargs="?")
    parser.add_argument(
        "--fullscreen",
        "-f",
        action="store_true",
        help="run fullscreen",
    )
    parser.add_argument(
        "--geometry",
        "-g",
        metavar="WxH+X+Y",
        help="set window geometry, eg -g +0+-999",
        type=str,
    )
    parser.add_argument(
        "--order",
        "-o",
        metavar="[natural (default)|string|random|mtime|ctime|size]",
        help="sort order",
        default="natural",
        type=str,
    )
    parser.add_argument(
        "--quality",
        "-q",
        metavar="N",
        help="set antialiasing level (0-5, default 0)",
        default=0,
        type=int,
    )
    parser.add_argument(
        "--resize",
        "-r",
        metavar="N",
        nargs="?",
        help="resize image to fit window (0-3: none, all, big, small. default 1)",
        const=1,
        type=lambda s: int(s) if 0 <= int(s) <= 3 else 0,
    )
    parser.add_argument(
        "--slideshow",
        "-s",
        metavar="ms",
        nargs="?",
        help="switch to next image every N ms (default 4000)",
        const=4000,
        type=int,
    )
    parser.add_argument(
        "--transpose",
        "-t",
        metavar="N",
        help=f"transpose 0-{len(Transpose)-1} {', '.join(x.name.lower() for x in Transpose)}",
        default=-1,
        type=int,
    )
    parser.add_argument(
        "--update",
        "-u",
        metavar="ms",
        nargs="?",
        help="update interval (default 4000)",
        const=4000,
        type=int,
    )
    parser.add_argument(
        "-v", "--verbose", help="set log level", action="count", default=0
    )

    main(parser.parse_args())
