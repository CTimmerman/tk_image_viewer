# pylint: disable=consider-using-f-string, global-statement, line-too-long, multiple-imports, too-many-boolean-expressions, too-many-branches, too-many-lines, too-many-locals, too-many-nested-blocks,too-many-statements, unused-argument, unused-import, wrong-import-position
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
"""
import base64, enum, functools, gzip, logging, os, pathlib, random, re, subprocess, time, tkinter, zipfile  # noqa: E401
from io import BytesIO
from tkinter import filedialog, messagebox, ttk

import pillow_avif  # type: ignore  # noqa: F401  # pylint: disable=E0401
import pillow_jxl  # noqa: F401
import pyperclip  # type: ignore
import yaml
from PIL import ExifTags, Image, ImageCms, ImageGrab, ImageTk, IptcImagePlugin, TiffTags
from PIL.Image import Transpose
from pillow_heif import register_heif_opener  # type: ignore
from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore

os.environ["PYGAME_HIDE_SUPPORT_PROMPT"] = "hide"
import pygame  # noqa: E402

from psd_info import psd_resource_ids  # noqa: E402


class Fits(enum.IntEnum):
    """Types of window fitting."""

    NONE = 0
    ALL = 1
    BIG = 2
    SMALL = 3


BG_COLORS = ["black", "gray10", "gray50", "white"]
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
TITLE = __doc__.split("\n", 1)[0]
VERBOSITY_LEVELS = [
    logging.CRITICAL,
    logging.ERROR,
    logging.WARN,
    logging.INFO,
    logging.DEBUG,
]

# Add a handler to stream to sys.stderr warnings from all modules.
logging.basicConfig(format="%(levelname)s: %(message)s")
# Add a logging namespace.
LOG = logging.getLogger(TITLE)

register_heif_opener()


def log_this(func):
    """Decorator to log function calls."""

    @functools.wraps(func)  # Keep signature.
    def inner(*args, **kwargs):
        LOG.debug("Calling %s with %s, %s", func.__name__, args, kwargs)
        return func(*args, **kwargs)

    return inner


def animation_toggle(event=None):
    """Toggle animation."""
    APP.b_animate = not APP.b_animate
    if APP.b_animate:
        toast("Starting animation.")
        im_resize(APP.b_animate)
    else:
        s = "Stopping animation." + (
            f" Frame {1 + (1 + APP.im_frame) % APP.im.n_frames}/{APP.im.n_frames}"
            if hasattr(APP.im, "n_frames")
            else ""
        )
        LOG.info(s)
        toast(s)


def bind():
    """Binds input events to functions."""
    APP.bind_all("<Key>", debug_keys)
    for b in BINDS:
        func = b[0]
        for event in b[1].split(" "):
            APP.bind(f"<{event}>", func)


def browse_end(event=None):
    """Last."""
    browse(pos=APP.i_path - 1)


def browse_home(event=None):
    """First."""
    browse(pos=0)


def browse_mouse(event):
    """Previous/Next."""
    browse(delta=-1 if event.delta > 0 else 1)


def browse_percentage(event):
    """Shift+1-9 to go to 10 to 90 percent of the list."""
    if hasattr(event, "state") and event.state == 1 and event.keycode in range(49, 58):
        ni = int(len(APP.paths) / 10 * (event.keycode - 48))
        browse(pos=ni)


def browse_next(event=None):
    """Next."""
    browse(delta=1)


def browse_prev(event=None):
    """Previous."""
    browse(delta=-1)


def browse_random(event=None):
    """Go to random index."""
    browse(pos=random.randint(0, len(APP.paths) - 1))


@log_this
def browse(event=None, delta=0, pos=None):
    """Browse list of paths."""
    if pos is not None:
        new_index = pos
    else:
        new_index = (APP.i_zip if "Names" in APP.info else APP.i_path) + delta

    if "Names" in APP.info:
        if new_index < 0:
            new_index = APP.i_path - 1
        elif new_index >= len(APP.info["Names"]):
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


def browse_frame(event=None):
    """Browse animation frames."""
    if not hasattr(APP.im, "n_frames"):
        toast("No frames.")
        return
    n = APP.im.n_frames - 1
    k = event.keysym
    if k == "comma":
        APP.im_frame -= 1
        if APP.im_frame < 0:
            APP.im_frame = n
    else:
        APP.im_frame += 1
        if APP.im_frame > n:
            APP.im_frame = 0

    APP.im.seek(APP.im_frame)
    im_resize()
    toast(f"Frame {1 + APP.im_frame}/{1 + n}", 1000)


def clipboard_copy(event=None):
    """Copy info to clipboard."""
    pyperclip.copy(CANVAS.itemcget(CANVAS.text, "text"))
    toast("Copied info.")


def clipboard_paste(event=None):
    """Paste image from clipboard."""
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
        APP.paths = [pathlib.Path(s) for s in im]
        LOG.debug("Set paths to %s", APP.paths)
        APP.i_path = 0
        im_load()
        return
    APP.im = im
    APP.info = {"Pasted": time.ctime()}
    APP.i_path = 0
    APP.paths = ["pasted"]
    im_resize(APP.im)


@log_this
def close(event=None):
    """Close fullscreen or app."""
    if APP.overrideredirect():
        fullscreen_toggle()
    else:
        APP.quit()


@log_this
def debug_keys(event=None):
    """Show all keys."""


def delete_file(event=None):
    """Delete file. Bypasses Trash."""
    path = APP.paths[APP.i_path]
    msg = f"Delete? {path}"
    LOG.warning(msg)
    answer = messagebox.showwarning(
        "Delete File", f"Permanently delete {path}?", type=messagebox.YESNO
    )
    if answer == "yes":
        LOG.warning("Deleting %s", path)
        os.remove(path)
        paths_update()


@log_this
def drag_begin(event):
    """Keep drag begin pos for delta move."""
    if event.widget != CANVAS:
        return
    CANVAS.dragx = CANVAS.canvasx(event.x)
    CANVAS.dragy = CANVAS.canvasy(event.y)
    CANVAS.config(cursor="fleur" if event.num == 1 else "tcross")


@log_this
def drag_end(event):
    """End drag."""
    if event.widget != CANVAS:
        return
    CANVAS.config(cursor="")
    if (
        CANVAS.canvasx(event.x) == CANVAS.dragx
        and CANVAS.canvasy(event.y) == CANVAS.dragy
    ):
        lines_toggle(off=True)


def drag(event):
    """Drag image."""
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
        CANVAS.xview_scroll(round(-dx / SCROLL_SPEED), "units")
    if new_y == 0:
        CANVAS.yview_scroll(round(-dy / SCROLL_SPEED), "units")

    dx, dy = new_x - x, new_y - y
    CANVAS.move(CANVAS.image_ref, dx, dy)
    scrollbars_set()
    CANVAS.dragx, CANVAS.dragy = evx, evy


def select(event):
    """Select area."""
    if event.widget != CANVAS:
        return
    lines_toggle(on=True)
    x = CANVAS.dragx
    y = CANVAS.dragy
    x2 = CANVAS.canvasx(event.x)
    y2 = CANVAS.canvasy(event.y)
    CANVAS.coords(CANVAS.lines[0], x, y, x2, y, x, y2, x2, y2)
    CANVAS.coords(CANVAS.lines[1], x, y2, x, y, x2, y2, x2, y)


@log_this
def drop_handler(event):
    """Handles dropped files."""
    LOG.debug("Dropped %r", event.data)
    APP.paths = [
        pathlib.Path(line.strip('"'))
        for line in re.findall("{(.+?)}" if "{" in event.data else "[^ ]+", event.data)
    ]  # Windows 11.
    if isinstance(APP.paths, list):
        LOG.debug("Set paths to %s", APP.paths)
        APP.i_path = 0
        im_load()


def error_show(msg: str):
    """Show error."""
    APP.title(msg + " - " + TITLE)
    LOG.error(msg)
    ERROR_OVERLAY.config(text=msg)
    ERROR_OVERLAY.lift()
    info_set(msg)  # To copy.
    APP.i_path_old = -1  # To refresh image info.


def help_toggle(event=None):
    """Toggle help."""
    if APP.show_info and CANVAS.itemcget(CANVAS.text, "text").startswith("C - Set"):
        info_hide()
    else:
        lines = []
        for fun, keys in BINDS:
            if fun in (drag_begin, drag_end, resize_handler):
                continue
            lines.append(
                re.sub(
                    "((^|[+])[a-z])",
                    lambda m: m.group(1).upper(),
                    re.sub(
                        "([QTU])\\b",
                        "Shift+\\1",
                        keys.replace("Control-", "Ctrl+")
                        .replace("Alt-", "Alt+")
                        .replace("Shift-", "Shift+")
                        .replace(" Prior ", " PageUp ")
                        .replace(" Next ", " PageDown "),
                    ),
                    0,
                    re.MULTILINE,
                )
                + " - "
                + fun.__doc__.replace("...", "")
            )
        msg = "\n".join(lines)
        info_set(msg)
        info_show()
        LOG.debug(msg)


def info_set(msg: str):
    """Change info text."""
    CANVAS.itemconfig(CANVAS.text, text=msg)  # type: ignore
    info_bg_update()


def info_bg_update():
    """Update info overlay."""
    x1, y1, x2, y2 = CANVAS.bbox(CANVAS.text)
    CANVAS.text_bg_tkim = ImageTk.PhotoImage(  # type: ignore
        Image.new("RGBA", (x2 - x1, y2 - y1), "#000a")
    )
    CANVAS.itemconfig(CANVAS.text_bg, image=CANVAS.text_bg_tkim)  # type: ignore
    CANVAS.coords(CANVAS.im_bg, x1, y1, x2, y2)


def lines_toggle(event=None, on=None, off=None):
    """Toggle line overlay."""
    APP.b_lines = True if on else False if off else not APP.b_lines  # NOSONAR
    if not APP.b_lines and CANVAS.lines:
        for line in CANVAS.lines:
            CANVAS.delete(line)
        CANVAS.lines = []
    if APP.b_lines and not CANVAS.lines:
        w = APP.winfo_width() - 1
        h = APP.winfo_height() - 1
        CANVAS.lines.append(CANVAS.create_line(0, 0, w, 0, 0, h, w, h, fill="#f00"))  # type: ignore
        CANVAS.lines.append(CANVAS.create_line(0, h, 0, 0, w, h, w, 0, fill="#f00"))  # type: ignore


def load_mhtml(path):
    """Load EML/MHT/MHTML."""
    with open(path, "r", encoding="utf8") as f:
        mhtml = f.read()
    boundary = re.search('boundary="(.+)"', mhtml).group(1)
    parts = mhtml.split(boundary)[1:-1]
    APP.info["Names"] = []
    new_parts = []
    for p in parts:
        meta, data = p.split("\n\n", maxsplit=1)
        m = meta.lower()
        if "\ncontent-transfer-encoding: base64" not in m:
            continue
        if "\ncontent-type:" in m and "\ncontent-type: image" not in m:
            continue
        name = sorted(meta.strip().split("\n"))[0].split("/")[-1]
        APP.info["Names"].append(name)
        new_parts.append(data)
    LOG.debug("%s", f"Getting part {APP.i_zip}/{len(new_parts)} of {len(parts)}.")
    data = new_parts[APP.i_zip]
    try:
        im_file = BytesIO(base64.standard_b64decode(data.rstrip()))
        APP.im = Image.open(im_file)
    except ValueError as ex:
        LOG.error("Failed to split mhtml: %s", ex)
        LOG.error("DATA %r", data[:180])
        im_file.seek(0)
        LOG.error("DECODED %s", im_file.read()[:80])


def load_svg(fpath):
    """Load an SVG file."""
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


def load_zip(path):
    """Load a zip file."""
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        APP.info["Names"] = names
        LOG.debug("Loading name index %s", APP.i_zip)
        # pylint: disable=consider-using-with
        APP.im = Image.open(zf.open(names[APP.i_zip]))


def im_load(path=None):
    """Load image."""
    if not path and APP.paths:
        path = APP.paths[APP.i_path]
    else:
        return

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
            else:
                APP.im = Image.open(path)
        LOG.debug("Cached %s PIL_IMAGE", APP.im.size)
        APP.im_frame = 0
        if hasattr(APP.im, "n_frames"):
            APP.info["Frames"] = APP.im.n_frames
        APP.info.update(**APP.im.info)
        for k, v in APP.info.items():
            LOG.debug(
                "%s: %s",
                k,
                str(v)[:80] + "..." if len(str(v)) > 80 else v,
            )
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
        err_msg = f"im_load {type(ex).__name__}: {ex}"
        APP.im = None
        msg = f"{msg} {err_msg} {path}"
        error_show(msg)
        raise


def get_fit_ratio(im_w, im_h):
    """Get fit ratio."""
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
    """Fit image to window."""
    w, h = im.size
    ratio = get_fit_ratio(w, h)
    if ratio != 1.0:  # NOSONAR
        im = im.resize((int(w * ratio), int(h * ratio)), APP.quality)
    return im


def im_scale(im):
    """Scale image."""
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


def im_resize(loop=False):
    """Resize image."""
    if not (hasattr(APP, "im") and APP.im):
        return

    im = APP.im.copy()

    if APP.fit:
        im = im_fit(APP.im)

    if APP.im_scale != 1:
        im = im_scale(APP.im)

    if APP.transpose_type != -1:
        LOG.debug("Transposing %s", Transpose(APP.transpose_type))
        im = im.transpose(APP.transpose_type)

    im_show(im)

    if loop and hasattr(APP.im, "n_frames") and APP.im.n_frames > 1:
        APP.im_frame = (APP.im_frame + 1) % APP.im.n_frames
        try:
            APP.im.seek(APP.im_frame)
        except EOFError as ex:
            LOG.error("IMAGE EOF. %s", ex)
        duration = int(APP.info["duration"] or 100) if "duration" in APP.info else 100
        if hasattr(APP, "animation"):
            APP.after_cancel(APP.animation)
        APP.animation = APP.after(duration, im_resize, APP.b_animate)


def im_show(im):
    """Show PIL image in Tk image widget."""
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

        # canvas.move(canvas.image_ref, 10, 0)
        ERROR_OVERLAY.lower()
    except MemoryError as ex:
        LOG.error("Out of memory. Scaling down. %s", ex)
        APP.im_scale = max(SCALE_MIN, min(APP.im_scale * 0.9, SCALE_MAX))
        return

    zip_info = (
        f" {APP.i_zip + 1}/{len(APP.info['Names'])} {APP.info['Names'][APP.i_zip]}"
        if "Names" in APP.info
        else ""
    )
    msg = (
        f"{APP.i_path+1}/{len(APP.paths)}{zip_info} {'%sx%s' % APP.im.size}"
        f" @ {'%sx%s' % im.size} {APP.paths[APP.i_path]}"
    )
    APP.title(msg + " - " + TITLE)
    if APP.show_info and (
        not hasattr(APP, "i_path_old")
        or APP.i_path != APP.i_path_old
        or not hasattr(APP, "i_path_old")
        or APP.i_zip != APP.i_zip_old
    ):
        APP.i_path_old = APP.i_path
        APP.i_zip_old = APP.i_zip
        info_set(msg + info_get())
    scrollbars_set()


def info_decode(b: bytes, encoding: str) -> str:
    """Decodes a sequence of bytes, as stated by the method signature."""
    if not isinstance(b, bytes):
        return str(b)
    LOG.debug("BYTES! %s", str(b[:40]))
    if b.startswith(b"ASCII\0\0\0"):
        return b[8:].decode("ascii")
    if b.startswith(b"UNICODE\0"):
        b = b[8:]
        for enc in (
            "utf-16-be",  # Works despite EXIF byte order being LE.
            "utf-16-le",  # Turns utf-16-be text Chinese.
            encoding,
            "utf8",  # Leaves \0 of utf-16-be, which print() leaves out! XXX
        ):
            try:
                LOG.debug("info_decode %s", enc)
                return b.decode(enc)
            except UnicodeDecodeError:
                pass
    return re.sub("[^\x20-\x7F]+", " ", b.decode("ansi"))


def info_get() -> str:
    """Get image info."""
    msg = ""
    for k, v in APP.info.items():
        # jfif attribute is just hex version in decimal.
        if k in (
            "dpi",
            "exif",
            "icc_profile",
            "jfif",
            "Names",
            "photoshop",
            "transparency",
            "XML:com.adobe.xmp",
        ):
            continue

        if k == "comment":
            try:
                v = v.decode("utf8")
            except UnicodeDecodeError:
                v = v.decode("utf_16_be")
        elif k == "jfif_unit":
            v = {0: "none", 1: "inch", 2: "cm"}.get(v, v)
        elif k == "jfif_version":
            v = f"{v[0]}.0{v[1]}"
        elif k == "loop":
            v = {0: "infinite"}.get(v, v)
        # Image File Directories (IFD)
        elif k == "tag_v2":
            v = {TiffTags.TAGS_V2[k2]: v2 for k2, v2 in v}
            LOG.debug("tag_v2: %s", v)
        # PNG parameters
        msg += f"\n{k}: {v}"
        # PNG transparency
        # msg += f"\n{k}: {(str(v)[:80] + '...') if len(str(v)) > 80 else v}"
    if not APP.im:
        return msg.replace("\0", "\\0")

    CANVAS.config(cursor="watch")  # Invisible on Windows 11?! XXX
    msg += f"\nFormat: {APP.im.format}"
    try:
        msg += f"\nMIME type: {APP.im.get_format_mimetype()}"  # type: ignore
    except AttributeError:
        pass
    try:
        msg += f"\nBit Depth: {APP.im.bits}"
    except AttributeError:
        pass
    pixels = APP.im.width * APP.im.height
    msg += (
        f"\nColor Type: {APP.im.mode}"
        + f"\nColors: {len(APP.im.getcolors(pixels)):,}"
        + f"\nPixels: {pixels:,}"
    )
    for fun in (info_exif, info_icc, info_iptc, info_xmp, info_psd, info_exiftool):
        s = fun()
        if s:
            msg += "\n\n" + s

    CANVAS.config(cursor="")
    return msg.replace("\0", "\\0")


def info_exif() -> str:
    """Return Exchangeable Image File (EXIF) info."""
    # Workaround from https://github.com/python-pillow/Pillow/issues/5863
    if not hasattr(APP.im, "_getexif"):
        return ""

    exif = APP.im._getexif()  # type: ignore  # pylint: disable=protected-access
    if not exif:
        return ""
    encoding = "utf_16_be" if b"MM" in APP.info["exif"][:8] else "utf_16_le"
    LOG.debug("Encoding: %s", encoding)
    s = f"EXIF: {encoding[-2:].upper()}"
    for k, v in exif.items():
        if k not in ExifTags.TAGS:
            s += f"\nUnknown EXIF tag {k}: {v}"
            continue
        key_name = ExifTags.TAGS[k]
        if key_name == "ColorSpace":
            v = {1: "sRGB", 65535: "uncalibrated"}.get(v, v)
        elif key_name == "ComponentsConfiguration":
            try:
                v = "".join(("-", "Y", "Cb", "Cr", "R", "G", "B")[B] for B in v)
            except IndexError:
                pass
        elif key_name == "Orientation":
            v = (
                "",
                "normal",
                "flip left right",
                "rotate 180",
                "flip top bottom",
                "transpose",
                "rotate 90",
                "transverse",
                "rotate 270",
            )[v]
        elif key_name == "ResolutionUnit":
            v = {2: "inch", 3: "cm"}.get(v, v)
        elif key_name == "SceneCaptureType":
            v = {0: "standard", 1: "landscape", 2: "portrait", 3: "night scene"}.get(
                v, v
            )
        elif key_name == "YCbCrPositioning":
            v = {
                1: "centered",
                2: "co-sited",
            }.get(v, v)
        else:
            v = info_decode(v, encoding)

        s += f"\n{key_name}: {v}"

    # Image File Directory (IFD)
    # exif = IMAGE.getexif()  # type: ignore
    # for k in ExifTags.IFD:
    #     try:
    #         v = exif.get_ifd(k)
    #         if v:
    #             s += f"\nIFD tag {k}: {ExifTags.IFD(k).name}: {v}"
    #     except KeyError:
    #         log.debug("IFD not found. %s", k)
    return s.strip()


def info_exiftool() -> str:
    """Uses exiftool on path."""
    s = ""
    try:
        output = subprocess.run(
            [
                "exiftool",
                "-duplicates",
                "-groupHeadings",
                "-unknown2",
                APP.paths[APP.i_path],
            ],
            capture_output=True,
            check=False,
            text=False,
        )  # text=False to avoid dead thread with uncatchable UnicodeDecodeError: 'charmap' codec can't decode byte 0x8f in position 1749: character maps to <undefined> like https://github.com/smarnach/pyexiftool/issues/20
        # Output for D:\\art\\__original_drawn_by_pink_ocean__e48c8d8c99313c1f4a86f35f8795c44b.jpg is not utf8, shift-jis, euc_jp, ISO-2022-JP, utf-16-le, or utf-16-be! Not latin1 either but that decodes.
        s += (
            output.stdout
            and output.stdout.decode("ansi", errors="replace").replace("\r", "")
            or ""
        ) + output.stderr.decode("ansi", errors="replace").replace("\r", "")
    except FileNotFoundError:
        LOG.debug("Exiftool not on PATH.")
    except UnicodeDecodeError as ex:
        # PyExifTool can't handle Parameters data of naughty test\00032-1238577453.png which Exiftool itself handles fine.
        LOG.error("exiftool read fail: %s", ex)
    return s.strip()


def info_icc() -> str:
    """Return the ICC color profile info."""
    s = ""
    icc = APP.im.info.get("icc_profile")  # type: ignore
    if icc:
        p = ImageCms.ImageCmsProfile(BytesIO(icc))
        intent = ImageCms.getDefaultIntent(p)
        man = ImageCms.getProfileManufacturer(p).strip()
        model = ImageCms.getProfileModel(p).strip()
        s += f"""ICC Profile:
