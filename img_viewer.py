# pylint: disable=consider-using-f-string, global-statement, line-too-long, too-many-boolean-expressions, too-many-branches, unused-argument, use-maxsplit-arg
"""Tk Image Viewer
by Cees Timmerman, 2024-03-17."""

import functools
import logging
import os
import pathlib
import tkinter
from tkinter import messagebox

from PIL import (
    ExifTags,
    Image,
    ImageTk,
)
from PIL.Image import Transpose
from pillow_heif import register_heif_opener


# Add a handler to stream to sys.stderr warnings from all modules.
logging.basicConfig(format="%(levelname)s: %(message)s")
# Add a logging namespace.
log = logging.getLogger(__name__)

register_heif_opener()

BG_COLORS = ["black", "gray10", "gray50", "white"]
BG_INDEX = -1

FIT_TYPE = 0
FIT_ALL = 1
FIT_BIG = 2
FIT_SMALL = 4

PIL_IMAGE = None
QUALITY = Image.Resampling.NEAREST  # 0
REFRESH_INTERVAL = 0
SCALE = 1.0
SHOW_INFO = False
TITLE = __doc__.split("\n")[0]
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
paths: list[str] = []
path_index: int = 0


def log_this(func):
    """Decorator to log function calls."""

    @functools.wraps(func)
    def inner(*args, **kwargs):
        log.debug("Calling %s with %s, %s", func.__name__, args, kwargs)
        return func(*args, **kwargs)

    return inner


@log_this
def browse(event=None):
    """Selects next or previous file."""
    global path_index

    k = event.keysym if event else "Right"
    delta = -1 if k in ("Left", "Up") else 1

    path_index += delta
    if path_index < 0:
        path_index = len(paths) - 1
    if path_index >= len(paths):
        path_index = 0

    image_load()


@log_this
def close(event=None):
    """Closes fullscreen or app."""
    if root.overrideredirect():
        fullscreen_toggle()
    else:
        event.widget.withdraw()
        event.widget.quit()


def debug_keys(event=None):
    """Shows all keys."""


def delete_file(event=None):
    """Delete file."""
    path = paths[path_index]
    msg = f"Delete? {path}"
    log.warning(msg)
    answer = messagebox.askyesno("Delete file?", f"Delete {path}?")
    if answer is True:
        log.warning("Deleting %s", path)
        paths_update()


def image_load(path=None):
    """Loads image."""
    global PIL_IMAGE

    if not path:
        path = paths[path_index]

    msg = f"{path_index+1}/{len(paths)} "
    log.debug("Loading %s%s", msg, path)

    err_msg = ""
    try:
        PIL_IMAGE = Image.open(path)
        log.debug("Cached %s PIL_IMAGE", PIL_IMAGE.size)
        image_resize()
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
        PIL_IMAGE = None
        msg = f"{msg} {err_msg} {path}"
        IMAGE_WIDGET.config(image="", text=msg)
        IMAGE_WIDGET.im = None
        INFO_OVERLAY.config(text=msg)
        root.title(msg + " - " + TITLE)


def image_resize():
    """Resizes image."""
    global PIL_IMAGE
    if not PIL_IMAGE:
        return

    pim = PIL_IMAGE.copy()

    log.debug("Got cached %s", PIL_IMAGE.size)
    im_w, im_h = PIL_IMAGE.size

    if FIT_TYPE:
        w = root.winfo_width()
        h = root.winfo_height()

        log.debug("Fitting to window %s %sx%s", IMAGE_WIDGET.winfo_geometry(), w, h)
        im_w, im_h = PIL_IMAGE.size
        if im_w != w or im_h != h:
            if (
                FIT_TYPE & FIT_ALL
                or (FIT_TYPE & FIT_BIG and (im_w > w or im_h > h))
                or (FIT_TYPE & FIT_SMALL and (im_w < w or im_h < h))
            ):
                ratio = min(w / im_w, h / im_h)
                log.debug("Ratio: %s", ratio)
                pim = PIL_IMAGE.resize((int(im_w * ratio), int(im_h * ratio)), QUALITY)

    if SCALE != 1:
        log.debug("Scaling to %s", SCALE)
        try:
            pim = PIL_IMAGE.resize(
                (int(SCALE * im_w), int(SCALE * im_h)),
                QUALITY,
            )
        except ValueError as ex:
            log.error("Failed to scale. %s", ex)

    if TRANSPOSE_INDEX != -1:
        log.debug("Transposing %s", Transpose(TRANSPOSE_INDEX))
        pim = pim.transpose(TRANSPOSE_INDEX)

    try:
        im = ImageTk.PhotoImage(pim)
        IMAGE_WIDGET.config(image=im, text="")  # Set it.
        IMAGE_WIDGET.im = im  # Keep it. Why isn't this built in?!
        msg = f"{path_index+1}/{len(paths)} {im_w}x{im_h} @ {'%sx%s' % pim.size} {paths[path_index]}"
        root.title(msg + " - " + TITLE)

        if SHOW_INFO:
            exif = PIL_IMAGE.getexif()
            if exif:
                msg += " EXIF:\n"
                for key, val in exif.items():
                    if key in ExifTags.TAGS:
                        msg += f"{ExifTags.TAGS[key]}: {val}\n"
                    else:
                        msg += f"Unknown EXIF tag {key}: {val}\n"

                for k in ExifTags.IFD:
                    try:
                        msg += f"IFD tag {ExifTags.GPS[k]}: {exif.get_ifd(k)}\n"
                    except KeyError:
                        pass

        INFO_OVERLAY.configure(text=msg)

    except MemoryError as ex:
        log.error("Out of memory. Scaling down. %s", ex)
        root.event_generate("<minus>")


