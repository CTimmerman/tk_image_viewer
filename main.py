"""Tk Image Viewer
by Cees Timmerman
2024-03-17 First version.
2024-03-23 Save stuff.
2024-03-24 Zip and multiframe image animation support.
2024-03-27 Set sort order. Support EML, MHT, MHTML.
2024-03-30 Copy info + paste/drop picture(s)/paths.
2024-04-08 Scroll/drag.
2024-04-10 AVIF, JXL, SVG support.
2024-04-25 Photoshop IRB, XMP, exiftool support.
2024-06-19 Windows WYSIWYG copy like PrtScr.
2025-12-24 Select all as displayed, and filter/reverse files.
"""

# pylint: disable=consider-using-f-string, global-statement, line-too-long, multiple-imports, no-member, too-many-boolean-expressions, too-many-branches, too-many-lines, too-many-locals, too-many-nested-blocks, too-many-statements, unused-argument, unused-import, wrong-import-position
import argparse, base64, enum, functools, gzip, logging, os, pathlib, random, re, sys, tarfile, time, tkinter, zipfile  # noqa: E401
from io import BytesIO
from tkinter import filedialog, messagebox, simpledialog, ttk
from typing import Optional

# pyrefly: ignore[unused-import]  # Also in the toml but VS Code still marks it!
import pillow_jxl  # noqa: F401
import pyperclip  # type: ignore
from PIL import GifImagePlugin, Image, ImageGrab, ImageTk
from PIL.Image import Transpose
from pillow_heif import register_heif_opener  # type: ignore
from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore


os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
import pygame  # noqa: E402

from metadata import info_get  # noqa: E402

GifImagePlugin.LOADING_STRATEGY = (
    GifImagePlugin.LoadingStrategy.RGB_AFTER_DIFFERENT_PALETTE_ONLY
)


class Fits(enum.IntEnum):
    """Window fitting types"""

    NONE = 0
    ALL = 1
    BIG = 2
    SMALL = 3


BG_COLORS = ["black", "gray10", "gray50", "white"]
FOLDER = FOLDER = os.path.dirname(
    os.path.realpath((sys.argv and sys.argv[0]) or sys.executable)  # type: ignore
)
CONFIG_FILE = os.path.join(FOLDER, "tiv.state")
FONT_SIZE = 14
RESIZE_QUALITY = [
    Image.Resampling.NEAREST,
    Image.Resampling.BOX,
    Image.Resampling.BILINEAR,
    Image.Resampling.HAMMING,
    Image.Resampling.BICUBIC,
    Image.Resampling.LANCZOS,
]
SCALE_MIN = 0.001
SCALE_MAX = 40.0
SCROLL_SPEED = 10.0
SORTS = "natural string ctime mtime size".split()
TIME_FORMAT = "%Y-%m-%d %H:%M:%S%z"
TITLE = __doc__.split("\n", 1)[0]  # type: ignore
VERBOSITY_LEVELS = [
    logging.CRITICAL,
    logging.ERROR,
    logging.WARN,
    logging.INFO,
    logging.DEBUG,
]

# Set log line format. Force to override submodules.
logging.basicConfig(format="%(levelname)s: %(message)s")  # , force=True)
LOG = logging.getLogger(__name__)

register_heif_opener()


def log_this(func):
    """Decorator to log function calls"""

    @functools.wraps(func)  # Keep signature.
    def inner(*args, **kwargs):
        LOG.debug("Calling %s with %s, %s", func.__name__, args, kwargs)
        return func(*args, **kwargs)

    return inner


def animation_toggle(event=None):
    """Animation"""
    APP.b_animate = not APP.b_animate
    if APP.b_animate:
        toast("Starting animation")
        im_resize(APP.b_animate)
    else:
        s = "Stopping animation" + (
            f" Frame {1 + (1 + APP.im_frame) % APP.im.n_frames}/{APP.im.n_frames}"
            if hasattr(APP.im, "n_frames")
            else ""
        )
        LOG.info(s)
        toast(s)


def bind():
    """Bind input events to functions"""
    # APP.bind_all("<Key>", debug_keys)
    for b in BINDS:
        func = b[0]
        if func == "-":
            continue
        for event in b[1].split(" "):
            APP.bind(f"<{event}>", func)


def browse(event=None, delta: int = 0, pos: Optional[int] = None):
    """Browse list of paths"""
    i, _ = browse_get()
    if pos is not None:
        new_index = pos
    else:
        new_index = i + delta

    if APP.browse_archives and "Names" in APP.info:
        if new_index == -1:
            new_index = APP.i_path - 1
        elif new_index == len(APP.info["Names"]):
            new_index = APP.i_path + 1
        else:
            APP.i_zip = new_index
            im_load()
            return

    if new_index < 0:
        new_index = len(APP.paths) - 1
    if new_index >= len(APP.paths):
        new_index = 0

    APP.i_path = new_index
    APP.i_zip = 0
    im_load()


def browse_archive_toggle(event=None):
    """Browse archives"""
    APP.browse_archives = not APP.browse_archives
    toast(f"Archive browse {APP.browse_archives}")


def browse_end(event=None):
    """Last"""
    _, arr = browse_get()
    browse(pos=len(arr) - 1)


def browse_home(event=None):
    """First"""
    browse(pos=0)


def browse_frame(event=None):
    """Browse animation"""
    if not hasattr(APP.im, "n_frames"):
        toast("No frames")
        return
    last = APP.im.n_frames - 1
    k = event.keysym if event else ""
    if k == "comma":
        APP.im_frame -= 1
        if APP.im_frame < 0:
            APP.im_frame = last
    else:
        APP.im_frame += 1
        if APP.im_frame > last:
            APP.im_frame = 0

    APP.im.seek(APP.im_frame)
    im_resize()
    toast(f"Frame {1 + APP.im_frame}/{1 + last}", 1000)


def browse_get():
    """Return index and array of files"""
    if APP.browse_archives and "Names" in APP.info:
        arr = APP.info["Names"]
        i = APP.i_zip
    else:
        arr = APP.paths
        i = APP.i_path
    return i, arr


def browse_index(event=None):  # Context menu lacks event
    """Index..."""
    i, _ = browse_get()
    i = simpledialog.askinteger("Index", "Where to?", initialvalue=i + 1, parent=APP)
    if not i:
        return
    browse(pos=i - 1)


def browse_mouse(event):
    """Previous/Next"""
    browse(delta=-1 if event.delta > 0 else 1)


def browse_next(event=None):
    """Next"""
    browse(delta=1)


def browse_prev(event=None):
    """Previous"""
    browse(delta=-1)


def browse_percentage(event):
    """0 to 90% of list: Shift+0-9"""
    _, arr = browse_get()
    if hasattr(event, "state") and event.state & 1 and event.keycode in range(48, 58):
        ni = int(len(arr) / 10 * (event.keycode - 48))
        browse(pos=ni)


def browse_random(event=None):
    """Random"""
    _, arr = browse_get()
    browse(pos=random.randint(0, len(arr) - 1))


def browse_search(event=None):
    """Find..."""
    i, arr = browse_get()

    s = simpledialog.askstring(
        "File name", "Search for?", initialvalue=arr[i], parent=APP
    )
    if not s:
        return

    found = False
    start = i
    n = len(arr)
    while True:
        i = (i + 1) % n
        if s in str(arr[i]):
            found = True
            break
        if i == start:
            break
    if not found:
        toast(f"{s} not found")
    browse(pos=i)


def clipboard_copy(event=None):
    """Copy"""
    if CANVAS.find_closest(0, 0) == (CANVAS.text_bg,):
        LOG.debug("Copying overlay")
        pyperclip.copy(CANVAS.itemcget(CANVAS.text, "text"))
        toast("Copied info")
    elif isinstance(APP.winfo_children()[-1], tkinter.Label):
        LOG.debug("Copying title.")
        pyperclip.copy(APP.title())
        toast("Copied title")
    elif APP.b_lines and CANVAS.lines:
        im_left, im_top, _, _ = CANVAS.bbox(CANVAS.image_ref)
        left, top, right, bottom = CANVAS.bbox(CANVAS.lines[0])
        im = ImageTk.getimage(CANVAS.tkim).crop(
            (left - im_left, top - im_top, right - im_left, bottom - im_top)
        )
        try:
            import clipboard  # pylint:disable=import-outside-toplevel  # App loads slow enough as is.

            clipboard.copy(im)
            toast("Copied selection")
        except ImportError as ex:
            LOG.error("Clipboard error: %s", ex)
            toast(f"{ex}")
    else:
        LOG.debug("Copying path")
        pyperclip.copy(str(path_get().absolute()))
        toast("Copied path")


