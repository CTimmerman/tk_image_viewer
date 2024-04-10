# pylint: disable=consider-using-f-string, global-statement, line-too-long, multiple-imports, too-many-boolean-expressions, too-many-branches, too-many-lines, too-many-locals, unused-argument, unused-import
"""Tk Image Viewer
by Cees Timmerman
2024-03-17 First version.
2024-03-23 Save stuff.
2024-03-24 Zip and multiframe image animation support.
2024-03-27 Set sort order. Support EML, MHT, MHTML.
2024-03-30 Copy info + paste/drop picture(s)/paths.
2024-04-08 Scroll/drag.
2024-04-10 AVIF, JXL, some SVG support.
"""
import base64, enum, functools, logging, os, pathlib, random, re, time, tkinter, zipfile  # noqa: E401
from io import BytesIO
from tkinter import filedialog, messagebox
import traceback

from tkinterdnd2 import DND_FILES, TkinterDnD  # type: ignore
import pillow_avif  # type: ignore  # noqa: F401  # pylint: disable=E0401
import pillow_jxl  # noqa: F401
from PIL import (
    ExifTags,
    Image,
    ImageCms,
    ImageColor,
    ImageDraw,
    ImageGrab,
    ImageTk,
    IptcImagePlugin,
    TiffTags,
)
from PIL.Image import Transpose
from pillow_heif import register_heif_opener  # type: ignore


# For libcairo
# os.environ["PATH"] = os.pathsep.join((".", os.environ["PATH"]))

from svgpathtools import svg2paths2, wsvg, Line  # type: ignore


class Fits(enum.IntEnum):
    """Types of window fitting."""

    NONE = 0
    ALL = 1
    BIG = 2
    SMALL = 3


ANIMATION_ON: bool = True
BG_COLORS = ["black", "gray10", "gray50", "white"]
BG_INDEX = -1
FIT = 0
FONT_SIZE = 14
IMAGE: Image.Image | None = None
IM_FRAME = 0
INFO: dict = {}
lines: list = []
lines_on: bool = False
OLD_INDEX = -1
QUALITY = Image.Resampling.NEAREST  # 0
REFRESH_INTERVAL = 0
SCALE = 1.0
SCALE_MIN = 0.001
SCALE_MAX = 40.0
SCALE_TEXT = 1.0
SHOW_INFO = False
SORTS = "natural string ctime mtime size".split()
SORT = "natural"
SUPPORTED_FILES: list = []
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
        s = (
            "Stopping animation."
            + f" Frame {1 + (1 + IM_FRAME) % IMAGE.n_frames}/{IMAGE.n_frames}"
            if hasattr(IMAGE, "n_frames")
            else ""
        )
        log.info(s)
        toast(s)


@log_this
def browse(event=None):
    """Browse."""
    global path_index, ZIP_INDEX

    new_index = path_index

    if "Names" in INFO:
        new_index = ZIP_INDEX

    k = event.keysym if event else "Next"
    if k in ("1", "Home"):
        new_index = 0
    elif k == "End":
        new_index = path_index - 1
    elif k == "x":
        new_index = random.randint(0, len(paths) - 1)
    elif (
        k in ("Left", "Up", "Button-4", "BackSpace")
        or event
        and (event.num == 4 or event.delta > 0)
    ):
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
            im_load()
            return

    if new_index < 0:
        new_index = len(paths) - 1
    if new_index >= len(paths):
        new_index = 0

    path_index = new_index
    ZIP_INDEX = 0
    im_load()


@log_this
def clipboard_copy(event):
    """Copy info to clipboard while app is running."""
    root.clipboard_clear()
    root.clipboard_append(
        "{}\n{}".format(root.title(), "\n".join(f"{k}: {v}" for k, v in INFO.items()))
    )