Copyright: {ImageCms.getProfileCopyright(p).strip()}
Description: {ImageCms.getProfileDescription(p).strip()}
Intent: {('Perceptual', 'Relative colorimetric', 'Saturation', 'Absolute colorimetric')[intent]}
isIntentSupported: {ImageCms.isIntentSupported(p, ImageCms.Intent(intent), ImageCms.Direction(1))}"""
        if man:
            s += f"\nManufacturer: {man}"
        if model:
            s += f"\nModel: {model}"
    return s.strip()


def info_iptc() -> str:
    """Return IPTC metadata."""
    s = ""
    iptc = IptcImagePlugin.getiptcinfo(APP.im)
    if iptc:
        s += "IPTC:"
        for k, v in iptc.items():
            s += "\nKey:{} Value:{}".format(k, repr(v))
    return s.strip()


def info_psd() -> str:
    """Return PhotoShop Document info."""
    if "photoshop" not in APP.info:
        return ""
    s = "Photoshop:\n"
    for k, v in APP.info["photoshop"].items():
        readable_v = re.sub(r"(\\x..){2,}", " ", str(v)).replace(r"\\0", "")
        # readable_v = re.sub(
        #     r"\\0", "", re.sub(r"(\\x..){2,}", " ", str(v))
        # ).strip()
        # for enc in ('utf-16-le', 'utf-16-be', 'utf8'):
        #     try:
        #         readable_v = v.decode(enc)
        #         s += f"\nFROM ENCODING {enc}\n"
        #         break
        #     except:
        #         pass
        if not readable_v or re.match("b'\\s+'", readable_v):
            # Often binary data like version numbers.
            if len(v) < 5:
                v = int.from_bytes(v, byteorder="big")
            s += f"{psd_resource_ids.get(k, k)}: {(str(v)[:200] + '...') if len(str(v)) > 200 else v}\n"
        else:
            s += f"{psd_resource_ids.get(k, k)}: {readable_v[:200] + '...' if len(readable_v) > 200 else readable_v}\n"
        if (
            k == 1036
        ):  # PS5 thumbnail, https://www.awaresystems.be/imaging/tiff/tifftags/docs/photoshopthumbnail.html
            continue

    return s.strip()


def info_xmp() -> str:
    """Return XMP metadata."""
    s = ""
    if hasattr(APP.im, "getxmp"):
        xmp = APP.im.getxmp()  # type: ignore
        if xmp:
            s += "XMP:\n"
            s += yaml.safe_dump(xmp)
            # Ugly:
            # import json
            # s += json.dumps(xmp, indent=2, sort_keys=True)
            # import toml
            # s += toml.dumps(xmp)
            # s += "\n\n" + str(xmp)
    return s.strip()


def info_toggle(event=None):
    """Toggle info overlay."""
    if not APP.show_info or CANVAS.itemcget(CANVAS.text, "text").startswith("C - Set"):
        info_set(APP.title()[: -len(" - " + TITLE)] + info_get())
        LOG.debug("Showing info:\n%s", CANVAS.itemcget(CANVAS.text, "text"))
        info_show()
    else:
        info_hide()


def info_show():
    """Show info overlay."""
    APP.show_info = True
    CANVAS.lift(CANVAS.text_bg)
    CANVAS.lift(CANVAS.text)
    scrollbars_set()


def info_hide():
    """Hide info overlay."""
    APP.show_info = False
    CANVAS.lower(CANVAS.text_bg)
    CANVAS.lower(CANVAS.text)
    info_set(CANVAS.itemcget(CANVAS.text, "text")[:7])
    scrollbars_set()


def menu_show(event):
    """Show menu."""
    MENU.post(event.x_root, event.y_root)


def natural_sort(s):
    """Sort by number and string."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