def clipboard_paste(event=None):
    """Paste"""
    im = ImageGrab.grabclipboard()
    LOG.debug("Pasted %r", im)
    if not im:
        im = APP.clipboard_get()
        LOG.debug("Tk pasted %r", im)
        if not im:
            return
    if isinstance(im, str):
        im = [line.strip('"') for line in im.split("\n")]
    if isinstance(im, list):
        paths_set([pathlib.Path(s) for s in im])
        return
    APP.im = im
    APP.info = {"Pasted": time.ctime()}
    APP.i_path = 0
    APP.i_zip = 0
    APP.paths = ["pasted"]
    im_resize()


def paths_set(paths: list | tuple):
    """Change paths"""
    APP.paths = [pathlib.Path(s) for s in paths]
    APP.i_path = 0
    APP.i_zip = 0
    LOG.debug("Set paths to %s", APP.paths)
    if not APP.paths:
        toast("No paths")
        return
    if len(APP.paths) == 1:
        paths_update(None, APP.paths[0], open_folder=True)
        return
    im_load()


@log_this
def close(event=None):
    """Exit fullscreen or app"""
    if APP.overrideredirect():
        fullscreen_toggle()
    else:
        config_save()
        APP.quit()


def config_save():
    """Save geometry like IrfanView"""
    try:
        with open(CONFIG_FILE, "w+", encoding="utf8") as fp:
            s = fp.read()
            if " -g" not in s:
                s += " -g _"

            if APP.state() == "zoomed":
                if " -m" not in s:
                    s += " -m"
                g = APP.old_geometry
            else:
                s = s.replace(" -m", "")
                g = APP.geometry()
            s = re.sub(r" (-g|--geometry) ([^\s]+)", rf" \1 {g}", s)
            s = re.sub(r" (-r|--resize)( [0-3])?", "", s)
            s = re.sub(r" (-z|--archives)", "", s)
            if APP.fit:
                s += f" -r {APP.fit}"
            if APP.browse_archives:
                s += " -z"
            LOG.debug("Saving state %s", s)
            fp.seek(0)
            fp.write(s)
    except IOError as ex:
        LOG.error("Config save error: %s", ex)


@log_this
def debug_keys(event=None):
    """Show all keys"""


def delete_file(event=None):
    """Delete"""
    path = path_get()
    msg = f"Delete? {path}"
    LOG.warning(msg)
    if messagebox.askokcancel(
        "Delete File",
        f"Permanently delete {path}?",
        default="cancel",
        icon=messagebox.WARNING,
        parent=APP,
    ):
        LOG.warning("Deleting %s", path)
        os.remove(path)
        paths_update()


def drag_begin(event):
    """Keep drag begin pos for delta move"""
    if event.widget != CANVAS:
        return
    CANVAS.dragx = CANVAS.canvasx(event.x)
    CANVAS.dragy = CANVAS.canvasy(event.y)
    CANVAS.config(cursor="fleur" if event.num == 1 else "tcross")


def drag_end(event):
    """End drag"""
    if event.widget != CANVAS:
        return
    CANVAS.config(cursor="")
    if (
        CANVAS.canvasx(event.x) == CANVAS.dragx
        and CANVAS.canvasy(event.y) == CANVAS.dragy
    ):
        lines_toggle(off=True)


def drag(event):
    """Drag image"""
    if event.widget != CANVAS:
        return

    evx, evy = CANVAS.canvasx(event.x), CANVAS.canvasy(event.y)
    x, y, x2, y2 = CANVAS.bbox(CANVAS.image_ref)
    w = x2 - x
    h = y2 - y
    dx, dy = int(evx - CANVAS.dragx), int(evy - CANVAS.dragy)
    # Keep at least a corner in view.
    # Goes entirely out of view when switching to smaller imag!
    # new_x = max(-w + 64, min(APP.winfo_width() - 64, x + dx))
    # new_y = max(-h + 64, min(APP.winfo_height() - 64, y + dy))

    new_x = max(0, min(APP.winfo_width() - w, x + dx))
    new_y = max(0, min(APP.winfo_height() - h, y + dy))
    if new_x == 0:
        CANVAS.xview_scroll(int(-dx / SCROLL_SPEED), "units")
    if new_y == 0:
        CANVAS.yview_scroll(int(-dy / SCROLL_SPEED), "units")

    dx, dy = new_x - x, new_y - y
    CANVAS.move(CANVAS.image_ref, dx, dy)
    scrollbars_set()
    CANVAS.dragx, CANVAS.dragy = evx, evy


@log_this
def select(event=None):
    """Select area"""
    if event and event.keycode != 65 and event.widget != CANVAS:
        return

    lines_toggle(on=True)
    if not event or event.keycode == 65:
        x, y, x2, y2 = CANVAS.bbox(CANVAS.image_ref)
        x += 2
        y += 2
        x2 -= 2
        y2 -= 2
    else:
        x = CANVAS.dragx
        y = CANVAS.dragy
        x2 = CANVAS.canvasx(event.x)
        y2 = CANVAS.canvasy(event.y)
        w = CANVAS.winfo_width()
        h = CANVAS.winfo_height()
        px = CANVAS.winfo_pointerx() - CANVAS.winfo_rootx()
        py = CANVAS.winfo_pointery() - CANVAS.winfo_rooty()
        if px < 0:
            CANVAS.xview_scroll(-int(SCROLL_SPEED), "units")
        elif px > w:
            CANVAS.xview_scroll(int(SCROLL_SPEED), "units")
        if py < 0:
            CANVAS.yview_scroll(-int(SCROLL_SPEED), "units")
        elif py > h:
            CANVAS.yview_scroll(int(SCROLL_SPEED), "units")

    CANVAS.coords(CANVAS.lines[0], x, y, x2, y, x, y2, x2, y2)
    CANVAS.coords(CANVAS.lines[1], x, y, x2, y, x, y2, x2, y2)
    CANVAS.coords(CANVAS.lines[2], x, y2, x, y, x2, y2, x2, y)
    CANVAS.coords(CANVAS.lines[3], x, y2, x, y, x2, y2, x2, y)


@log_this
def drop_handler(event):
    """Handle dropped files"""
    LOG.debug("Dropped %r", event.data)
    paths_set(
        [
            pathlib.Path(line.strip('"'))
            for line in re.findall(
                "{(.+?)}" if "{" in event.data else "[^ ]+", event.data
            )
        ]
    )  # Windows 11.


def error_show(msg: str):
    """Show error"""
    # Remove old image from help/info overlay.
    im_show(Image.new("1", (1, 1)))
    APP.title(msg + " - " + TITLE)
    ERROR_OVERLAY.config(text=msg, fg="#00FF00" if "Press enter" in msg else "red")
    ERROR_OVERLAY.lift()
    APP.i_path_old = -1  # To refresh image info.
    if "Press enter" not in msg:
        LOG.error(msg)
        if LOG.level == logging.DEBUG:
            raise ValueError(msg)