@log_this
def clipboard_paste(event):
    """Paste image from clipboard."""
    global IMAGE, INFO, path_index, paths
    im = ImageGrab.grabclipboard()
    log.debug("Pasted %r", im)
    if not im:
        im = root.clipboard_get()
        log.debug("Tk pasted %r", im)
        if not im:
            return
    if isinstance(im, str):
        im = [line.strip('"') for line in im.split("\n")]
    if isinstance(im, list):
        paths = [pathlib.Path(s) for s in im]
        log.debug("Set paths to %s", paths)
        path_index = 0
        im_load()
        return
    IMAGE = im
    INFO = {"Pasted": time.ctime()}
    path_index = 0
    paths = ["pasted"]
    im_resize(IMAGE)


@log_this
def close(event=None):
    """Close fullscreen or app."""
    if root.overrideredirect():
        fullscreen_toggle()
    else:
        event.widget.withdraw()
        event.widget.quit()


def debug_keys(event=None):
    """Show all keys."""


def delete_file(event=None):
    """Delete file. Bypasses Trash."""
    path = paths[path_index]
    msg = f"Delete? {path}"
    log.warning(msg)
    answer = messagebox.showwarning(
        "Delete File", f"Permanently delete {path}?", type=messagebox.YESNO
    )
    if answer == "yes":
        log.warning("Deleting %s", path)
        os.remove(path)
        paths_update()


@log_this
def drop_handler(event):
    """Handles dropped files."""
    global paths, path_index
    log.debug("Dropped %r", event.data)
    paths = [
        pathlib.Path(line.strip('"'))
        for line in re.findall("{(.+?)}" if "{" in event.data else "[^ ]+", event.data)
    ]  # Windows 11.
    if isinstance(paths, list):
        log.debug("Set paths to %s", paths)
        path_index = 0
        im_load()


def error_show(msg: str):
    """Show error."""
    log.error(msg)
    ERROR_OVERLAY.config(text=msg)
    ERROR_OVERLAY.lift()


def help_handler(event=None):
    """Show help."""
    global SHOW_INFO
    SHOW_INFO = not SHOW_INFO
    if SHOW_INFO:
        msg = "\n".join(
            f"{keys.replace('Control', 'Ctrl')} - {fun.__doc__}"
            for fun, keys in binds
            if "Configure" not in keys and "ButtonPress" not in keys
        )
        log.debug(msg)
        info_set(msg)
        canvas.lift(canvas.overlay)
    else:
        canvas.lower(canvas.overlay)


def info_set(msg: str):
    """Change info text."""
    canvas.itemconfig(canvas_info, text=msg)  # type: ignore
    info_update()


def info_update():
    """Update info overlay."""
    x1, y1, x2, y2 = canvas.bbox(canvas_info)
    canvas.overlay_tkim = ImageTk.PhotoImage(  # type: ignore
        Image.new("RGBA", (x2 - x1, y2 - y1), "#000a")
    )
    canvas.itemconfig(canvas.overlay, image=canvas.overlay_tkim)  # type: ignore


def lines_toggle(event):
    """Toggle line overlay."""
    global lines, lines_on
    if lines:
        for line in lines:
            canvas.delete(line)
        lines = []
    lines_on = not lines_on
    toast("Lines: %s" % lines_on)
    resize_handler()


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