@log_this
def path_open(event=None):
    """Pick a file to open...."""
    filename = filedialog.askopenfilename(filetypes=APP.SUPPORTED_FILES_READ)
    if filename:
        paths_update(None, filename)


@log_this
def path_save(event=None, filename=None, newmode=None, noexif=False):
    """Save file as...."""
    if "Names" in APP.info:
        p = pathlib.Path(
            str(APP.paths[APP.i_path]) + "." + APP.info["Names"][APP.i_zip]
        )
    else:
        p = APP.paths[APP.i_path]

    if not filename:
        filename = filedialog.asksaveasfilename(
            defaultextension=p.suffix,
            filetypes=APP.SUPPORTED_FILES_WRITE,
            initialfile=p.absolute(),
        )
    if filename:
        LOG.info("Saving %s", filename)
        im = APP.im.convert(newmode) if newmode else APP.im
        save_all = hasattr(im, "n_frames") and im.n_frames > 1
        fmt = filename.split(".")[-1].upper()
        if fmt == "JPG":
            fmt = "JPEG"
        if save_all and fmt not in Image.SAVE_ALL:
            answer = messagebox.showwarning(
                "Lose Frames",
                f"Can only store one frame in {fmt}. Ignore the rest?",
                type=messagebox.YESNO,
            )
            if answer != "yes":
                return
            save_all = False
        try:
            im_info = im.info.copy()
            if noexif:
                del im_info["exif"]
            # print("XXX Saving", im_info)
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
            if (
                str(ex) == "EXIF data is too long"  # From Pillow 9.5.0 (2023-04-01)
                and messagebox.showwarning(
                    "Lose EXIF", f"{ex}. Retry without it?", type=messagebox.YESNO
                )
                == "yes"
            ):
                path_save(filename=filename, newmode=newmode, noexif=True)
                return
            if str(ex) == "cannot write mode RGBA as JPEG":
                path_save(filename=filename, newmode="RGB", noexif=noexif)
                return
            raise