def help_toggle(event=None):
    """Help"""
    if APP.showing == "help":
        info_hide()
    else:
        APP.showing = "help"
        lines = []
        for fun, keys in BINDS:
            if fun in ("-", drag_begin, drag_end, resize_handler):
                continue
            key_part = "" if ": " in fun.__doc__ else ": "
            if key_part:
                key_part += re.sub(
                    "((^|[+])[a-z])",
                    lambda m: m.group(1).upper(),
                    re.sub(
                        "([OQTV])\\b",
                        "Shift+\\1",
                        keys.replace("Key-", "")
                        .replace("Button-", "B")
                        .replace("Mouse", "")
                        .replace("Control-", "Ctrl+")
                        .replace("Alt-", "Alt+")
                        .replace("Shift-", "Shift+")
                        .replace(" Prior ", " PageUp ")
                        .replace(" Next ", " PageDown "),
                    ),
                    count=0,
                    flags=re.MULTILINE,
                )
            # Dedup case-sensitive shortcuts
            last_key = ""
            new_keys = []
            for key in key_part.split(" "):
                if key == last_key:
                    pass
                else:
                    last_key = key
                    new_keys.append(key)

            lines.append(fun.__doc__.replace("...", "") + " ".join(new_keys))

        msg = "\n".join(lines)
        info_set(msg)
        info_show()
        LOG.debug(msg)


def info_set(msg: str):
    """Change info text"""
    CANVAS.itemconfig(CANVAS.text, text=msg)  # type: ignore
    info_bg_update()


def info_bg_update():
    """Update info overlay"""
    x1, y1, x2, y2 = CANVAS.bbox(CANVAS.text)
    CANVAS.text_bg_tkim = ImageTk.PhotoImage(  # type: ignore
        Image.new("RGBA", (x2 - x1, y2 - y1), "#000a")
    )
    CANVAS.itemconfig(CANVAS.text_bg, image=CANVAS.text_bg_tkim)  # type: ignore
    CANVAS.coords(CANVAS.im_bg, x1, y1, x2, y2)


def lines_toggle(event=None, on=None, off=None):
    """Line overlay"""
    APP.b_lines = True if on else False if off else not APP.b_lines  # NOSONAR
    if not APP.b_lines and CANVAS.lines:
        for line in CANVAS.lines:
            CANVAS.delete(line)
        CANVAS.lines = []
    if APP.b_lines and not CANVAS.lines:
        w = APP.winfo_width() - 1
        h = APP.winfo_height() - 1
        # Windows sucks at dashed lines. https://tcl.tk/man/tcl8.5/TkCmd/canvas.htm#M18
        CANVAS.lines.append(
            CANVAS.create_line(0, 0, w, 0, 0, h, w, h, fill="white", dash=(6, 4))  # type: ignore[call-arg]
        )
        CANVAS.lines.append(
            CANVAS.create_line(0, 0, w, 0, 0, h, w, h, fill="black", dash=(2, 4))  # type: ignore[call-arg]
        )
        CANVAS.lines.append(
            CANVAS.create_line(0, h, 0, 0, w, h, w, 0, fill="white", dash=(6, 4))  # type: ignore[call-arg]
        )
        CANVAS.lines.append(
            CANVAS.create_line(0, h, 0, 0, w, h, w, 0, fill="black", dash=(2, 4))  # type: ignore[call-arg]
        )


def load_mhtml(path):
    """Load image from EML/MHT/MHTML"""
    with open(path, "r", encoding="utf8") as f:
        mhtml = f.read()
    boundary = re.search('boundary="(.+)"', mhtml).group(1)  # type: ignore
    parts = mhtml.split(boundary)[1:-1]
    names = []
    new_parts = []
    for p in parts:
        meta, data = p.split("\n\n", maxsplit=1)
        m = meta.lower()
        if "\ncontent-transfer-encoding: base64" not in m:
            continue
        if "\ncontent-type:" in m and "\ncontent-type: image" not in m:
            continue
        name = sorted(meta.strip().split("\n"))[0].split("/")[-1]
        names.append(name)
        new_parts.append(data)
    if not new_parts:
        raise ValueError(f"No image found in {path}")
    APP.info["Names"] = names
    LOG.debug(
        "%s",
        f"Getting image {1 + APP.i_zip}/{len(new_parts)} of {len(parts)} parts: {APP.info['Names'][APP.i_zip]}",
    )
    data = new_parts[APP.i_zip]
    im_file = None
    try:
        im_file = BytesIO(base64.standard_b64decode(data.rstrip()))
        APP.im = Image.open(im_file)
    except (Image.UnidentifiedImageError, ValueError) as ex:
        LOG.error("MHT %s", ex)
        LOG.error("DATA %r", data[:180])
        if im_file:
            im_file.seek(0)
            LOG.error("DECODED %s", im_file.read()[:80])
            # https://github.com/fdintino/pillow-avif-plugin/issues/13
            # with open(f"tiv_mhtml_image_{1 + APP.i_zip}_fail.avif", "wb") as f:
            #     f.write(im_file.read())
        ex.args = (f"Failed to load image {1 + APP.i_zip} of",)
        raise ex


def load_svg(fpath):
    """Load SVG file"""
    if fpath.suffix == ".svgz":  # NOSONAR
        with gzip.open(fpath, "rt", encoding="utf8") as f:
            data = f.read()
    else:
        with open(fpath, "r", encoding="utf8") as fp:
            data = fp.read()

    size = None
    try:
        size = [
            round(float(v))
            for v in re.split(
                "[, ]+",
                re.findall(
                    r'viewbox\s*=\s*"([, 0-9.]+)"', data, re.DOTALL | re.IGNORECASE
                )[0],
            )
        ][2:]
    except IndexError:
        pass
    try:
        size = [
            round(
                float(re.findall(rf'<svg [^>]*?{k}\s*=\s*"([0-9.]+)"[^>]*>', data)[0])
            )
            for k in ("width", "height")
        ]
    except IndexError:
        pass
    if size:
        r = get_fit_ratio(*size)
        data = re.sub(
            "<svg([^>]+)>",
            f'<svg \\1 width="{size[0]*r}" height="{size[1]*r}" transform="scale({r})">',
            data,
        )

    surface = pygame.image.load(BytesIO(data.encode()))
    bf = BytesIO()
    pygame.image.save(surface, bf, "png")
    APP.im = Image.open(bf)


def has_supported_extension(name: str | pathlib.Path):
    """To skip unsupported files"""
    if str(name).startswith("__MACOSX"):
        return False
    if isinstance(name, pathlib.Path) and name.is_dir(follow_symlinks=True):
        return True
    for ext in APP.SUPPORTED_EXTENSIONS:
        if str(name).upper().endswith(ext):
            return True
    # LOG.debug(f"Excluding {name}; not endswith {APP.SUPPORTED_EXTENSIONS}")
    return False


def load_tar(path):
    """Load file from tar with optional compression"""
    with tarfile.open(path, "r") as tf:
        names = tf.getnames()
        LOG.debug("Contains %s names", len(names))
        if APP.filter_names:
            names = list(filter(has_supported_extension, names))
        LOG.debug("of which %s images", len(names))
        if len(names) == 0:
            raise ValueError("No image found")

        for s in APP.sort.split(","):
            if s == "natural":
                names.sort(key=natural_sort, reverse=APP.reverse)
            elif s == "string":
                names.sort(reverse=APP.reverse)

        APP.info["Names"] = names
        try:
            name = names[APP.i_zip]
        except IndexError:
            LOG.info("Can't read tar index %s/%s", APP.i_zip, len(names))
            APP.i_zip = 0
            name = names[0]

        LOG.debug("Loading tar index %s: %s", APP.i_zip, name)
        im_fp = tf.extractfile(name)
        LOG.debug("Loading im file %s", im_fp)
        if not im_fp:
            raise TypeError(f"Not an image: {name}")
        APP.im = Image.open(im_fp)
        fmt = APP.im.format
        # No-copy APP.im works only while stepping through, else ValueError: I/O operation on closed file
        # copy loses format
        APP.im = APP.im.copy()  # type: ignore
        APP.im.format = fmt


def load_zip(path):
    """Load file from zip"""
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        if APP.filter_names:
            names = list(filter(has_supported_extension, names))
        if len(names) == 0:
            APP.im = None
            return

        for s in APP.sort.split(","):
            if s == "natural":
                names.sort(key=natural_sort, reverse=APP.reverse)
            elif s == "string":
                names.sort(reverse=APP.reverse)

        APP.info["Names"] = names
        LOG.debug("Loading zip index %s", APP.i_zip)
        # pylint: disable=consider-using-with
        try:
            APP.im = Image.open(zf.open(names[APP.i_zip]))
        except IndexError:
            APP.i_zip = 0
            APP.im = Image.open(zf.open(names[APP.i_zip]))