def load_svg(fpath):
    """Load an SVG file."""
    global IMAGE

    svgpaths, attributes, svg_attributes = svg2paths2(fpath)
    print(
        "SVG PATHS\n",
        "\n".join(str(p) for p in svgpaths),
        "\nPATH ATTRS\n",
        "\n".join(str(s) for s in attributes),
        "\nSVG ATTRS\n",
        svg_attributes,
    )
    w, h = svg_attributes["viewBox"].split()[2:]
    IMAGE = Image.new("RGBA", (int(float(w)), int(float(h))), (100, 100, 100, 100))
    print(IMAGE, IMAGE.size)
    IMAGE.format = "SVG"
    ctx = ImageDraw.Draw(IMAGE)
    try:
        for i, path in enumerate(svgpaths):
            attrs = attributes[i]
            opacity = 1.0
            fill = "red"
            if "fill" in attrs:
                fill = attrs["fill"]
            elif "style" in attrs:
                style = attributes[i]["style"]
                fill = re.findall(r"fill:\s*([#0-9a-zA-Z]+)", style)
                if fill:
                    fill = fill[0]
                stroke = re.findall(r"stroke:\s*([#0-9a-zA-Z]+)", style)
                if stroke:
                    fill = stroke[0]
                if "opacity" in style:
                    opacity = float(re.findall(r"opacity:\s*([.0-9]+)", style)[0])

            try:
                color = (
                    ImageColor.getcolor(
                        (
                            "black"
                            if fill == "none"
                            else "white" if "url" in fill else fill
                        ),
                        "RGB",
                    )
                    if fill
                    else (255, 0, 0)
                )
            except ValueError as ex:
                log.error(ex)
                color = (255, 0, 0)

            if opacity:
                color = (*color, int(opacity * 255))
            print("COLOR", color, "FILL", fill)
            for el in path:
                log.debug("Drawing %s", (el, color))
                if isinstance(el, Line):
                    xy = (int(el.start.real), int(el.start.imag))
                    xy2 = (int(el.end.real), int(el.end.imag))
                    ctx.line(xy=(xy, xy2), fill=color, width=1)
                # ctx.polygon(path, fill=fill[0] if fill else 'red')  #, outline=None)
    except Exception as ex:  # pylint: disable=W0718
        print("SVG ERROR")
        traceback.print_exception(ex)


def load_zip(path):
    """Load a zip file."""
    global IMAGE
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        INFO["Names"] = names
        log.debug("Loading name index %s", ZIP_INDEX)
        # pylint: disable=consider-using-with
        IMAGE = Image.open(zf.open(names[ZIP_INDEX]))


def im_load(path=None):
    """Load image."""
    global IMAGE, IM_FRAME

    if not path and paths:
        path = paths[path_index]
    else:
        return

    msg = f"{path_index+1}/{len(paths)}"
    log.debug("Loading %s %s", msg, path)

    err_msg = ""
    try:
        if path != "pasted":
            set_stats(path)
            if path.suffix == ".zip":
                load_zip(path)
            elif path.suffix == ".svg":
                load_svg(path)
            elif path.suffix in (".eml", ".mht", ".mhtml"):
                load_mhtml(path)
            else:
                IMAGE = Image.open(path)
        log.debug("Cached %s PIL_IMAGE", IMAGE.size)
        IM_FRAME = 0
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
    # pylint: disable=W0718
    except (
        tkinter.TclError,
        IOError,
        MemoryError,  # NOSONAR
        EOFError,  # NOSONAR
        ValueError,  # NOSONAR
        BufferError,  # NOSONAR
        OSError,  # NOSONAR
        BaseException,  # NOSONAR  # https://github.com/PyO3/pyo3/issues/3519
    ) as ex:
        err_msg = f"{type(ex)} {ex}"
        IMAGE = None
        msg = f"{msg} {err_msg} {path}"
        error_show(msg)
        info_set(msg)
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
    if ratio != 1.0:  # NOSONAR
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
        duration = (INFO["duration"] or 100) if "duration" in INFO else 100
        try:
            root.after_cancel(root.animation)
        except AttributeError:
            pass
        root.animation = root.after(duration, im_resize, ANIMATION_ON)


def im_show(im):
    """Show PIL image in Tk image widget."""
    global SCALE
    try:
        canvas.tkim: ImageTk.PhotoImage = ImageTk.PhotoImage(im)  # type: ignore
        canvas.itemconfig(canvas.image_ref, image=canvas.tkim, anchor="center")

        try:
            rw, rh = root.winfo_width(), root.winfo_height()
            x, y, x2, y2 = canvas.bbox(canvas.image_ref)
            w = x2 - x
            h = y2 - y
            good_x = rw // 2 - w // 2
            good_y = rh // 2 - h // 2
            # canvas.move(canvas.image_ref, -x + canvas.winfo_width() // 2, -y + canvas.winfo_height() // 2)
            canvas.move(canvas.image_ref, good_x - x, good_y - y)
        except TypeError as ex:
            log.error(ex)

        # canvas.move(canvas.image_ref, 10, 0)
        ERROR_OVERLAY.lower()
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
    info_set(msg + "\n" + info_get())
    scrollbars_set()