def paths_sort(path=None):
    """Sort paths."""
    LOG.debug("Sorting %s", APP.sort)
    if path:
        try:
            APP.i_path = APP.paths.index(pathlib.Path(path))
        except ValueError:
            pass
    elif APP.paths:
        path = APP.paths[APP.i_path]
    else:
        return

    for s in APP.sort.split(","):
        if s == "natural":
            APP.paths.sort(key=natural_sort)
        elif s == "ctime":
            APP.paths.sort(key=os.path.getmtime)
        elif s == "mtime":
            APP.paths.sort(key=os.path.getmtime)
        elif s == "random":
            random.shuffle(APP.paths)
        elif s == "size":
            APP.paths.sort(key=os.path.getsize)
        elif s == "string":
            APP.paths.sort()

    try:
        APP.i_path = APP.paths.index(pathlib.Path(path))
        im_load()
    except ValueError as ex:
        error_show("Not found: %s" % ex)


@log_this
def paths_update(event=None, path=None):
    """Update path info."""
    if not path:
        path = APP.paths[APP.i_path]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent
    LOG.debug("Reading %s...", p)
    APP.paths = list(p.glob("*"))
    LOG.debug("Found %s files.", len(APP.paths))
    LOG.debug("Filter?")
    paths_sort(path)


