"""Tk Image Viewer
by Cees Timmerman 2024-03-17."""

import logging, pathlib, tkinter

from PIL import Image, ImageTk  # pip install pillow


# logging.basicConfig(level=logging.INFO)


antialias_on = False
bg_colors = ["black", "gray10", "gray50", "white"]
bg_index = -1
resize = True
scale = 1.0
slideshow_pause = 4000
slideshow_on = False
TITLE = __doc__.split("\n")[0]
path = None
paths: list[str] = []
path_index = -1
image_label = None
status_label = None


def browse(event=None):
    global image_label, path_index, status_label

    k = event.keysym if event else "Right"
    delta = -1 if k in ("Left", "Up") else 1

    path_index += delta
    if path_index < 0:
        path_index = len(paths) - 1
    if path_index >= len(paths):
        path_index = 0

    msg = f"Index {path_index + 1}/{len(paths) + 1}"
    status_label.config(text=msg)
    path = paths[path_index]
    show_image(path)


def debug_keys(event=None):
    logging.info(f"KEY: {event}")


def mouse_wheel(event=None):
    logging.info(f"MOUSE: {event}")
    if event.num == 5 or event.delta == -120:
        root.event_generate("<Down>")
    if event.num == 4 or event.delta == 120:
        root.event_generate("<Up>")


def quit(event=None):
    event.widget.withdraw()
    event.widget.quit()


def refresh_paths(event=None):
    global paths
    logging.debug(f"Reading {path}...")
    paths = list(pathlib.Path(path).glob("*"))
    logging.debug(f"Found {len(paths)} files.")


def run_slideshow(event=None):
    if slideshow_on:
        browse()
        root.after(slideshow_pause, run_slideshow)


def set_bg(event=None):
    global bg_index
    bg_index += 1
    if bg_index >= len(bg_colors):
        bg_index = 0
    bg = bg_colors[bg_index]
    root.config(background=bg)
    image_label.config(background=bg)


def show_image(path):
    logging.debug(f"Showing {path}")
    msg = ""
    try:
        pil_img = Image.open(path)
    except Exception as ex:
        msg = str(ex)
        logging.error(msg)
        pil_img = None

    if pil_img:
        im_w, im_h = pil_img.size
        if scale != 1:
            pil_img = pil_img.resize(
                (int(scale * im_w), int(scale * im_h)),
                Image.BICUBIC if antialias_on else None,
            )

        if False:
            logging.debug(image_label.winfo_geometry())
            im_w, im_h = pil_img.size
            if im_w > w or im_h > h:
                ratio = min(w / im_w, h / im_h)
                im_w = int(im_w * ratio)
                im_h = int(im_h * ratio)
                pil_img = pil_img.resize(
                    (im_w, im_h), Image.BICUBIC if antialias_on else None
                )

    msg = (
        f"{path_index+1}/{len(paths)} "
        + (f"{im_w}x{im_h} x{scale:.1f}" if pil_img else msg)
        + f" {path} - {TITLE}"
    )
    root.title(msg)
    status_label.configure(text=msg)

    img = ImageTk.PhotoImage(pil_img) if pil_img else None
    image_label.config(image=img, text="" if img else msg)  # Set it.
    image_label.img = img  # Keep it. Why isn't this built in?!


def toggle_fullscreen(event=None):
    logging.debug("Toggling fullscreen")
    root.attributes("-fullscreen", not root.attributes("-fullscreen"))


def toggle_slideshow(event=None, **kwargs):
    print("KWARGS", kwargs)
    global slideshow_on
    slideshow_on = not slideshow_on
    if slideshow_on:
        logging.info("Starting slideshow.")
        run_slideshow()
    else:
        logging.info("Stopping slideshow.")


def zoom(event=None):
    global scale
    logging.debug(f"ZOOM: {event}")
    k = event.keysym if event else "plus"
    if event.num == 5 or event.delta == -120:
        k = "plus"
    if event.num == 4 or event.delta == 120:
        k = "minus"
    if k == "plus":
        scale *= 1.1
    elif k == "minus":
        scale *= 0.9
    else:
        scale = 1
    if scale < 0.1:
        scale = 0.1
    if scale >= 8:
        scale = 8
    show_image(paths[path_index])


root = tkinter.Tk()
root.title(TITLE)
w, h = root.winfo_screenwidth(), root.winfo_screenheight()
root.geometry("%dx%d" % (int(w / 2), int(h / 2)))

image_label = tkinter.Label(root, width=w, height=h, fg="red")
image_label.pack()

status_label = tkinter.Label(
    root,
    text="status",
    font=("Consolas", 14),
    fg="green3",
    bg="grey19",
    wraplength=w,
    anchor="nw",
    justify="left",
)
status_label.pack()

set_bg()


root.bind_all("<Key>", debug_keys)
root.bind("<Escape>", quit)

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
        description="An image viewer that supports both arrow keys and WebP with foreign characters in long paths."
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

    path = args.path
    refresh_paths()
    browse()

    if args.slideshow:
        slideshow_pause = args.slideshow
        toggle_slideshow()

    root.mainloop()