def natural_sort(s):
    """Sort by number and string."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


def scroll(event):
    """Scroll."""
    k = event.keysym
    if k == "Left":
        canvas.xview_scroll(-10, "units")
    elif k == "Right":
        canvas.xview_scroll(10, "units")
    if k == "Up":
        canvas.yview_scroll(-10, "units")
    elif k == "Down":
        canvas.yview_scroll(10, "units")


def scrollbars_set():
    """Hide/show scrollbars."""
    global OLD_INDEX
    try:
        x, y, x2, y2 = canvas.bbox(canvas.image_ref, canvas_info)
        w = x2 - x
        h = y2 - y
        sv = max(0, y) + h > root.winfo_height()
        # Vertical scrollbar causing horizontal scrollbar.
        sh = max(0, x) + w > root.winfo_width() - 16 * sv
        # Horizontal scrollbar causing vertical scrollbar.
        sv = max(0, y) + h > root.winfo_height() - 16 * sh
        if sh:
            h += 16
            scrollx.lift()
        else:
            scrollx.lower()

        if sv:
            w += 16
            scrolly.lift()
        else:
            scrolly.lower()

        scrollregion = (min(x, 0), min(y, 0), x + w, y + h)
        canvas.config(scrollregion=scrollregion)
        if path_index != OLD_INDEX:
            canvas.xview_moveto(0)
            canvas.yview_moveto(0)
            OLD_INDEX = path_index
    except TypeError as ex:
        log.error(ex)


def info_get() -> str:
    """Get image info."""
    msg = "\n".join(
        f"{k}: {(str(v)[:80] + '...') if len(str(v)) > 80 else v}"
        for k, v in INFO.items()
    )
    if not IMAGE:
        return msg

    msg += f"\nFormat: {IMAGE.format}"
    try:
        msg += f"\nMIME type: {IMAGE.get_format_mimetype()}" ""  # type: ignore
    except AttributeError:
        pass
    icc = IMAGE.info.get("icc_profile")
    if icc:
        p = ImageCms.ImageCmsProfile(BytesIO(icc))
        intent = ImageCms.getDefaultIntent(p)
        man = ImageCms.getProfileManufacturer(p).strip()
        model = ImageCms.getProfileModel(p).strip()
        msg += f"""