def info_toggle(event=None):
    """Toggles info overlay."""
    global SHOW_INFO
    SHOW_INFO = not SHOW_INFO
    if SHOW_INFO:
        INFO_OVERLAY.lift()
    else:
        INFO_OVERLAY.lower()


@log_this
def mouse_wheel(event=None):
    """Handles mouse events."""
    if event.num == 5 or event.delta == -120:
        root.event_generate("<Down>")
    if event.num == 4 or event.delta == 120:
        root.event_generate("<Up>")


@log_this
def paths_update(event=None, path=None):
    """Refreshes path info."""
    global paths, path_index
    if not path:
        path = paths[path_index]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent

    log.debug("Reading %s...", p)
    paths = list(p.glob("*"))
    log.debug("Found %s files.", len(paths))

    try:
        path_index = paths.index(pathlib.Path(path))
    except ValueError as ex:
        log.error("paths_update %s", ex)

    image_load()


def update_loop():
    """Autoupdates paths."""
    if REFRESH_INTERVAL:
        paths_update()
        root.after(REFRESH_INTERVAL, update_loop)


@log_this
def resize_handler(event):
    """Handles Tk resize event."""
    global WINDOW_SIZE
    new_size = root.winfo_geometry().split("+", maxsplit=1)[0]
    if WINDOW_SIZE != new_size:
        log.debug("%s", f"{WINDOW_SIZE} -> {new_size}")
        log.debug(INFO_OVERLAY.winfo_geometry())
        IMAGE_WIDGET.config(wraplength=event.width)
        INFO_OVERLAY.config(wraplength=event.width)
        STATUS_OVERLAY.config(wraplength=event.width)
        if WINDOW_SIZE and FIT_TYPE:
            image_resize()
        WINDOW_SIZE = new_size


@log_this
def set_bg(event=None):
    """Sets background color."""
    global BG_INDEX
    BG_INDEX += 1
    if BG_INDEX >= len(BG_COLORS):
        BG_INDEX = 0
    bg = BG_COLORS[BG_INDEX]
    root.config(background=bg)
    IMAGE_WIDGET.config(background=bg)


@log_this
def set_verbosity(event=None):
    """Sets verbosity."""
    global VERBOSITY
    VERBOSITY -= 10
    if VERBOSITY < 10:
        VERBOSITY = logging.CRITICAL

    log.setLevel(VERBOSITY)
    print("Log level %s" % logging.getLevelName(VERBOSITY))


def slideshow_run(event=None):
    """Runs slideshow."""
    if SLIDESHOW_ON:
        browse()
        root.after(SLIDESHOW_PAUSE, slideshow_run)


def slideshow_toggle(event=None):
    """Toggles slideshow."""
    global SLIDESHOW_ON
    SLIDESHOW_ON = not SLIDESHOW_ON
    if SLIDESHOW_ON:
        toast("Starting slideshow.")
        root.after(SLIDESHOW_PAUSE, slideshow_run)
    else:
        toast("Stopping slideshow.")


def toast(msg: str, ms: int = 1000):
    """Temporarily shows a status message."""
    STATUS_OVERLAY.config(text=msg)
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
    image_resize()