def im_load(path=None):
    """Load image"""
    path = path_get(path)
    msg = f"{APP.i_path+1}/{len(APP.paths)}"
    LOG.debug("Loading %s %s", msg, path)

    err_msg = ""
    try:
        if path != "pasted":
            set_stats(path)
            if path.suffix == ".zip":
                load_zip(path)
            elif path.suffix in (".svg", ".svgz"):
                load_svg(path)
            elif path.suffix in (".eml", ".mht", ".mhtml"):
                load_mhtml(path)
            elif path.suffix in (".tar", ".tbz2", ".tgz", ".txz") or "".join(
                path.suffixes[-2:]
            ) in (".tar.bz2", ".tar.gz", ".tar.xz", ".tar.zst", ".tar.zstd"):
                load_tar(path)
            else:
                APP.im = Image.open(path)
                APP.im.load()  # Else im.info = {} for AVIF.
        APP.info.update(**APP.im.info)
        APP.im_frame = 0
        if hasattr(APP.im, "n_frames"):
            n = APP.im.n_frames
            if n > 1:
                APP.info["Frames"] = n
                duration: int = 0
                # for frame in range(n - 1, -1, -1):  # 116 GIF frames in 15.45s vs 0.21s!
                for frame in range(n):
                    APP.im.seek(frame)
                    duration += int(APP.im.info.get("duration", 100)) or 100
                APP.im.seek(0)
                APP.info["duration"] = f"{duration} ms"
                if APP.b_animate:
                    APP.im_frame = -1  # Animation increments before displaying.
        im_resize(APP.b_animate)
    # pylint: disable=W0718
    except (
        tkinter.TclError,
        IOError,
        MemoryError,  # NOSONAR
        EOFError,  # NOSONAR
        ValueError,  # NOSONAR
        BufferError,  # NOSONAR
        OSError,  # NOSONAR
        PermissionError,  # NOSONAR
        BaseException,  # NOSONAR  # https://github.com/PyO3/pyo3/issues/3519
    ) as ex:
        if os.path.isdir(path):
            err_msg = "Press enter to open folder:"
        else:
            err_msg = f"{type(ex).__name__}: {ex}"
            if LOG.level == logging.DEBUG:
                raise ex
        APP.im = None
        msg = f"{msg} {err_msg}{f' {path}' if repr(str(path)) not in err_msg and str(path) not in err_msg else ''}"

        error_show(msg)


def get_fit_ratio(im_w: int, im_h: int) -> float:
    """Get fit ratio"""
    ratio = 1.0
    w = APP.winfo_width()
    h = APP.winfo_height()
    if (
        ((APP.fit == Fits.ALL) and (im_w != w or im_h != h))
        or ((APP.fit == Fits.BIG) and (im_w > w or im_h > h))
        or ((APP.fit == Fits.SMALL) and (im_w < w and im_h < h))
    ):
        ratio = min(w / im_w, h / im_h)
    return ratio


def im_fit(im):
    """Fit image to window"""
    w, h = im.size
    ratio = get_fit_ratio(w, h)
    if ratio != 1.0:  # NOSONAR
        im = im.resize((int(w * ratio), int(h * ratio)), APP.quality)
    return im


def im_scale(im):
    """Scale image"""
    im_w, im_h = im.size
    ratio = APP.im_scale * get_fit_ratio(im_w, im_h)
    try:
        new_w = int(ratio * im_w)
        new_h = int(ratio * im_h)
        if new_w < 1 or new_h < 1:
            LOG.error("Too small. Scaling up.")
            APP.im_scale = max(SCALE_MIN, min(APP.im_scale * 1.1, SCALE_MAX))
            im = im_scale(im)
        else:
            im = APP.im.resize((new_w, new_h), APP.quality)
    except MemoryError as ex:
        LOG.error("Out of memory. Scaling down. %s", ex)
        APP.im_scale = max(SCALE_MIN, min(APP.im_scale * 0.9, SCALE_MAX))

    return im


def im_resize(loop: bool = False):
    """Resize image"""
    if not (hasattr(APP, "im") and APP.im):
        return

    if loop and APP.info.get("Frames", 1) > 1:
        APP.im_frame = (APP.im_frame + 1) % APP.im.n_frames
        try:
            APP.im.seek(APP.im_frame)
        except EOFError as ex:
            LOG.error("IMAGE EOF. %s", ex)
        # 10 FPS default; nice and round.
        duration = (
            int(APP.im.info.get("duration", 100)) or 100
        )  # apng have float ms duration?!
        # Cancel existing timer.
        if hasattr(APP, "animation"):
            APP.after_cancel(APP.animation)
        # Set new timer.
        APP.animation = APP.after(duration, im_resize, APP.b_animate)

    im = APP.im.copy()  # Loses im.format!

    if APP.fit:
        im = im_fit(APP.im)

    if APP.im_scale != 1:
        im = im_scale(APP.im)

    if APP.transpose_type != -1:
        LOG.debug("Transposing %s", Transpose(APP.transpose_type))
        im = im.transpose(APP.transpose_type)

    im_show(im)


def im_show(im):
    """Show PIL image in Tk image widget"""
    try:
        CANVAS.tkim: ImageTk.PhotoImage = ImageTk.PhotoImage(im)  # type: ignore
        CANVAS.itemconfig(CANVAS.image_ref, image=CANVAS.tkim, anchor="center")

        try:
            rw, rh = APP.winfo_width(), APP.winfo_height()
            x, y, x2, y2 = CANVAS.bbox(CANVAS.image_ref)
            w = x2 - x
            h = y2 - y
            good_x = rw // 2 - w // 2
            good_y = rh // 2 - h // 2
            # canvas.move(canvas.image_ref, -x + canvas.winfo_width() // 2, -y + canvas.winfo_height() // 2)
            CANVAS.move(CANVAS.image_ref, good_x - x, good_y - y)
        except TypeError as ex:
            LOG.error(ex)

        ERROR_OVERLAY.lower()
    except MemoryError as ex:
        LOG.error("Out of memory. Scaling down. %s", ex)
        APP.im_scale = max(SCALE_MIN, min(APP.im_scale * 0.9, SCALE_MAX))
        return

    zip_info = ""
    if "Names" in APP.info and len(APP.info["Names"]):
        if APP.i_zip > len(APP.info["Names"]):
            APP.i_zip = 0
        zip_info = (
            f" {APP.i_zip + 1}/{len(APP.info['Names'])} {APP.info['Names'][APP.i_zip]}"
        )

    msg = (
        f"{APP.i_path+1}/{len(APP.paths)}{zip_info} {('%sx%s' % APP.im.size) if APP.im else ''}"
        f"->{'%sx%s' % im.size} {path_get()}"
    )
    APP.title(msg + " - " + TITLE)
    if APP.showing == "info" and (
        not hasattr(APP, "i_path_old")
        or APP.i_path != APP.i_path_old
        or not hasattr(APP, "i_path_old")
        or APP.i_zip != APP.i_zip_old
    ):
        APP.i_path_old = APP.i_path
        APP.i_zip_old = APP.i_zip
        CANVAS.config(cursor="watch")
        info_set(msg + info_get(APP.im, APP.info, path_get()))
        CANVAS.config(cursor="")
    scrollbars_set()


def info_toggle(event=None, show: bool | None = None):
    """Info"""
    if show or APP.showing != "info":
        APP.showing = "info"
        CANVAS.config(cursor="watch")
        info_set(
            APP.title()[: -len(" - " + TITLE)] + info_get(APP.im, APP.info, path_get())
        )
        LOG.debug("Showing info:\n%s", CANVAS.itemcget(CANVAS.text, "text"))  # type: ignore
        info_show()
        CANVAS.config(cursor="")
    else:
        info_hide()


def info_show():
    """Show info overlay"""
    ERROR_OVERLAY.lower()
    CANVAS.lift(CANVAS.text_bg)
    CANVAS.lift(CANVAS.text)
    scrollbars_set()