ICC Profile:
-Copyright: {ImageCms.getProfileCopyright(p).strip()}
-Description: {ImageCms.getProfileDescription(p).strip()}
-Intent: {('Perceptual', 'Relative colorimetric', 'Saturation', 'Absolute colorimetric')[intent]}
-isIntentSupported: {ImageCms.isIntentSupported(p, intent, 1)}
"""
        if man:
            msg += f"-Manufacturer: {man}"
        if model:
            msg += f"-Model: {model}"

    # Image File Directories (IFD)
    if hasattr(IMAGE, "tag_v2"):
        meta_dict = {TiffTags.TAGS_V2[key]: IMAGE.tag_v2[key] for key in IMAGE.tag_v2}
        log.debug("tag_v2 %s", meta_dict)

    # Exchangeable Image File (EXIF)
    # Workaround from https://github.com/python-pillow/Pillow/issues/5863
    if hasattr(IMAGE, "_getexif"):
        exif = IMAGE._getexif()  # pylint: disable=protected-access
        if exif:
            msg += "\n\nEXIF:"
            for key, val in exif.items():
                if isinstance(val, bytes):
                    val = val.decode("utf_16_be")
                    log.debug(
                        "==========================================================\nDecoded %s",
                        val,
                    )
                if key in ExifTags.TAGS:
                    msg += f"\n{ExifTags.TAGS[key]}: {val}"
                else:
                    msg += f"\nUnknown EXIF tag {key}: {val}"

        # Image File Directory (IFD)
        exif = IMAGE.getexif()
        for k in ExifTags.IFD:
            try:
                msg += f"\nIFD tag {k}: {ExifTags.IFD(k).name}: {exif.get_ifd(k)}"
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
        canvas.lift(canvas.overlay)
        canvas.lift(canvas_info)
        log.debug("Showing info:\n%s", canvas.itemcget(canvas_info, "text"))
    else:
        canvas.lower(canvas.overlay)
        canvas.lower(canvas_info)


@log_this
def drag_start(e):
    """Keep start pos for delta move."""
    canvas.dragx = e.x
    canvas.dragy = e.y


def drag(e):
    """Drag image around."""
    if e.widget != canvas:
        return
    x, y, x2, y2 = canvas.bbox(canvas.image_ref)
    w = x2 - x
    h = y2 - y
    log.debug("Draggin image: %s", (x, y, x2, y2, w, h))
    dx, dy = e.x - canvas.dragx, e.y - canvas.dragy
    # Keep at least a corner in view.
    # Goes entirely out of view when switching to smaller imag!
    # new_x = max(-w + 64, min(root.winfo_width() - 64, x + dx))
    # new_y = max(-h + 64, min(root.winfo_height() - 64, y + dy))

    new_x = max(0, min(root.winfo_width() - w, x + dx))
    new_y = max(0, min(root.winfo_height() - h, y + dy))
    if new_x == 0:
        canvas.xview_scroll(-dx, "units")
    if new_y == 0:
        canvas.yview_scroll(-dy, "units")

    dx, dy = new_x - x, new_y - y
    canvas.move(canvas.image_ref, dx, dy)
    scrollbars_set()
    canvas.dragx, canvas.dragy = e.x, e.y


def set_supported_files():
    """Set supported files. TODO: Distinguish between openable and saveable."""
    global SUPPORTED_FILES
    exts = Image.registered_extensions()
    exts[".eml"] = "EML"
    exts[".mht"] = "MHT"
    exts[".mhtml"] = "MHTML"
    exts[".svg"] = "SVG"
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

    log.debug("Image info to be saved: %s", IMAGE.info)
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
                lossless=True,
                optimize=True,
                save_all=hasattr(IMAGE, "n_frames"),  # All frames.
            )
            paths_update()
            toast(f"Saved {filename}")
        except (IOError, KeyError, TypeError, ValueError) as ex:
            msg = f"Failed to save as {filename}. {ex}"
            log.error(msg)
            toast(msg, 4000, "red")
            raise


def paths_sort(path=None):
    """Sort paths."""
    global path_index
    log.debug("Sorting %s", SORT)
    if path:
        try:
            path_index = paths.index(pathlib.Path(path))
        except ValueError:
            pass
    elif paths:
        path = paths[path_index]
    else:
        return

    for s in SORT.split(","):
        if s == "natural":
            paths.sort(key=natural_sort)
        elif s == "ctime":
            paths.sort(key=os.path.getmtime)
        elif s == "mtime":
            paths.sort(key=os.path.getmtime)
        elif s == "random":
            random.shuffle(paths)
        elif s == "size":
            paths.sort(key=os.path.getsize)
        elif s == "string":
            paths.sort()

    try:
        path_index = paths.index(pathlib.Path(path))
        im_load()
    except ValueError as ex:
        error_show("Not found: %s" % ex)


@log_this
def paths_update(event=None, path=None):
    """Update path info."""
    global paths
    if not path:
        path = paths[path_index]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent
    log.debug("Reading %s...", p)
    paths = list(p.glob("*"))
    log.debug("Found %s files.", len(paths))
    log.debug("Filter?")
    paths_sort(path)


def update_loop():
    """Autoupdate paths."""
    if REFRESH_INTERVAL:
        paths_update()
        root.after(REFRESH_INTERVAL, update_loop)


def resize_handler(event=None):
    """Handle Tk resize event."""
    global WINDOW_SIZE
    new_size = root.winfo_geometry().split("+", maxsplit=1)[0]
    if lines_on:
        w = root.winfo_width() - 1
        h = root.winfo_height() - 1
        if not lines:
            lines.append(canvas.create_line(0, 0, w, 0, 0, h, w, h, fill="#f00"))  # type: ignore
            lines.append(canvas.create_line(0, h, 0, 0, w, h, w, 0, fill="#f00"))  # type: ignore
        else:
            canvas.coords(lines[0], 0, 0, w, 0, 0, h, w, h)
            canvas.coords(lines[1], 0, h, 0, 0, w, h, w, 0)
    if WINDOW_SIZE != new_size:
        ERROR_OVERLAY.config(wraplength=event.width)
        TOAST.config(wraplength=event.width)
        bb = canvas.bbox(canvas_info)
        canvas.itemconfig(canvas_info, width=event.width - 16)
        if bb != canvas.bbox(canvas_info):
            info_update()

        if WINDOW_SIZE and FIT:
            im_resize()
        else:
            scrollbars_set()
        WINDOW_SIZE = new_size


@log_this
def set_bg(event=None):
    """Set background color."""
    global BG_INDEX
    BG_INDEX += 1
    if BG_INDEX >= len(BG_COLORS):
        BG_INDEX = 0
    bg = BG_COLORS[BG_INDEX]
    root.config(bg=bg)
    canvas.config(bg=bg)
    ERROR_OVERLAY.config(bg=bg)


@log_this
def set_order(event=None):
    """Set order."""
    global SORT
    i = SORTS.index(SORT) if SORT in SORTS else -1
    i = (i + 1) % len(SORTS)
    SORT = SORTS[i]
    s = "Sort: " + SORT
    log.info(s)
    toast(s)
    paths_sort()


@log_this
def set_verbosity(event=None):
    """Set verbosity."""
    global VERBOSITY
    VERBOSITY -= 10
    if VERBOSITY < 10:
        VERBOSITY = logging.CRITICAL

    logging.basicConfig(level=VERBOSITY)  # Show up in nested shells in Windows 11.
    log.setLevel(VERBOSITY)
    s = "Log level %s" % logging.getLevelName(log.getEffectiveLevel())
    toast(s)
    print(s)


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
    TOAST.config(text=msg, fg=fg)
    TOAST.lift()
    root.after(ms, TOAST.lower)


@log_this
def transpose_set(event=None):
    """Transpose image."""
    global TRANSPOSE_INDEX
    TRANSPOSE_INDEX += -1 if event.keysym == "T" else 1
    if TRANSPOSE_INDEX >= len(Transpose):
        TRANSPOSE_INDEX = -1
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
    toast(str(Fits(FIT)))
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


def zoom(event):
    """Zoom."""
    global SCALE
    k = event.keysym if event else "plus"
    if event.num == 5 or event.delta < 0:
        k = "plus"
    if event.num == 4 or event.delta > 0:
        k = "minus"
    if k in ("plus", "equal"):
        SCALE *= 1.1
    elif k == "minus":
        SCALE *= 0.9
    else:
        SCALE = 1
    SCALE = max(SCALE_MIN, min(SCALE, SCALE_MAX))
    im_resize()


@log_this
def zoom_text(event):
    """Zoom text."""
    global SCALE_TEXT
    k = event.keysym if event else "plus"
    if event.num == 5 or event.delta < 0:
        k = "plus"
    if event.num == 4 or event.delta > 0:
        k = "minus"
    if k in ("plus", "equal"):
        SCALE_TEXT *= 1.1
    elif k == "minus":
        SCALE_TEXT *= 0.9
    else:
        SCALE_TEXT = 1
    SCALE_TEXT = max(0.1, min(SCALE_TEXT, 20))
    new_font_size = int(FONT_SIZE * SCALE_TEXT)
    new_font_size = max(1, min(new_font_size, 200))

    log.info("Text scale: %s New font size: %s", SCALE_TEXT, new_font_size)

    ERROR_OVERLAY.config(font=("Consolas", new_font_size))
    TOAST.config(font=("Consolas", new_font_size * 2))


root = TkinterDnD.Tk()  # notice - use this instead of tk.Tk()
root.drop_target_register(DND_FILES)
root.dnd_bind("<<Drop>>", drop_handler)

root.title(TITLE)
root_w, root_h = int(root.winfo_screenwidth() * 0.75), int(
    root.winfo_screenheight() * 0.75
)
geometry = f"{root_w}x{root_h}+{int(root_w * 0.125)}+{int(root_h * 0.125)}"
root.geometry(geometry)

SLIDESHOW_ON = False
SLIDESHOW_PAUSE = 4000
TOAST = tkinter.Label(
    root,
    text="status",
    font=("Consolas", FONT_SIZE * 2),
    fg="#00FF00",
    bg="black",
    wraplength=root_w,
    anchor="center",
    justify="center",
)
TOAST.place(x=0, y=0)

canvas = tkinter.Canvas(borderwidth=0, highlightthickness=0, relief="flat")
canvas.place(x=0, y=0, relwidth=1, relheight=1)
canvas.image_ref = canvas.create_image(root_w // 2, root_h // 2, anchor="center")  # type: ignore
canvas.overlay = canvas.create_image(0, 0, anchor="nw")  # type: ignore
canvas_info = canvas.create_text(
    1,  # If 0, bbox starts at -1.
    0,
    anchor="nw",
    text="status",
    fill="#ff0",
    font=("Consolas", FONT_SIZE),
    width=root_w,
)

scrollx = tkinter.Scrollbar(root, orient="horizontal", command=canvas.xview)
scrollx.place(x=0, y=1, relwidth=1, relx=1, rely=1, anchor="se")
scrolly = tkinter.Scrollbar(root, command=canvas.yview)
scrolly.place(x=1, y=0, relheight=1, relx=1, rely=1, anchor="se")
canvas.config(xscrollcommand=scrollx.set, yscrollcommand=scrolly.set)
ERROR_OVERLAY = tkinter.Label(
    root,
    compound="center",
    fg="red",
    font=("Consolas", FONT_SIZE),
    width=root_w,
    height=root_h,
    wraplength=root_w,
)
ERROR_OVERLAY.place(x=0, y=0, relwidth=1, relheight=1)
set_bg()

root.bind_all("<Key>", debug_keys)
binds = [
    (close, "Escape q"),
    (help_handler, "F1 h"),
    (fullscreen_toggle, "F11 Return f"),
    (
        browse,
        "Left Right Up Down BackSpace space MouseWheel Button-4 Button-5 Home End Key-1 x",
    ),
    (path_open, "p"),
    (path_save, "s"),
    (delete_file, "Delete"),
    (paths_update, "F5 u"),
    (set_order, "o"),
    (set_bg, "b c"),
    (drag_start, "ButtonPress"),
    (drag, "B1-Motion B2-Motion B3-Motion"),
    (scroll, "Control-Left Control-Right Control-Up Control-Down"),
    (zoom, "Control-MouseWheel minus plus equal 0"),
    (zoom_text, "Alt-MouseWheel Alt-minus Alt-plus Alt-equal"),
    (fit_handler, "r"),
    (animation_toggle, "a"),
    (slideshow_toggle, "Pause"),
    (lines_toggle, "l"),
    (transpose_set, "t Shift-t"),
    (info_toggle, "i"),
    (clipboard_copy, "Control-c"),
    (clipboard_paste, "Control-v"),
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
    root.after(50, paths_update, None, args.path)

    if args.fullscreen:
        root.after(100, fullscreen_toggle)

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
