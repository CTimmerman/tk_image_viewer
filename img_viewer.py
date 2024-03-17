# pylint: disable=unused-argument, global-statement, use-maxsplit-arg, using-constant-test
"""Tk Image Viewer
by Cees Timmerman 2024-03-17."""

import logging
import pathlib
import tkinter

from PIL import Image, ImageTk  # pip install pillow


ANTIALIAS_ON = False
BG_COLORS = ["black", "gray10", "gray50", "white"]
BG_INDEX = -1
RESIZE = True
SCALE = 1.0
SLIDESHOW_PAUSE = 4000
SLIDESHOW_ON = False
TITLE = __doc__.split("\n")[0]
paths: list[str] = []
path_index: int = -1


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

    msg = f"Index {path_index + 1}/{len(paths) + 1}"
    STATUS_LABEL.config(text=msg)
    path = paths[path_index]
    show_image(path)


def debug_keys(event=None):
    """Shows all keys."""
    logging.info("KEY: %s", event)


def mouse_wheel(event=None):
    """Handles mouse events."""
    logging.info("MOUSE: %s", event)
    if event.num == 5 or event.delta == -120:
        root.event_generate("<Down>")
    if event.num == 4 or event.delta == 120:
        root.event_generate("<Up>")


def close(event=None):
    """Closes app."""
    event.widget.withdraw()
    event.widget.quit()


def refresh_paths(event=None, path="."):
    """Refreshes path info."""
    global paths
    logging.debug("Reading %s...", path)
    paths = list(pathlib.Path(path).glob("*"))
    logging.debug("Found %s files.", len(paths))


def run_slideshow(event=None):
    """Runs slideshow."""
    if SLIDESHOW_ON:
        browse()
        root.after(SLIDESHOW_PAUSE, run_slideshow)


def set_bg(event=None):
    """Sets background color."""
    global BG_INDEX
    BG_INDEX += 1
    if BG_INDEX >= len(BG_COLORS):
        BG_INDEX = 0
    bg = BG_COLORS[BG_INDEX]
    root.config(background=bg)
    IMAGE_LABEL.config(background=bg)


def show_image(path):
    """Shows image."""
    logging.debug("Showing %s", path)
    msg = ""
    try:
        pil_img = Image.open(path)
    except PermissionError as ex:
        msg = str(ex)
        logging.error(msg)
        pil_img = None

    if pil_img:
        im_w, im_h = pil_img.size
        if SCALE != 1:
            pil_img = pil_img.RESIZE(
                (int(SCALE * im_w), int(SCALE * im_h)),
                Image.BICUBIC if ANTIALIAS_ON else None,
            )

        if False:
            logging.debug(IMAGE_LABEL.winfo_geometry())
            im_w, im_h = pil_img.size
            if im_w > w or im_h > h:
                ratio = min(w / im_w, h / im_h)
                im_w = int(im_w * ratio)
                im_h = int(im_h * ratio)
                pil_img = pil_img.RESIZE(
                    (im_w, im_h), Image.BICUBIC if ANTIALIAS_ON else None
                )

    msg = (
        f"{path_index+1}/{len(paths)} "
        + (f"{im_w}x{im_h} x{SCALE:.1f}" if pil_img else msg)
        + f" {path} - {TITLE}"
    )
    root.title(msg)
    STATUS_LABEL.configure(text=msg)

    img = ImageTk.PhotoImage(pil_img) if pil_img else None
    IMAGE_LABEL.config(image=img, text="" if img else msg)  # Set it.
    IMAGE_LABEL.img = img  # Keep it. Why isn't this built in?!


def toggle_fullscreen(event=None):
    """Toggles fullscreen."""
    logging.debug("Toggling fullscreen")
    root.attributes("-fullscreen", not root.attributes("-fullscreen"))


def toggle_slideshow(event=None, **kwargs):
    """Toggles slideshow."""
    print("KWARGS", kwargs)
    global SLIDESHOW_ON
    SLIDESHOW_ON = not SLIDESHOW_ON
    if SLIDESHOW_ON:
        logging.info("Starting slideshow.")
        run_slideshow()
    else:
        logging.info("Stopping slideshow.")


def zoom(event=None):
    """Zooms."""
    global SCALE  # noqa
    logging.debug("ZOOM: %s", event)
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
    SCALE = max(SCALE, 0.1)
    SCALE = min(SCALE, 8)
    show_image(paths[path_index])


root = tkinter.Tk()
root.title(TITLE)
w, h = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry(f"{int(w / 2)}x{int(h / 2)}")

IMAGE_LABEL = tkinter.Label(root, width=w, height=h, fg="red")
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


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="An image viewer that supports both arrow keys and "
        + "WebP with foreign characters in long paths."
    )
    parser.add_argument("path", default=".", nargs="?")
    parser.add_argument(
        "-s",
        "--slideshow",
        metavar="N",
        type=int,
        nargs="?",
        const=4000,
        help="switches to next image every N ms (default 4000)",
    )
    parser.add_argument(
        "-v", "--verbose", help="sets log level", action="count", default=0
    )
    args = parser.parse_args()
    print(args)

    if args.verbose:
        level = [logging.ERROR, logging.WARN, logging.INFO, logging.DEBUG][args.verbose]
        logging.basicConfig(level=level)

    refresh_paths(path=args.path)
    browse()

    if args.slideshow:
        SLIDESHOW_PAUSE = args.slideshow
        toggle_slideshow()

    root.mainloop()