def info_hide():
    """Hide info overlay"""
    APP.showing = ""
    info_set("")
    CANVAS.lower(CANVAS.text_bg)
    CANVAS.lower(CANVAS.text)
    scrollbars_set()


def menu_init():
    """Create context menu"""
    for fun, keys in BINDS:
        if fun in (
            browse_home,
            browse_index,
            browse_mouse,
            browse_next,
            browse_prev,
            browse_percentage,
            browse_search,
            close,
            drag,
            drag_begin,
            drag_end,
            lines_toggle,
            menu_show,
            paths_down,
            paths_up,
            resize_handler,
            scroll,
            scroll_toggle,
            zoom,
            zoom_text,
        ):
            continue

        if fun == "-":
            MENU.add_separator()
            continue

        lbl = str(fun.__doc__).title()
        if re.match("[a-z0-9]( |$)", keys):
            uli = lbl.find(keys[0].upper())
            if uli < 0:
                uli = lbl.find(keys[0].lower())
            if uli < 0:
                lbl += f" [{keys[0].upper()}]"
                uli = len(lbl) - 2
            MENU.add_command(label=lbl, command=fun, underline=uli)
        else:
            MENU.add_command(
                label=lbl, command=fun
            )  # , accelerator=keys) makes menu too wide


def menu_show(event):
    """Menu"""
    MENU.post(event.x_root, event.y_root)


def natural_sort(s: str):
    """Sort by number and string
    >>> a = ['koko2.gif', 'koko 0004.gif', r'koko.gif']
    >>> a.sort(key=natural_sort); a
    ['koko.gif', 'koko2.gif', 'koko 0004.gif']
    """
    return [
        -1 if t == "." else int(t) if t.isdigit() else t.lower()
        for t in re.split(r"(\d+|[.])", str(s))
    ]


def path_get(path: pathlib.Path | None = None) -> pathlib.Path:
    """Return shown path"""
    if path:
        return path
    return pathlib.Path(APP.paths[max(APP.i_path, 0)])


@log_this
def path_open(event=None):
    """Open file..."""
    filenames = filedialog.askopenfilenames(filetypes=APP.SUPPORTED_FILES_READ)
    if filenames:
        paths_set(filenames)


@log_this
def path_save(event=None, filename=None, newmode=None, noexif=False):
    """Save as..."""
    if "Names" in APP.info:
        p = pathlib.Path(str(path_get()) + "." + APP.info["Names"][APP.i_zip])
    else:
        p = path_get()

    if not filename:
        filename = filedialog.asksaveasfilename(
            defaultextension=p.suffix,
            filetypes=APP.SUPPORTED_FILES_WRITE,
            initialfile=p.absolute(),
        )
    if not filename:
        return
    LOG.info("Saving %s", filename)
    im = APP.im.convert(newmode) if newmode else APP.im
    save_all = hasattr(im, "n_frames") and im.n_frames > 1
    fmt = filename.split(".")[-1].upper()
    if fmt == "JPG":
        fmt = "JPEG"
    if save_all and fmt not in Image.SAVE_ALL:
        if not messagebox.askokcancel(
            "Lose Frames",
            f"Can only store one frame in {fmt}. Ignore the rest?",
            icon=messagebox.WARNING,
            parent=APP,
        ):
            return
        save_all = False
    try:
        im_info = im.info.copy()
        if noexif:
            del im_info["exif"]

        del im_info["duration"]  # Only contains one frame.
        LOG.debug("Saving info: %s", im_info)
        if save_all and filename.endswith("webp"):
            del im_info["background"]
        im.save(
            filename,
            None,  # Let Pillow handle ".jfif" -> JPEG
            **im_info,
            lossless=True,
            optimize=True,
            save_all=save_all,  # All frames.
        )
        paths_update()
        toast(f"Saved {filename}")
    except (IOError, KeyError, TypeError, ValueError) as ex:
        msg = f"Failed to save as {filename}. {ex}"
        LOG.error(msg)
        toast(msg, 4000, "red")
        if str(
            ex
        ) == "EXIF data is too long" and messagebox.askokcancel(  # From Pillow 9.5.0 (2023-04-01)
            "Lose EXIF", f"{ex}. Retry without it?", icon=messagebox.WARNING, parent=APP
        ):
            path_save(filename=filename, newmode=newmode, noexif=True)
            return
        if str(ex) == "cannot write mode RGBA as JPEG":
            path_save(filename=filename, newmode="RGB", noexif=noexif)
            return
        raise


def paths_sort(path=None, reverse=False):
    """Sort paths"""
    LOG.debug("Sorting %s", APP.sort)
    if not APP.paths:
        LOG.error("No paths to sort.")
        return
    path = path_get(path)

    for s in APP.sort.split(","):
        if s == "natural":
            APP.paths.sort(key=natural_sort, reverse=reverse)
        elif s == "ctime":
            # only mtime in zip
            APP.paths.sort(key=os.path.getmtime, reverse=reverse)
        elif s == "mtime":
            APP.paths.sort(key=os.path.getmtime, reverse=reverse)
        elif s == "random":
            random.shuffle(APP.paths)
        elif s == "size":
            APP.paths.sort(key=os.path.getsize, reverse=reverse)
        elif s == "string":
            APP.paths.sort(reverse=reverse)

    try:
        APP.i_path = APP.paths.index(pathlib.Path(path))
    except ValueError:
        pass

    try:
        im_load()
    except ValueError as ex:
        error_show("Not found: %s" % ex)


def paths_up(event=None, path=None):
    """Leave folder"""
    APP.i_path = max(APP.i_path, 0)
    path = path_get(path)

    p = pathlib.Path(path or ".")
    p = p.parent
    paths_update(None, p.parent, open_folder=True)


def paths_down(event=None, path=None):
    """Enter folder"""
    APP.i_path = max(APP.i_path, 0)
    path = path_get(path)
    paths_update(None, path, open_folder=True)


def filter_toggle(event=None):
    """No filter"""
    APP.filter_names = not APP.filter_names
    toast(f"Filter: {APP.filter_names}")
    APP.after(1000, paths_update)


def paths_update(event=None, path=None, open_folder=False):
    """Refresh"""
    path = path_get(path)
    p = pathlib.Path(path)
    if not p.is_dir() or not open_folder:
        p = p.parent
    LOG.debug("Reading %s", p)
    if APP.filter_names:
        paths = list(filter(has_supported_extension, p.glob("*")))
    else:
        paths = list(p.glob("*"))
    if paths:
        APP.paths = paths
        APP.i_path = 0  # In case path is gone.
        LOG.debug("Found %s files.", len(APP.paths))
        paths_sort(path, reverse=APP.reverse)
    else:
        toast("Folder empty")


def refresh_loop():
    """Autorefresh paths"""
    if APP.update_interval > 0:
        paths_update()
        if hasattr(APP, "path_updater"):
            APP.after_cancel(APP.path_updater)
        APP.path_updater = APP.after(APP.update_interval, refresh_loop)


def refresh_toggle(event=None):
    """Autorefresh"""
    APP.update_interval = -APP.update_interval
    if APP.update_interval > 0:
        toast(f"Refreshing every {APP.update_interval/1000:.2}s")
        APP.after(1000, refresh_loop)
    else:
        toast("Refresh off")


def resize_handler(event=None):
    """Handle Tk resize event"""
    new_size = APP.winfo_geometry().split("+", maxsplit=1)[0]
    if APP.s_geo == new_size:
        return
    APP.w = APP.winfo_width()
    APP.h = APP.winfo_height()
    ERROR_OVERLAY.config(wraplength=APP.w)
    TOAST.config(wraplength=APP.w)
    CANVAS.itemconfig(CANVAS.text, width=APP.w - 16)
    CANVAS.coords(CANVAS.im_bg, 0, 0, APP.w, APP.h)
    # Resize selection?

    bb = CANVAS.bbox(CANVAS.text)
    if bb != CANVAS.bbox(CANVAS.text):
        info_bg_update()

    if APP.fit:
        im_resize()

    scrollbars_set()

    APP.s_geo = new_size