def refresh_loop():
    """Autoupdate paths."""
    if APP.update_interval > 0:
        paths_update()
        if hasattr(APP, "path_updater"):
            APP.after_cancel(APP.path_updater)
        APP.path_updater = APP.after(APP.update_interval, refresh_loop)


def refresh_toggle(event=None):
    """Toggle autoupdate."""
    APP.update_interval = -APP.update_interval
    if APP.update_interval > 0:
        toast(f"Refreshing every {APP.update_interval/1000:.2}s.")
        refresh_loop()
    else:
        toast("Refresh off.")


def resize_handler(event=None):
    """Handle Tk resize event."""
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
    """Scroll."""
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


def scrollbars_set():
    """Hide/show scrollbars."""
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
        if APP.i_path != APP.i_scroll:
            CANVAS.xview_moveto(0)
            CANVAS.yview_moveto(0)
            APP.i_scroll = APP.i_path
    except TypeError as ex:
        LOG.error(ex)


def set_bg(event=None):
    """Set background color."""
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
        bg=bg, fg=fg, bd=0, relief="flat", tearoff=0, activeborderwidth=0
    )  # Can't stop border on Windows!
    style.configure("TScrollbar", troughcolor=bg, background="darkgrey")
    style.map("TScrollbar", background=[("pressed", "!disabled", fg), ("active", fg)])
    style.configure("TSizegrip", background=bg)


