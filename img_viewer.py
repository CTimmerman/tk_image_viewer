# pylint: disable=unused-argument, global-statement, too-many-branches, use-maxsplit-arg
"""Tk Image Viewer
by Cees Timmerman, 2024-03-17."""

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

register_heif_opener()

QUALITY = Image.Resampling.NEAREST  # 0
BG_COLORS = ["black", "gray10", "gray50", "white"]
BG_INDEX = -1
FIT_WINDOW = 0
FULLSCREEN = 1
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
paths: list[str] = []
path_index: int = 0


def log_this(func):
    """Decorator to log function calls."""

    def inner(*args, **kwargs):
        logging.debug("Calling %s with %s, %s", func.__name__, args, kwargs)
        func(*args, **kwargs)

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


@log_this
def debug_keys(event=None):
    """Shows all keys."""


def delete_file(event=None):
    """Delete file."""
    path = paths[path_index]
    msg = f"Delete? {path}"
    logging.warning(msg)
    answer = messagebox.askyesno("Delete file?", f"Delete {path}?")
    if answer is True:
        logging.warning("Deleting %s", path)
        paths_refresh()


def image_load(path=None):
    """Loads image."""
    if not path:
        path = paths[path_index]

    msg = f"{path_index+1}/{len(paths)} "
    logging.debug("Loading %s%s", msg, path)

    err_msg = ""
    try:
        root.pil_im = Image.open(path)
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
        logging.error(err_msg)
        root.pil_im = None
        msg = f"{msg} {err_msg} {path}"
        IMAGE_WIDGET.config(image="", text=msg)
        IMAGE_WIDGET.img = None
        root.title(msg + " - " + TITLE)


def image_resize():
    """Resizes image."""
    pil_im = root.pil_im
    if not pil_im:
        return

    im_w, im_h = pil_im.size

    if FIT_WINDOW:
        w = root.winfo_width()
        h = root.winfo_height()

        logging.debug("Fitting to window %s %sx%s", IMAGE_WIDGET.winfo_geometry(), w, h)
        im_w, im_h = pil_im.size
        if im_w > w or im_h > h:
            ratio = min(w / im_w, h / im_h)
            im_w = int(im_w * ratio)
            im_h = int(im_h * ratio)
            pil_im = pil_im.resize((im_w, im_h), QUALITY)

    if SCALE != 1:
        logging.debug("Scaling to %s", SCALE)
        try:
            pil_im = pil_im.resize(
                (int(SCALE * im_w), int(SCALE * im_h)),
                QUALITY,
            )
        except ValueError as ex:
            logging.error("Failed to scale. %s", ex)

    if TRANSPOSE_INDEX != -1:
        logging.debug("Transposing %s", Transpose(TRANSPOSE_INDEX))
        pil_im = pil_im.transpose(TRANSPOSE_INDEX)

    try:
        img = ImageTk.PhotoImage(pil_im)
        IMAGE_WIDGET.config(image=img, text="")  # Set it.
        IMAGE_WIDGET.img = img  # Keep it. Why isn't this built in?!

        msg = f"{path_index+1}/{len(paths)} {im_w}x{im_h} x{SCALE:.2f} {paths[path_index]}"
        root.title(msg + " - " + TITLE)

        if SHOW_INFO:
            exif = pil_im.getexif()
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

            INFO_OVERLAY.configure(text=msg, fg="green")

    except MemoryError as ex:
        logging.error("Out of memory. Scaling down. %s", ex)
        root.event_generate("<minus>")


def info_toggle(event=None):
    """Toggles info overlay."""
    global SHOW_INFO
    SHOW_INFO = not SHOW_INFO
    if SHOW_INFO:
        INFO_OVERLAY.lift()
    else:
        INFO_OVERLAY.lower()

    image_resize()


@log_this
def mouse_wheel(event=None):
    """Handles mouse events."""
    if event.num == 5 or event.delta == -120:
        root.event_generate("<Down>")
    if event.num == 4 or event.delta == 120:
        root.event_generate("<Up>")


@log_this
def paths_refresh(event=None, path=None):
    """Refreshes path info."""
    global paths, path_index
    if not path:
        path = paths[path_index]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent

    logging.debug("Reading %s...", p)
    paths = list(p.glob("*"))
    logging.debug("Found %s files.", len(paths))

    try:
        path_index = paths.index(pathlib.Path(path))
    except ValueError as ex:
        logging.error("paths_refresh %s", ex)

    image_load()


def refresh_loop():
    """Autorefreshes paths."""
    if REFRESH_INTERVAL:
        paths_refresh()
        root.after(REFRESH_INTERVAL, refresh_loop)


def resize(w, h):
    """Resize the Tk image widget."""
    INFO_OVERLAY.config(width=w, wraplength=w)
    IMAGE_WIDGET.config(width=w, height=h)