def scroll(event):
    """Scroll"""
    k = event.keysym
    if k == "Left":
        CANVAS.xview_scroll(-1, "units")
    elif k == "Right":
        CANVAS.xview_scroll(1, "units")
        LOG.debug("After scrolling 10 px, xvieww returns: %s", CANVAS.xview())
    if k == "Up":
        CANVAS.yview_scroll(-1, "units")
    elif k == "Down":
        CANVAS.yview_scroll(1, "units")


@log_this
def scroll_toggle(event):
    """Scroll lock"""
    APP.scroll_locked = event.state & 32
    toast(f"Scroll {not APP.scroll_locked}")


def scrollbars_set():
    """Hide/show scrollbars"""
    win_h = APP.winfo_height()
    win_w = APP.winfo_width()
    try:
        x, y, x2, y2 = CANVAS.bbox(CANVAS.image_ref, CANVAS.text)
        can_w = x2 - x
        can_h = y2 - y
        show_v = max(0, y) + can_h > win_h
        # Vertical scrollbar causing horizontal scrollbar.
        show_h = max(0, x) + can_w > win_w - 16 * show_v
        # Horizontal scrollbar causing vertical scrollbar.
        show_v = max(0, y) + can_h > win_h - 16 * show_h
        if show_h:
            can_h += 16
            SCROLLX.place(
                x=0,
                y=1,
                width=win_w,
                relx=0,
                rely=1,
                anchor="sw",
                bordermode="outside",
            )
            SCROLLX.lift()
        else:
            SCROLLX.lower()

        if show_v:
            can_w += 16
            SCROLLY.place(
                x=1,
                y=0,
                height=win_h,
                relx=1,
                rely=0,
                anchor="ne",
                bordermode="outside",
            )
            SCROLLY.lift()
        else:
            SCROLLY.lower()

        if show_h and show_v:
            SCROLLX.place(
                x=0,
                y=1,
                width=win_w - 16,
                relx=0,
                rely=1,
                anchor="sw",
                bordermode="outside",
            )
            SCROLLY.place(
                x=1,
                y=0,
                height=win_h - 16,
                relx=1,
                rely=0,
                anchor="ne",
                bordermode="outside",
            )
            GRIP.lift()
        else:
            GRIP.lower()

        scrollregion = (min(x, 0), min(y, 0), x + can_w, y + can_h)
        CANVAS.config(scrollregion=scrollregion)
        if not APP.scroll_locked and APP.i_path != APP.i_scroll:
            # Scroll to top for comics.
            CANVAS.xview_moveto(0)
            CANVAS.yview_moveto(0)
            APP.i_scroll = APP.i_path
    except TypeError as ex:
        LOG.error("Scrollbar error: %s", ex)


def set_bg(event=None):
    """Background color"""
    APP.i_bg += 1
    if APP.i_bg >= len(BG_COLORS):
        APP.i_bg = 0
    bg = BG_COLORS[APP.i_bg]
    fg = "black" if APP.i_bg == len(BG_COLORS) - 1 else "white"
    APP.config(bg=bg)
    CANVAS.config(bg=bg)
    CANVAS.itemconfig(CANVAS.im_bg, fill=bg)
    ERROR_OVERLAY.config(bg=bg)
    MENU.config(
        bg=bg, fg=fg, bd=0, relief="flat", tearoff=False, activeborderwidth=0
    )  # Can't stop border on Windows!
    style.configure("TScrollbar", troughcolor=bg, background="darkgrey")
    style.map("TScrollbar", background=[("pressed", "!disabled", fg), ("active", fg)])
    style.configure("TSizegrip", background=bg)
    # Dialogs
    APP.option_add("*Background", bg)
    APP.option_add("*Foreground", fg)


@log_this
def set_order(event=None):
    """Order"""
    APP.reverse = False
    if event and event.keysym == "O":
        APP.reverse = True
    else:
        i = SORTS.index(APP.sort) if APP.sort in SORTS else -1
        i = (i + 1) % len(SORTS)
        APP.sort = SORTS[i]
    s = "Sort: " + APP.sort + (" reverse" if APP.reverse else "")
    LOG.info(s)
    toast(s)
    paths_sort(reverse=APP.reverse)  # type:ignore


def set_stats(path):
    """Set stats"""
    stats = os.stat(path)
    APP.info = {
        # "Path": pathlib.Path(path),
        "Size": f"{stats.st_size:,} B",
        "Created": time.strftime(
            TIME_FORMAT,
            time.localtime(
                stats.st_birthtime if hasattr(stats, "st_birthtime") else stats.st_ctime
            ),
        ),
        "Modified": time.strftime(TIME_FORMAT, time.localtime(stats.st_mtime)),
        "Accessed": time.strftime(TIME_FORMAT, time.localtime(stats.st_atime)),
    }


def set_supported_files():
    """Set supported files"""
    exts = Image.registered_extensions()
    exts[".eml"] = "MHTML"
    exts[".mht"] = "MHTML"
    exts[".mhtml"] = "MHTML"
    exts[".svg"] = "SVG"
    exts[".svgz"] = "SVG"
    exts[".tar"] = "TAR"
    exts[".tar.bz2"] = "TAR"
    exts[".tbz2"] = "TAR"
    exts[".tar.gz"] = "TAR"
    exts[".tgz"] = "TAR"
    exts[".tar.xz"] = "TAR"
    exts[".txz"] = "TAR"
    exts[".tar.zst"] = "TAR"
    exts[".tar.zstd"] = "TAR"
    exts[".zip"] = "ZIP"
    added_exts = [
        "EML",
        "MHT",
        "MHTML",
        "SVG",
        "SVGZ",
        "TAR",
        "TAR.BZ2",
        "TAR.GZ",
        "TAR.XZ",
        "TAR.ZST",
        "TAR.ZSTD",
        "TBZ2",
        "TGZ",
        "TXZ",
        "ZIP",
    ]

    APP.SUPPORTED_EXTENSIONS = sorted(
        [k[1:].upper() for k, v in exts.items() if v in Image.OPEN] + added_exts
    )
    type_exts = {}
    for k, v in exts.items():
        type_exts.setdefault(v, []).append(k)

    APP.SUPPORTED_FILES_READ = [
        (
            "All supported files",
            " ".join(
                sorted(list(k for k, v in exts.items() if v in Image.OPEN) + added_exts)
            ),
        ),
        ("All files", "*"),
        (
            "Archives",
            ".eml .mht .mhtml .tar .tar.bz2 .tbz2 .tar.gz .tgz .tar.xz .txz .tar.zst .tar.zstd .zip",
        ),
        *sorted(
            (k, v) for k, v in type_exts.items() if k in Image.OPEN or k in added_exts
        ),
    ]
    APP.SUPPORTED_FILES_WRITE = [
        (
            "All supported files",
            " ".join(sorted(list(k for k, v in exts.items() if v in Image.SAVE))),
        ),
        *sorted((k, v) for k, v in type_exts.items() if k in Image.SAVE),
    ]
    LOG.debug(
        "Opens:\n%s",
        ", ".join(APP.SUPPORTED_EXTENSIONS),
    )
    LOG.debug(
        "Saves:\n%s",
        ", ".join(sorted(k[1:].upper() for k, v in exts.items() if v in Image.SAVE)),
    )
    LOG.debug(
        "Saves all frames:\n%s",
        ", ".join(
            sorted(k[1:].upper() for k, v in exts.items() if v in Image.SAVE_ALL)
        ),
    )


def quality_set(event=None):
    """Resize quality"""
    i = RESIZE_QUALITY.index(APP.quality)
    i += -1 if event and event.keysym == "Q" else 1
    if i >= len(RESIZE_QUALITY):
        i = 0
    if i < 0:
        i = len(RESIZE_QUALITY) - 1
    APP.quality = RESIZE_QUALITY[i]
    toast(f"Quality: {Image.Resampling(APP.quality).name}")
    im_resize()