@log_this
def set_order(event=None):
    """Set order."""
    i = SORTS.index(APP.sort) if APP.sort in SORTS else -1
    i = (i + 1) % len(SORTS)
    APP.sort = SORTS[i]
    s = "Sort: " + APP.sort
    LOG.info(s)
    toast(s)
    paths_sort()


def set_stats(path):
    """Set stats."""
    stats = os.stat(path)
    LOG.debug("Stat: %s", stats)
    APP.info = {
        # "Path": pathlib.Path(path),
        "Size": f"{stats.st_size:,} B",
        "Accessed": time.strftime(TIME_FORMAT, time.localtime(stats.st_atime)),
        "Modified": time.strftime(TIME_FORMAT, time.localtime(stats.st_mtime)),
        "Created": time.strftime(
            TIME_FORMAT,
            time.localtime(
                stats.st_birthtime if hasattr(stats, "st_birthtime") else stats.st_ctime
            ),
        ),
    }


def set_supported_files():
    """Set supported files."""
    exts = Image.registered_extensions()
    exts[".eml"] = "MHTML"
    exts[".mht"] = "MHTML"
    exts[".mhtml"] = "MHTML"
    exts[".svg"] = "SVG"
    exts[".svgz"] = "SVG"
    exts[".zip"] = "ZIP"

    type_exts = {}
    for k, v in exts.items():
        type_exts.setdefault(v, []).append(k)

    APP.SUPPORTED_FILES_READ = [
        (
            "All supported files",
            " ".join(sorted(list(k for k, v in exts.items() if v in Image.OPEN))),
        ),
        ("All files", "*"),
        ("Archives", ".eml .mht .mhtml .zip"),
        *sorted((k, v) for k, v in type_exts.items() if k in Image.OPEN),
    ]
    APP.SUPPORTED_FILES_WRITE = [
        (
            "All supported files",
            " ".join(sorted(list(k for k, v in exts.items() if v in Image.SAVE))),
        ),
        *sorted((k, v) for k, v in type_exts.items() if k in Image.SAVE),
    ]

    LOG.debug("Supports %s", ", ".join(s[1:].upper() for s in sorted(list(exts))))
    LOG.debug(
        "Open: %s",
        ", ".join(
            sorted(
                [k[1:].upper() for k, v in exts.items() if v in Image.OPEN]
                + ["EML", "MHT", "MHTML", "SVG", "SVGZ", "ZIP"]
            )
        ),
    )
    LOG.debug(
        "Save: %s",
        ", ".join(sorted(k[1:].upper() for k, v in exts.items() if v in Image.SAVE)),
    )
    LOG.debug(
        "Save all frames: %s",
        ", ".join(
            sorted(k[1:].upper() for k, v in exts.items() if v in Image.SAVE_ALL)
        ),
    )


