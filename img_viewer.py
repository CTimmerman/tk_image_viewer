# pylint: disable=unused-argument, global-statement, use-maxsplit-arg, using-constant-test
"""Tk Image Viewer
by Cees Timmerman, 2024-03-17."""

import logging
import os
import pathlib
import tkinter

from PIL import Image, ImageTk, UnidentifiedImageError  # pip install pillow
from PIL.Image import Transpose

ANTIALIAS_LEVEL = Image.Resampling.NEAREST  # 0
BG_COLORS = ["black", "gray10", "gray50", "white"]
BG_INDEX = -1
FIT_WINDOW = 0
SCALE = 1.0
SLIDESHOW_PAUSE = 4000
SLIDESHOW_ON = False
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

    show_image()


@log_this
def debug_keys(event=None):
    """Shows all keys."""


def delete_file(event=None):
    """Delete file."""
    msg = f"Delete? {paths[path_index]}"
    logging.warning(msg)
    IMAGE_LABEL.config(text=msg, bg="black", fg="red")


@log_this
def mouse_wheel(event=None):
    """Handles mouse events."""
    if event.num == 5 or event.delta == -120:
        root.event_generate("<Down>")
    if event.num == 4 or event.delta == 120:
        root.event_generate("<Up>")


@log_this
def close(event=None):
    """Closes app."""
    event.widget.withdraw()
    event.widget.quit()


def refresh_paths(event=None, path=None):
    """Refreshes path info."""
    global paths, path_index
    if not path:
        path = paths[path_index]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent
        path_index = -1

    logging.debug("Reading %s...", p)
    paths = list(p.glob("*"))
    logging.debug("Found %s files.", len(paths))

    if path_index < 0:
        logging.debug("\n".join(str(p) for p in paths))
        try:
            path_index = paths.index(pathlib.Path(path))
        except ValueError as ex:
            logging.error("refresh_paths %s", ex)
            # path_index = 0

    show_image()


def run_slideshow(event=None):
    """Runs slideshow."""
    if SLIDESHOW_ON:
        browse()
        root.after(SLIDESHOW_PAUSE, run_slideshow)


@log_this
def set_bg(event=None):
    """Sets background color."""
    global BG_INDEX
    BG_INDEX += 1
    if BG_INDEX >= len(BG_COLORS):
        BG_INDEX = 0
    bg = BG_COLORS[BG_INDEX]
    root.config(background=bg)
    IMAGE_LABEL.config(background=bg)


@log_this
def inc_transpose(event=None):
    """Increment transpose."""
    global TRANSPOSE_INDEX
    TRANSPOSE_INDEX += 1
    if TRANSPOSE_INDEX >= len(Transpose):
        TRANSPOSE_INDEX = -1
    show_image()


@log_this
def dec_transpose(event=None):
    """Decrement transpose."""
    global TRANSPOSE_INDEX
    TRANSPOSE_INDEX -= 1
    if TRANSPOSE_INDEX < -1:
        TRANSPOSE_INDEX = len(Transpose) - 1
    show_image()


@log_this
def set_verbosity(event=None):
    """Increment transpose."""
    global VERBOSITY
    VERBOSITY -= 10
    if VERBOSITY < 10:
        VERBOSITY = logging.CRITICAL

    logging.basicConfig(level=VERBOSITY)
    logging.getLogger().setLevel(VERBOSITY)
    print("\nSet verbosity to", VERBOSITY)
    logging.debug("debug")
    logging.info("info")
    logging.warning("warning")
    logging.error("error")
    logging.critical("critical")


def show_image(path=None):
    """Shows image."""
    if not path:
        path = paths[path_index]

    msg = f"{path_index+1}/{len(paths)} "
    logging.debug("Showing %s%s", msg, path)

    err_msg = ""
    try:
        pil_img = Image.open(path)
    except (
        UnidentifiedImageError,
        PermissionError,
        tkinter.TclError,
        IOError,
        MemoryError,
        EOFError,
        ValueError,
        BufferError,
    ) as ex:
        err_msg = str(ex)
        logging.error(err_msg)
        pil_img = None

    if pil_img:
        im_w, im_h = pil_img.size

        if FIT_WINDOW:
            logging.debug(IMAGE_LABEL.winfo_geometry())
            im_w, im_h = pil_img.size
            if im_w > w or im_h > h:
                ratio = min(w / im_w, h / im_h)
                im_w = int(im_w * ratio)
                im_h = int(im_h * ratio)
                pil_img = pil_img.resize((im_w, im_h), ANTIALIAS_LEVEL)

        if SCALE != 1:
            logging.debug("Scaling to %s", SCALE)
            pil_img = pil_img.resize(
                (int(SCALE * im_w), int(SCALE * im_h)),
                ANTIALIAS_LEVEL,
            )

        if TRANSPOSE_INDEX != -1:
            logging.debug("Transposing %s", Transpose(TRANSPOSE_INDEX))
            pil_img = pil_img.transpose(TRANSPOSE_INDEX)

    msg = msg + (f"{im_w}x{im_h} x{SCALE:.2f}" if pil_img else err_msg) + f" {path}"
    root.title(msg + " - " + TITLE)
    STATUS_LABEL.configure(text=msg)

    if pil_img:
        img = ImageTk.PhotoImage(pil_img)
        IMAGE_LABEL.config(image=img, text="" if img else msg)  # Set it.
        IMAGE_LABEL.img = img  # Keep it. Why isn't this built in?!
    else:
        IMAGE_LABEL.config(text=msg, fg="red")