@log_this
def set_verbosity(event=None):
    """Verbosity"""
    delta = 10 if event and event.keysym == "V" else -10
    APP.verbosity += delta
    if APP.verbosity < logging.DEBUG:
        APP.verbosity = logging.CRITICAL
    if APP.verbosity > logging.CRITICAL:
        APP.verbosity = logging.DEBUG

    # Includes 3rd-party modules
    # logging.getLogger().setLevel(APP.verbosity)
    LOG.setLevel(APP.verbosity)
    logging.getLogger("metadata").setLevel(APP.verbosity)
    s = "Log level %s" % logging.getLevelName(LOG.getEffectiveLevel())
    toast(s)
    print(s)


def slideshow_run(event=None):
    """Run slideshow"""
    if APP.b_slideshow:
        try:
            browse(delta=1)
        except (Image.UnidentifiedImageError, PermissionError):
            pass
        APP.after(APP.slideshow_pause, slideshow_run)


def slideshow_toggle(event=None):
    """Slideshow"""
    APP.b_slideshow = not APP.b_slideshow
    if APP.b_slideshow:
        toast("Starting slideshow")
        APP.after(APP.slideshow_pause, slideshow_run)
    else:
        toast("Stopping slideshow")


def toast(msg: str, ms: int = 2000, fg="#00FF00"):
    """Temporarily show a status message"""
    LOG.info("Toast: %s", msg)
    TOAST.config(text=msg, fg=fg)
    TOAST.lift()
    if hasattr(APP, "toast_timer"):
        APP.after_cancel(APP.toast_timer)
    APP.toast_timer = APP.after(ms, TOAST.lower)


@log_this
def transpose_set(event=None):
    """Transpose"""
    APP.transpose_type += -1 if event and event.keysym == "T" else 1
    if APP.transpose_type >= len(Transpose):
        APP.transpose_type = -1
    if APP.transpose_type < -1:
        APP.transpose_type = len(Transpose) - 1

    if APP.transpose_type >= 0:
        toast(f"Transpose: {Transpose(APP.transpose_type).name}")
    else:
        toast("Transpose: Normal")
    im_resize()


@log_this
def fit_handler(event=None):
    """Resize"""
    APP.fit = (APP.fit + 1) % len(Fits)
    toast("Resize " + Fits(APP.fit).name)
    im_resize()


def fullscreen_toggle(event=None):
    """Fullscreen"""
    if not APP.overrideredirect():
        APP.old_geometry = APP.geometry()
        APP.old_state = APP.state()
        LOG.debug("Old widow geometry: %s", APP.old_geometry)
        APP.overrideredirect(True)
        APP.state("zoomed")
    else:
        APP.overrideredirect(False)
        APP.state(APP.old_state)
        if APP.state() == "normal":
            new_geometry = (
                "300x200+300+200"
                if APP.old_geometry.startswith("1x1")  # Window wasn't visible yet.
                else APP.old_geometry
            )
            LOG.debug("Restoring geometry: %s", new_geometry)
            APP.geometry(new_geometry)
    resize_handler()


def str2float(s: str) -> float:
    """Python lacks a parse function for "13px"."""
    m = re.match("\\d+", s)
    return float(m.group(0)) if m else 0.0


def zoom(event):
    """Zoom"""
    k = event.keysym
    if event.num == 5 or event.delta > 0:
        k = "plus"
    if event.num == 4 or event.delta < 0:
        k = "minus"
    if k in ("plus", "equal"):
        APP.im_scale *= 1.1
    elif k == "minus":
        APP.im_scale *= 0.9
    else:
        APP.im_scale = 1
    APP.im_scale = max(SCALE_MIN, min(APP.im_scale, SCALE_MAX))
    im_resize()


@log_this
def zoom_text(event):
    """Zoom text"""
    k = event.keysym
    if event.num == 5 or event.delta > 0:
        k = "plus"
    if event.num == 4 or event.delta < 0:
        k = "minus"
    if k in ("plus", "equal"):
        APP.f_text_scale *= 1.1
    elif k == "minus":
        APP.f_text_scale *= 0.9
    else:
        APP.f_text_scale = 1
    APP.f_text_scale = max(0.1, min(APP.f_text_scale, 20))
    new_font_size = int(FONT_SIZE * APP.f_text_scale)
    new_font_size = max(1, min(new_font_size, 200))
    LOG.info("Text scale: %s New font size: %s", APP.f_text_scale, new_font_size)

    ERROR_OVERLAY.config(font=("Consolas", new_font_size))
    TOAST.config(font=("Consolas", new_font_size * 2))
    CANVAS.itemconfig(CANVAS.text, font=("Consolas", new_font_size))
    info_bg_update()


APP = TkinterDnD.Tk()  # notice - use this instead of tk.Tk()
APP.withdraw()
APP.drop_target_register(DND_FILES)
APP.dnd_bind("<<Drop>>", drop_handler)
APP.showing = ""
APP.title(TITLE)
APP.iconphoto(
    True,
    tkinter.PhotoImage(
        data="R0lGODlhgACAAHAAACH5BAEAAAIALAAAAACAAIAAgQAAAP///wAAAAAAAAL/lI+py+0Po5y02ouz3rz7D4biSJbmiabqyrbuC8fyTNf2jef6zvf+DwwKh8Si8YhMKpfMpvMJAkgB0NX0is1eqxyt9+vlTsDkMlbMMKvXUrSADYdD43T5so63G/PXgP8PyDdFlAdoeIiYF0SH2Oh4SOcT90hZ+Re3A2e5aalXM8kZCBAqyvapyVkWihnDuIlaGelSRxrAFitr5Vp7S1mnC1rr1/v4i4InXGrma0yy7JVsSNwIbTaiOqwVrbzsCJ0NFoJtq719CZtYTh7uMb6OZX4+Dan+HtZFJl2/vUufpc8ugzt7faitCubvHzctAsGkU2gwFcKEBQHes+DwITxq/1Je0eII0SLDChk1VvTnsZ/IKd6+kPxSbJ8yXB9Nsmx5EUJJkBtNxkTG86TNLTphMgu5clRSlfJ64hzZIN9Rp0sFyQRHdSjRNEanCl1o9RvFm17PcBVbtmPQsFexfl27FcHOtEq1siU7Vm0nl3K77kUK9i7epQdz+v2btangxG4H08zSt+3Tt4oX681bNyVkA4cRU268+Cdj0WbRFh5tGbVkupxXk3YcmO1k2J4HvXE9+zLmsK91S9xs+jfg2Hx6+9ZMtDNy2pWtGk/G9zZuu8YL5T7+2Gzr6Vrp1oSb+bR26dyrekdHnVf07eWbY6+qJvvn620UzK3NnPj99OLHJ7TYX1149HEH4IAOSCXccAMKOCApZDxQYIPxJDiagUUFdx6DE+72Hnj1RRChXR1uiOBycYGoXIAakhgihxe0CN+Iwgwkn38SlIhfherBqF9DPIKmYH/tlbEBjSrO52GQIn6ogZELKglkikkyWSSOGaa24pJURGHllYIJaWMH3ZhoGZhhfuDkk9ZRuNkJY5K5JpwnmvCmnPPkeGYJ8e2Inp22tbAGP1Li2eYLgW5ozhqn7Imog4ph3nBno1PmKcNEkka5ng5MxZOLJEBBhwchvGn56B5YCsLEqc00oWqpXLSakxvsnSorhJbVilGouIow566+/gpssMIOS2yxxh6LbLLKLstss84+C2200k5LbbXWXotttgIUAAA7"
    ),
)
APP_w, APP_h = int(APP.winfo_screenwidth() * 0.75), int(APP.winfo_screenheight() * 0.75)
APP.old_geometry = f"{APP_w}x{APP_h}+{int(APP_w * 0.125)}+{int(APP_h * 0.125)}"
APP.geometry(APP.old_geometry)

TOAST = tkinter.Label(
    APP,
    text="status",
    font=("Consolas", FONT_SIZE * 2),
    fg="#00FF00",
    bg="black",
    wraplength=APP_w,
    anchor="center",
    justify="center",
)
TOAST.place(x=0, y=0)