@log_this
def resize_handler(event):
    """Handles Tk resize event."""
    resize(event.width, event.height)


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

    logging.basicConfig(level=VERBOSITY)
    logging.getLogger().setLevel(VERBOSITY)
    s = "verbosity set"
    logging.debug(s)
    logging.info(s)
    logging.warning(s)
    logging.error(s)
    logging.critical("%s\n", s)


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
        logging.info("Starting slideshow.")
        root.after(SLIDESHOW_PAUSE, slideshow_run)
    else:
        logging.info("Stopping slideshow.")


def status_timeout(msg: str, ms: int = 1000):
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
        status_timeout(f"Transpose: {Transpose(TRANSPOSE_INDEX).name}")
    image_resize()


@log_this
def transpose_dec(event=None):
    """Decrement transpose."""
    global TRANSPOSE_INDEX
    TRANSPOSE_INDEX -= 1
    if TRANSPOSE_INDEX < -1:
        TRANSPOSE_INDEX = len(Transpose) - 1
    if TRANSPOSE_INDEX >= 0:
        status_timeout(f"Transpose: {Transpose(TRANSPOSE_INDEX).name}")
    image_resize()


@log_this
def fullscreen_toggle(event=None):
    """Toggles fullscreen."""
    if not root.overrideredirect():
        root.old_geometry = root.geometry()
        root.old_state = root.state()
        logging.debug("Old widow geometry: %s", root.old_geometry)
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
            logging.debug("Restoring geometry: %s", new_geometry)
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
    fg="green",
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

root.bind("<Escape>", close)

root.bind("<f>", fullscreen_toggle)
root.bind("<F11>", fullscreen_toggle)
root.bind("<Return>", fullscreen_toggle)

root.bind("<Left>", browse)
root.bind("<Right>", browse)
root.bind("<Up>", browse)
root.bind("<Down>", browse)
root.bind("<MouseWheel>", mouse_wheel)
root.bind("<Button-4>", mouse_wheel)
root.bind("<Button-5>", mouse_wheel)

root.bind("<r>", paths_refresh)
root.bind("<F5>", paths_refresh)

root.bind("<c>", set_bg)

root.bind("<Control-MouseWheel>", zoom)
root.bind("<minus>", zoom)
root.bind("<plus>", zoom)
root.bind("<equal>", zoom)

root.bind("<s>", slideshow_toggle)
root.bind("<Pause>", slideshow_toggle)

root.bind("<t>", transpose_inc)
root.bind("<T>", transpose_dec)

root.bind("<v>", set_verbosity)

root.bind("<i>", info_toggle)

root.bind("<Configure>", resize_handler)

root.bind("<Delete>", delete_file)


def main(args):
    """Main function."""
    global FULLSCREEN, QUALITY, REFRESH_INTERVAL, SLIDESHOW_PAUSE, TRANSPOSE_INDEX, VERBOSITY

    if args.verbose:
        VERBOSITY = VERBOSITY_LEVELS[1 + args.verbose]
        set_verbosity()

    logging.debug("Args: %s", args)

    FULLSCREEN = args.fullscreen
    if FULLSCREEN:
        # Needs visible window so wait for mainloop.
        root.after(500, fullscreen_toggle)

    QUALITY = [
        Image.Resampling.NEAREST,
        Image.Resampling.BOX,
        Image.Resampling.BILINEAR,
        Image.Resampling.HAMMING,
        Image.Resampling.BICUBIC,
        Image.Resampling.LANCZOS,
    ][args.quality]

    TRANSPOSE_INDEX = args.transpose

    paths_refresh(path=args.path)
    if args.refresh:
        REFRESH_INTERVAL = args.refresh
        root.after(REFRESH_INTERVAL, refresh_loop)

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
        "-f",
        "--fullscreen",
        metavar="N",
        nargs="?",
        help="run in fullscreen on display N (1-?, default 1)",
        const=1,
        type=int,
    )
    parser.add_argument(
        "-p",
        "--pinch",
        metavar="N",
        nargs="?",
        help="pinch to fit window (0-1, default 0)",
        default=0,
        type=int,
    )
    parser.add_argument(
        "-q",
        "--quality",
        metavar="N",
        help="set antialiasing level (0-5, default 0)",
        default=0,
        type=int,
    )
    parser.add_argument(
        "-r",
        "--refresh",
        metavar="ms",
        nargs="?",
        help="refresh interval (default 4000)",
        const=4000,
        type=int,
    )
    parser.add_argument(
        "-s",
        "--slideshow",
        metavar="ms",
        nargs="?",
        help="switch to next image every N ms (default 4000)",
        const=4000,
        type=int,
    )
    parser.add_argument(
        "-t",
        "--transpose",
        metavar="N",
        help=f"transpose 0-{len(Transpose)-1} {', '.join(x.name for x in Transpose)}",
        default=-1,
        type=int,
    )
    parser.add_argument(
        "-v", "--verbose", help="set log level", action="count", default=0
    )
    main(parser.parse_args())