@log_this
def toggle_fullscreen(event=None):
    """Toggles fullscreen."""
    root.attributes("-fullscreen", not root.attributes("-fullscreen"))


def toggle_slideshow(event=None):
    """Toggles slideshow."""
    global SLIDESHOW_ON
    SLIDESHOW_ON = not SLIDESHOW_ON
    if SLIDESHOW_ON:
        logging.info("Starting slideshow.")
        run_slideshow()
    else:
        logging.info("Stopping slideshow.")


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
    show_image()


root = tkinter.Tk()
root.title(TITLE)
w, h = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{int(w / 2)}x{int(h / 2)}")

IMAGE_LABEL = tkinter.Label(root, width=w, height=h, fg="red", wraplength=int(w / 2))
IMAGE_LABEL.place(x=0, y=0, relwidth=1, relheight=1)
IMAGE_LABEL.pack()

STATUS_LABEL = tkinter.Label(
    root,
    text="status",
    font=("Consolas", 14),
    fg="green3",
    bg="grey19",
    wraplength=w,
    anchor="nw",
    justify="left",
)
STATUS_LABEL.pack()

set_bg()


root.bind_all("<Key>", debug_keys)
root.bind("<Escape>", close)

root.bind("<Return>", toggle_fullscreen)
root.bind("<F11>", toggle_fullscreen)

root.bind("<Left>", browse)
root.bind("<Right>", browse)
root.bind("<Up>", browse)
root.bind("<Down>", browse)
root.bind("<MouseWheel>", mouse_wheel)
root.bind("<Button-4>", mouse_wheel)
root.bind("<Button-5>", mouse_wheel)

root.bind("<r>", refresh_paths)
root.bind("<F5>", refresh_paths)

root.bind("<c>", set_bg)

root.bind("<Control-MouseWheel>", zoom)
root.bind("<minus>", zoom)
root.bind("<plus>", zoom)
root.bind("<equal>", zoom)

root.bind("<s>", toggle_slideshow)
root.bind("<Pause>", toggle_slideshow)

root.bind("<t>", inc_transpose)
root.bind("<T>", dec_transpose)

root.bind("<v>", set_verbosity)

root.bind("<Delete>", delete_file)  # TODO


def main(args):
    """Main function."""
    global ANTIALIAS_LEVEL, SLIDESHOW_PAUSE, TRANSPOSE_INDEX, VERBOSITY
    if args.verbose:
        VERBOSITY = VERBOSITY_LEVELS[2 + args.verbose]
        print("Setting verbosity", VERBOSITY)
        logging.basicConfig(level=VERBOSITY)

    logging.debug(args)

    ANTIALIAS_LEVEL = [
        Image.Resampling.NEAREST,
        Image.Resampling.BOX,
        Image.Resampling.BILINEAR,
        Image.Resampling.HAMMING,
        Image.Resampling.BICUBIC,
        Image.Resampling.LANCZOS,
    ][args.quality]

    TRANSPOSE_INDEX = args.transpose

    refresh_paths(path=args.path)

    if args.slideshow:
        SLIDESHOW_PAUSE = args.slideshow
        toggle_slideshow()

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
        "--fit",
        help="fit window (0-1, default 0)",
        default=0,
        type=int,
    )
    parser.add_argument(
        "-q",
        "--quality",
        help="set antialiasing level (0-5, default 0)",
        default=0,
        type=int,
    )
    parser.add_argument(
        "-s",
        "--slideshow",
        metavar="N",
        type=int,
        nargs="?",
        const=4000,
        help="switch to next image every N ms (default 4000)",
    )
    parser.add_argument(
        "-t",
        "--transpose",
        metavar="T",
        type=int,
        default=-1,
        help=f"transpose 0-{len(Transpose)-1} {', '.join(x.name for x in Transpose)}",
    )
    parser.add_argument(
        "-v", "--verbose", help="set log level", action="count", default=0
    )
    main(parser.parse_args())