CANVAS = tkinter.Canvas(bg="black", borderwidth=0, highlightthickness=0, relief="flat")
# Opening the context menu only triggers drag_end.
CANVAS.dragx = 0  # type: ignore
CANVAS.dragy = 0  # type: ignore
CANVAS.lines = []  # type: ignore
CANVAS.place(x=0, y=0, relwidth=1, relheight=1)
CANVAS.text_bg = CANVAS.create_image(0, 0, anchor="nw")  # type: ignore
CANVAS.text = CANVAS.create_text(  # type: ignore
    1,  # If 0, bbox starts at -1.
    0,
    anchor="nw",
    text="status",
    fill="#ff0",
    font=("Consolas", FONT_SIZE),
    width=APP_w,
)
CANVAS.im_bg = CANVAS.create_rectangle(0, 0, APP_w, APP_h, fill="black", width=0)  # type: ignore
CANVAS.image_ref = CANVAS.create_image(APP_w // 2, APP_h // 2, anchor="center")  # type: ignore
style = ttk.Style()
# LOG.debug("Theme names %s", style.theme_names())
style.theme_use("classic")
APP.update()
SCROLLX = ttk.Scrollbar(APP, orient="horizontal", command=CANVAS.xview)
SCROLLY = ttk.Scrollbar(APP, command=CANVAS.yview)
GRIP = ttk.Sizegrip(APP)
GRIP.pack(side="bottom", anchor="se")

CANVAS.config(
    xscrollcommand=SCROLLX.set,
    xscrollincrement=SCROLL_SPEED,
    yscrollcommand=SCROLLY.set,
    yscrollincrement=SCROLL_SPEED,
)
ERROR_OVERLAY = tkinter.Label(
    APP,
    compound="center",
    fg="red",
    font=("Consolas", FONT_SIZE),
    width=APP_w,
    height=APP_h,
    wraplength=APP_w,
)
ERROR_OVERLAY.place(x=0, y=0, relwidth=1, relheight=1)

MENU = tkinter.Menu(APP, tearoff=0)

BINDS = [
    (path_open, "p P F2"),
    (path_save, "s S F12"),
    (clipboard_copy, "Control-c Control-C Control-Insert"),
    (clipboard_paste, "Control-v Control-V Shift-Insert"),
    (delete_file, "d D Delete"),
    "--",
    (browse_search, "F3"),
    (filter_toggle, "n N"),
    (paths_update, "u U F5"),
    (refresh_toggle, "Control-u Control-U"),
    (set_order, "o O"),
    (slideshow_toggle, "b B Pause"),
    (browse_archive_toggle, "z Z"),
    (animation_toggle, "a A"),
    (browse_frame, "comma period"),
    (browse_mouse, "MouseWheel"),
    (browse_next, "Right Down Next space Button-5"),
    (browse_prev, "Left Up Prior Button-4"),
    (browse_home, "Key-1 Home Alt-Left"),
    (browse_end, "End Alt-Right"),
    (browse_index, "g G F4"),
    (browse_percentage, "Key"),
    (browse_random, "x X"),
    (paths_down, "Return"),
    (paths_up, "BackSpace"),
    "--",
    (fullscreen_toggle, "f F F11 Alt-Return"),
    (close, "Escape"),
    (zoom, "0 equal plus minus Control-MouseWheel"),
    (zoom_text, "Alt-equal Alt-plus Alt-minus Alt-MouseWheel"),
    (drag, "B1-Motion"),
    (scroll, "Control-Left Control-Right Control-Up Control-Down"),
    (scroll_toggle, "Scroll_Lock"),
    (select, "B2-Motion Control-a Control-A"),
    (drag_begin, "ButtonPress"),
    (drag_end, "ButtonRelease"),
    (fit_handler, "r R"),
    (resize_handler, "Configure"),
    (quality_set, "q Q"),
    (set_bg, "c C"),
    (transpose_set, "t T"),
    (lines_toggle, "l L"),
    (set_verbosity, "v V"),
    (menu_show, "Button-3 F10"),  # Or rather tk_popup in Ubuntu?
    (help_toggle, "h H F1"),
    (info_toggle, "i I"),
]


def main():
    """Main function"""
    APP.b_animate = True
    APP.b_lines = False
    APP.b_slideshow = False
    APP.i_bg = -1
    APP.i_path = 0
    APP.i_scroll = -1
    APP.i_zip = 0
    APP.im_scale = 1.0
    APP.info = {}
    APP.f_text_scale = 1.0
    APP.filter_names = True
    APP.reverse = False
    APP.s_geo = ""
    APP.scroll_locked = True
    APP.transpose_type = -1
    APP.update_interval = -4000

    parser = argparse.ArgumentParser(
        prog="tk_image_viewer",
        description="An image viewer that supports both arrow keys and "
        + "WebP with foreign characters in long paths.",
    )
    parser.add_argument("path", default=os.getcwd(), nargs="?")
    parser.add_argument(
        "-b",
        "--browse",
        metavar="ms",
        nargs="?",
        help="browse to next image every N ms (default 4000)",
        const=4000,
        type=int,
    )
    parser.add_argument(
        "-f",
        "--fullscreen",
        action="store_true",
        help="run fullscreen",
    )
    parser.add_argument(
        "-g",
        "--geometry",
        metavar="WxH+X+Y",
        help="set window geometry, eg -g +0+-999",
        type=str,
    )
    parser.add_argument("-m", "--maximize", action="store_true", help="maximize window")
    parser.add_argument(
        "-n", "--nofilter", action="store_true", help="try all file names"
    )
    parser.add_argument(
        "-o",
        "--order",
        help="sort order. [NATURAL|string|random|mtime|ctime|size]",
        default="natural",
        type=str,
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
        "--resize",
        metavar="N",
        nargs="?",
        help="resize image to fit window (0-3: none, all, big, small. default 1)",
        const=1,
        type=lambda s: int(s) if 0 <= int(s) <= 3 else 0,
    )
    parser.add_argument(
        "-t",
        "--transpose",
        metavar="N",
        help=f"transpose 0-{len(Transpose)-1} {', '.join(x.name.lower() for x in Transpose)}",
        default=-1,
        type=int,
    )
    parser.add_argument(
        "-u",
        "--update",
        metavar="ms",
        nargs="?",
        help="update interval (default 4000)",
        const=4000,
        type=int,
    )
    parser.add_argument(
        "-v", "--verbose", help="set log level", action="count", default=0
    )
    parser.add_argument("-z", "--archives", help="browse archives", action="store_true")

    parsed_args = argparse.Namespace()
    try:
        with open(CONFIG_FILE, "r", encoding="utf8") as fp:
            parser.parse_args(fp.read().split(), parsed_args)
    except IOError as ex:
        LOG.debug(ex)

    args = parser.parse_args(namespace=parsed_args)

    APP.verbosity = logging.CRITICAL
    if args.verbose:
        APP.verbosity = VERBOSITY_LEVELS[
            min(len(VERBOSITY_LEVELS) - 1, 1 + args.verbose)
        ]
    set_verbosity()

    LOG.debug("Args: %s", args)
    APP.paths: list[pathlib.Path] = []

    set_supported_files()

    APP.fit = args.resize or 0
    APP.quality = RESIZE_QUALITY[args.quality]
    APP.sort = args.order if args.order else "natural"
    APP.transpose_type = args.transpose

    # Needs visible window so wait for mainloop.
    APP.after(10, paths_update, None, args.path)
    APP.after(20, resize_handler)

    if args.fullscreen:
        APP.after(100, fullscreen_toggle)

    if args.geometry:
        APP.old_geometry = args.geometry
        APP.geometry(APP.old_geometry)
        APP.update()

    if args.maximize:
        APP.state("zoomed")

    if args.nofilter:
        APP.filter_names = False

    if args.update:
        APP.update_interval = args.update
        APP.after(1000, refresh_loop)

    if args.browse:
        APP.slideshow_pause = args.browse
        slideshow_toggle()
    else:
        APP.slideshow_pause = 4000

    APP.browse_archives = args.archives

    APP.protocol("WM_DELETE_WINDOW", close)
    menu_init()
    bind()
    set_bg()
    APP.deiconify()
    APP.mainloop()


if __name__ == "__main__":
    main()