def quality_set(event=None):
    """Set resize quality."""
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
    """Set verbosity."""
    APP.verbosity -= 10
    if APP.verbosity < 10:
        APP.verbosity = logging.CRITICAL

    logging.basicConfig(level=APP.verbosity)  # Show up in nested shells in Windows 11.
    LOG.setLevel(APP.verbosity)
    s = "Log level %s" % logging.getLevelName(LOG.getEffectiveLevel())
    toast(s)
    print(s)


def slideshow_run(event=None):
    """Run slideshow."""
    if APP.b_slideshow:
        browse()
        APP.after(APP.slideshow_pause, slideshow_run)


def slideshow_toggle(event=None):
    """Toggle slideshow."""
    APP.b_slideshow = not APP.b_slideshow
    if APP.b_slideshow:
        toast("Starting slideshow.")
        APP.after(APP.slideshow_pause, slideshow_run)
    else:
        toast("Stopping slideshow.")


def toast(msg: str, ms: int = 2000, fg="#00FF00"):
    """Temporarily show a status message."""
    TOAST.config(text=msg, fg=fg)
    TOAST.lift()
    if hasattr(APP, "toast_timer"):
        APP.after_cancel(APP.toast_timer)
    APP.toast_timer = APP.after(ms, TOAST.lower)