@log_this
def transpose_dec(event=None):
    """Decrement transpose."""
    global TRANSPOSE_INDEX
    TRANSPOSE_INDEX -= 1
    if TRANSPOSE_INDEX < -1:
        TRANSPOSE_INDEX = len(Transpose) - 1
    if TRANSPOSE_INDEX >= 0:
        toast(f"Transpose: {Transpose(TRANSPOSE_INDEX).name}")
    image_resize()


@log_this
def fullscreen_toggle(event=None):
    """Toggles fullscreen."""
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
def zoom(event=None):
    """Zooms."""
    global SCALE
    k = event.keysym if event else "plus"
    if event.num == 5 or event.delta == -120:
        k = "plus"
    if event.num == 4 or event.delta == 120:
        k = "minus"
    if k == "plus":
        SCALE *= 1.1
    elif k == "minus":
        SCALE *= 0.9
    else:
        SCALE = 1
    SCALE = max(SCALE, 0.01)
    SCALE = min(SCALE, 40.0)
    image_resize()


root = tkinter.Tk()
root.title(TITLE)
screen_w, screen_h = root.winfo_screenwidth(), root.winfo_screenheight()
geometry = f"{int(screen_w / 2)}x{int(screen_h / 2)}+100+100"
root.geometry(geometry)
SLIDESHOW_ON = False
SLIDESHOW_PAUSE = 4000
STATUS_OVERLAY = tkinter.Label(
    root,
    text="status",
    font=("Consolas", 24),
    fg="yellow",
    bg="black",
    wraplength=screen_w,
    anchor="center",
    justify="center",
)
STATUS_OVERLAY.place(x=0, y=0)
INFO_OVERLAY = tkinter.Label(
    root,
    text="status",
    font=("Consolas", 14),
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
    width=screen_w,
    height=screen_h,
    wraplength=int(screen_w / 2),
)
IMAGE_WIDGET.place(x=0, y=0, relwidth=1, relheight=1)

set_bg()

root.bind_all("<Key>", debug_keys)

binds = [
    ("<Escape>", close),
    ("<f>", fullscreen_toggle),
    ("<F11>", fullscreen_toggle),
    ("<Return>", fullscreen_toggle),
    ("<Left>", browse),
    ("<Right>", browse),
    ("<Up>", browse),
    ("<Down>", browse),
    ("<MouseWheel>", mouse_wheel),
    ("<Button-4>", mouse_wheel),
    ("<Button-5>", mouse_wheel),
    ("<u>", paths_update),
    ("<F5>", paths_update),
    ("<c>", set_bg),
    ("<Control-MouseWheel>", zoom),
    ("<minus>", zoom),
    ("<plus>", zoom),
    ("<equal>", zoom),
    ("<s>", slideshow_toggle),
    ("<Pause>", slideshow_toggle),
    ("<t>", transpose_inc),
    ("<T>", transpose_dec),
    ("<v>", set_verbosity),
    ("<i>", info_toggle),
    ("<Configure>", resize_handler),
    ("<Delete>", delete_file),
]
for b in binds:
    root.bind(b[0], b[1])


def main(args):
    """Main function."""
    global FIT_TYPE, QUALITY, REFRESH_INTERVAL, SLIDESHOW_PAUSE, TRANSPOSE_INDEX, VERBOSITY

    if args.verbose:
        VERBOSITY = VERBOSITY_LEVELS[1 + args.verbose]
        set_verbosity()

    log.debug("Args: %s", args)
    log.debug("Binds %s", "\n".join(f"{k}: {f.__name__}" for k, f in binds))

    FIT_TYPE = args.resize
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

    if args.update:
        REFRESH_INTERVAL = args.update
        root.after(REFRESH_INTERVAL, update_loop)

    if args.slideshow:
        SLIDESHOW_PAUSE = args.slideshow
        slideshow_toggle()

    root.mainloop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="An image viewer that supports both arrow keys and "
        + "WebP with foreign characters in long paths."
    )
    parser.add_argument("path", default=os.getcwd(), nargs="?")
    parser.add_argument(
        "--fullscreen",
        "-f",
        metavar="N",
        nargs="?",
        help="run in fullscreen on display N (1-?, default 1)",
        const=1,
        type=int,
    )
    parser.add_argument(
        "--resize",
        "-r",
        metavar="N",
        nargs="?",
        help="resize image to fit window (0-3: none, all, big, small. default 0)",
        const=1,
        type=int,
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
        "--update",
        "-u",
        metavar="ms",
        nargs="?",
        help="update interval (default 4000)",
        const=4000,
        type=int,
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
        "-v", "--verbose", help="set log level", action="count", default=0
    )

    main(parser.parse_args())