@log_this
def transpose_set(event=None):
    """Transpose image."""
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
    """Resize type to fit window."""
    APP.fit = (APP.fit + 1) % len(Fits)
    toast(str(Fits(APP.fit)))
    im_resize()


@log_this
def fullscreen_toggle(event=None):
    """Toggle fullscreen."""
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
    """Zoom."""
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
    """Zoom text."""
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
APP.drop_target_register(DND_FILES)
APP.dnd_bind("<<Drop>>", drop_handler)
APP.show_info = False
APP.title(TITLE)
APP_w, APP_h = int(APP.winfo_screenwidth() * 0.75), int(APP.winfo_screenheight() * 0.75)
geometry = f"{APP_w}x{APP_h}+{int(APP_w * 0.125)}+{int(APP_h * 0.125)}"
APP.geometry(geometry)

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

CANVAS = tkinter.Canvas(bg="blue", borderwidth=0, highlightthickness=0, relief="flat")
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
    (set_bg, "c"),
    (fullscreen_toggle, "f F11 Return"),
    (close, "Escape"),
    (help_toggle, "h F1"),
    (info_toggle, "i"),
    (animation_toggle, "a"),
    (browse_frame, "comma period"),
    (scroll, "Control-Left Control-Right Control-Up Control-Down"),
    (zoom, "Control-MouseWheel minus plus equal 0"),
    (quality_set, "q Q"),
    (fit_handler, "r"),
    (transpose_set, "t T"),
    (zoom_text, "Alt-MouseWheel Alt-minus Alt-plus Alt-equal"),
    (slideshow_toggle, "b Pause"),
    (browse_mouse, "MouseWheel"),
    (browse_next, "Right Down Next space Button-5"),
    (browse_prev, "Left Up Prior BackSpace Button-4"),
    (browse_end, "End"),
    (browse_home, "Key-1 Home"),
    (browse_percentage, "Key"),
    (browse_random, "x"),
    (set_order, "o"),
    (delete_file, "d Delete"),
    (path_open, "p"),
    (path_save, "s"),
    (paths_update, "u F5"),
    (refresh_toggle, "U"),
    (clipboard_copy, "Control-c Control-Insert"),
    (clipboard_paste, "Control-v Shift-Insert"),
    (set_verbosity, "v"),
    (drag, "B1-Motion"),
    (select, "B2-Motion"),
    (drag_begin, "ButtonPress"),
    (drag_end, "ButtonRelease"),
    (menu_show, "Button-3"),  # Or rather tk_popup in Ubuntu?
    (lines_toggle, "l"),
    (resize_handler, "Configure"),
]


def main(args):
    """Main function."""
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
    APP.s_geo = ""
    APP.transpose_type = -1
    APP.update_interval = -4000
    if args.verbose:
        APP.verbosity = VERBOSITY_LEVELS[
            min(len(VERBOSITY_LEVELS) - 1, 1 + args.verbose)
        ]
        set_verbosity()

    LOG.debug("Args: %s", args)
    APP.paths = []

    set_supported_files()

    APP.fit = args.resize or 0
    APP.quality = RESIZE_QUALITY[args.quality]
    APP.transpose_type = args.transpose

    # Needs visible window so wait for mainloop.
    APP.after(10, paths_update, None, args.path)
    APP.after(20, resize_handler)

    if args.fullscreen:
        APP.after(100, fullscreen_toggle)

    if args.geometry:
        APP.geometry(args.geometry)

    APP.sort = args.order if args.order else "natural"

    if args.update:
        APP.update_interval = args.update
        APP.after(1000, refresh_loop)

    if args.slideshow:
        APP.slideshow_pause = args.slideshow
        slideshow_toggle()
    else:
        APP.slideshow_pause = 4000

    # Prepare context menu.
    for fun, keys in BINDS:
        if fun in (
            browse_frame,
            browse_percentage,
            browse_mouse,
            drag,
            drag_begin,
            drag_end,
            menu_show,
            resize_handler,
            scroll,
            select,
            zoom,
            zoom_text,
        ):
            continue
        if re.match("[a-z]( |$)", keys):
            lbl = f"{fun.__doc__[:-1].title()} ({keys[0].upper()})"
            MENU.add_command(label=lbl, command=fun, underline=len(lbl) - 2)
        else:
            MENU.add_command(label=fun.__doc__[:-1].title(), command=fun)

    bind()
    set_bg()
    APP.mainloop()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        prog="tk_image_viewer",
        description="An image viewer that supports both arrow keys and "
        + "WebP with foreign characters in long paths.",
    )
    parser.add_argument("path", default=os.getcwd(), nargs="?")
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

    main(parser.parse_args())
