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
from tkinter import filedialog, messagebox

# from exiftool import ExifToolHelper  # type: ignore  # Needs exiftool in path.
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
SORTS = "natural string ctime mtime size".split()
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
log = logging.getLogger(TITLE)

register_heif_opener()


def log_this(func):
    """Decorator to log function calls."""

    @functools.wraps(func)  # Keep signature.
    def inner(*args, **kwargs):
        log.debug("Calling %s with %s, %s", func.__name__, args, kwargs)
        return func(*args, **kwargs)

    return inner


def animation_toggle(event=None):
    """Toggle animation."""
    ROOT.b_animate = not ROOT.b_animate
    if ROOT.b_animate:
        toast("Starting animation.")
        im_resize(ROOT.b_animate)
    else:
        s = (
            "Stopping animation."
            + f" Frame {1 + (1 + ROOT.im_frame) % ROOT.im.n_frames}/{ROOT.im.n_frames}"
            if hasattr(ROOT.im, "n_frames")
            else ""
        )
        log.info(s)
        toast(s)


@log_this
def browse(event=None):
    """Browse."""
    new_index = ROOT.i_path

    if "Names" in ROOT.info:
        new_index = ROOT.i_zip

    k = event.keysym if event else "Next"
    if k in ("1", "Home"):
        new_index = 0
    elif k == "End":
        new_index = ROOT.i_path - 1
    elif k == "x":
        new_index = random.randint(0, len(ROOT.paths) - 1)
    elif (
        k in ("Left", "Up", "Button-4", "BackSpace")
        or event
        and (event.num == 4 or event.delta > 0)
    ):
        new_index -= 1
    else:
        new_index += 1

    if "Names" in ROOT.info:
        if new_index < 0:
            new_index = ROOT.i_path - 1
        elif new_index >= len(ROOT.info["Names"]):
            new_index = ROOT.i_path + 1
        else:
            ROOT.i_zip = new_index
            im_load()
            return

    if new_index < 0:
        new_index = len(ROOT.paths) - 1
    if new_index >= len(ROOT.paths):
        new_index = 0

    ROOT.i_path = new_index
    ROOT.i_zip = 0
    im_load()


def browse_frame(event=None):
    """Browse animation frames."""
    if not hasattr(ROOT.im, "n_frames"):
        toast("No frames.")
        return
    n = ROOT.im.n_frames - 1
    k = event.keysym
    if k == "comma":
        ROOT.im_frame -= 1
        if ROOT.im_frame < 0:
            ROOT.im_frame = n
    else:
        ROOT.im_frame += 1
        if ROOT.im_frame > n:
            ROOT.im_frame = 0

    ROOT.im.seek(ROOT.im_frame)
    im_resize()
    toast(f"Frame {1 + ROOT.im_frame}/{1 + n}", 1000)


def clipboard_copy(event=None):
    """Copy info to clipboard."""
    pyperclip.copy(CANVAS.itemcget(canvas_info, "text"))
    toast("Copied info.")


def clipboard_paste(event=None):
    """Paste image from clipboard."""
    im = ImageGrab.grabclipboard()
    log.debug("Pasted %r", im)
    if not im:
        im = ROOT.clipboard_get()
        log.debug("Tk pasted %r", im)
        if not im:
            return
    if isinstance(im, str):
        im = [line.strip('"') for line in im.split("\n")]
    if isinstance(im, list):
        ROOT.paths = [pathlib.Path(s) for s in im]
        log.debug("Set paths to %s", ROOT.paths)
        ROOT.i_path = 0
        im_load()
        return
    ROOT.im = im
    ROOT.info = {"Pasted": time.ctime()}
    ROOT.i_path = 0
    ROOT.paths = ["pasted"]
    im_resize(ROOT.im)


@log_this
def close(event=None):
    """Close fullscreen or app."""
    if ROOT.overrideredirect():
        fullscreen_toggle()
    else:
        ROOT.quit()


@log_this
def debug_keys(event=None):
    """Show all keys."""


def delete_file(event=None):
    """Delete file. Bypasses Trash."""
    path = ROOT.paths[ROOT.i_path]
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
def drag_begin(event):
    """Keep drag begin pos for delta move."""
    if event.widget != CANVAS:
        return
    CANVAS.dragx = CANVAS.canvasx(event.x)
    CANVAS.dragy = CANVAS.canvasy(event.y)
    CANVAS.config(cursor="tcross" if event.num == 1 else "fleur")


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
    # new_x = max(-w + 64, min(root.winfo_width() - 64, x + dx))
    # new_y = max(-h + 64, min(root.winfo_height() - 64, y + dy))

    new_x = max(0, min(ROOT.winfo_width() - w, x + dx))
    new_y = max(0, min(ROOT.winfo_height() - h, y + dy))
    if new_x == 0:
        CANVAS.xview_scroll(-dx, "units")
    if new_y == 0:
        CANVAS.yview_scroll(-dy, "units")

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
    log.debug("Dropped %r", event.data)
    ROOT.paths = [
        pathlib.Path(line.strip('"'))
        for line in re.findall("{(.+?)}" if "{" in event.data else "[^ ]+", event.data)
    ]  # Windows 11.
    if isinstance(ROOT.paths, list):
        log.debug("Set paths to %s", ROOT.paths)
        ROOT.i_path = 0
        im_load()


def error_show(msg: str):
    """Show error."""
    ROOT.title(msg + " - " + TITLE)
    log.error(msg)
    ERROR_OVERLAY.config(text=msg)
    ERROR_OVERLAY.lift()
    info_set(msg)  # To copy.
    ROOT.i_path_old = -1  # To refresh image info.


def help_toggle(event=None):
    """Toggle help."""
    if ROOT.show_info and CANVAS.itemcget(canvas_info, "text").startswith("C - Set"):
        info_hide()
    else:
        lines = []
        for fun, keys in binds:
            if keys in ("ButtonPress", "ButtonRelease", "Configure"):
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
                        .replace("Shift-", "Shift+"),
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
        log.debug(msg)


def info_set(msg: str):
    """Change info text."""
    CANVAS.itemconfig(canvas_info, text=msg)  # type: ignore
    info_bg_update()


def info_bg_update():
    """Update info overlay."""
    x1, y1, x2, y2 = CANVAS.bbox(canvas_info)
    CANVAS.overlay_tkim = ImageTk.PhotoImage(  # type: ignore
        Image.new("RGBA", (x2 - x1, y2 - y1), "#000a")
    )
    CANVAS.itemconfig(CANVAS.overlay, image=CANVAS.overlay_tkim)  # type: ignore
    CANVAS.coords(CANVAS.im_bg, x1, y1, x2, y2)


def lines_toggle(event=None, on=None, off=None):
    """Toggle line overlay."""
    ROOT.b_lines = True if on else False if off else not ROOT.b_lines  # NOSONAR
    if not ROOT.b_lines and CANVAS.lines:
        for line in CANVAS.lines:
            CANVAS.delete(line)
        CANVAS.lines = []
    if ROOT.b_lines and not CANVAS.lines:
        w = ROOT.winfo_width() - 1
        h = ROOT.winfo_height() - 1
        CANVAS.lines.append(CANVAS.create_line(0, 0, w, 0, 0, h, w, h, fill="#f00"))  # type: ignore
        CANVAS.lines.append(CANVAS.create_line(0, h, 0, 0, w, h, w, 0, fill="#f00"))  # type: ignore


def load_mhtml(path):
    """Load EML/MHT/MHTML."""
    with open(path, "r", encoding="utf8") as f:
        mhtml = f.read()
    boundary = re.search('boundary="(.+)"', mhtml).group(1)
    parts = mhtml.split(boundary)[1:-1]
    ROOT.info["Names"] = []
    new_parts = []
    for p in parts:
        meta, data = p.split("\n\n", maxsplit=1)
        m = meta.lower()
        if "\ncontent-transfer-encoding: base64" not in m:
            continue
        if "\ncontent-type:" in m and "\ncontent-type: image" not in m:
            continue
        name = sorted(meta.strip().split("\n"))[0].split("/")[-1]
        ROOT.info["Names"].append(name)
        new_parts.append(data)
    log.debug("%s", f"Getting part {ROOT.i_zip}/{len(new_parts)} of {len(parts)}.")
    data = new_parts[ROOT.i_zip]
    try:
        im_file = BytesIO(base64.standard_b64decode(data.rstrip()))
        ROOT.im = Image.open(im_file)
    except ValueError as ex:
        log.error("Failed to split mhtml: %s", ex)
        log.error("DATA %r", data[:180])
        im_file.seek(0)
        log.error("DECODED %s", im_file.read()[:80])


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
    ROOT.im = Image.open(bf)


def load_zip(path):
    """Load a zip file."""
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        ROOT.info["Names"] = names
        log.debug("Loading name index %s", ROOT.i_zip)
        # pylint: disable=consider-using-with
        ROOT.im = Image.open(zf.open(names[ROOT.i_zip]))


def im_load(path=None):
    """Load image."""
    if not path and ROOT.paths:
        path = ROOT.paths[ROOT.i_path]
    else:
        return

    msg = f"{ROOT.i_path+1}/{len(ROOT.paths)}"
    log.debug("Loading %s %s", msg, path)

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
                ROOT.im = Image.open(path)
        log.debug("Cached %s PIL_IMAGE", ROOT.im.size)
        ROOT.im_frame = 0
        if hasattr(ROOT.im, "n_frames"):
            ROOT.info["Frames"] = ROOT.im.n_frames
        ROOT.info.update(**ROOT.im.info)
        for k, v in ROOT.info.items():
            log.debug(
                "%s: %s",
                k,
                str(v)[:80] + "..." if len(str(v)) > 80 else v,
            )
        im_resize(ROOT.b_animate)
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
        ROOT.im = None
        msg = f"{msg} {err_msg} {path}"
        error_show(msg)
        raise


def get_fit_ratio(im_w, im_h):
    """Get fit ratio."""
    ratio = 1.0
    w = ROOT.winfo_width()
    h = ROOT.winfo_height()
    if (
        ((ROOT.fit == Fits.ALL) and (im_w != w or im_h != h))
        or ((ROOT.fit == Fits.BIG) and (im_w > w or im_h > h))
        or ((ROOT.fit == Fits.SMALL) and (im_w < w and im_h < h))
    ):
        ratio = min(w / im_w, h / im_h)
    return ratio


def im_fit(im):
    """Fit image to window."""
    w, h = im.size
    ratio = get_fit_ratio(w, h)
    if ratio != 1.0:  # NOSONAR
        im = im.resize((int(w * ratio), int(h * ratio)), ROOT.quality)
    return im


def im_scale(im):
    """Scale image."""
    im_w, im_h = im.size
    ratio = ROOT.im_scale * get_fit_ratio(im_w, im_h)
    try:
        new_w = int(ratio * im_w)
        new_h = int(ratio * im_h)
        if new_w < 1 or new_h < 1:
            log.error("Too small. Scaling up.")
            ROOT.im_scale = max(SCALE_MIN, min(ROOT.im_scale * 1.1, SCALE_MAX))
            im = im_scale(im)
        else:
            im = ROOT.im.resize((new_w, new_h), ROOT.quality)
    except MemoryError as ex:
        log.error("Out of memory. Scaling down. %s", ex)
        ROOT.im_scale = max(SCALE_MIN, min(ROOT.im_scale * 0.9, SCALE_MAX))

    return im


def im_resize(loop=False):
    """Resize image."""
    if not ROOT.im:
        return

    im = ROOT.im.copy()

    if ROOT.fit:
        im = im_fit(ROOT.im)

    if ROOT.im_scale != 1:
        im = im_scale(ROOT.im)

    if ROOT.transpose_type != -1:
        log.debug("Transposing %s", Transpose(ROOT.transpose_type))
        im = im.transpose(ROOT.transpose_type)

    im_show(im)

    if loop and hasattr(ROOT.im, "n_frames") and ROOT.im.n_frames > 1:
        ROOT.im_frame = (ROOT.im_frame + 1) % ROOT.im.n_frames
        try:
            ROOT.im.seek(ROOT.im_frame)
        except EOFError as ex:
            log.error("IMAGE EOF. %s", ex)
        duration = int(ROOT.info["duration"] or 100) if "duration" in ROOT.info else 100
        if hasattr(ROOT, "animation"):
            ROOT.after_cancel(ROOT.animation)
        ROOT.animation = ROOT.after(duration, im_resize, ROOT.b_animate)


def im_show(im):
    """Show PIL image in Tk image widget."""
    try:
        CANVAS.tkim: ImageTk.PhotoImage = ImageTk.PhotoImage(im)  # type: ignore
        CANVAS.itemconfig(CANVAS.image_ref, image=CANVAS.tkim, anchor="center")

        try:
            rw, rh = ROOT.winfo_width(), ROOT.winfo_height()
            x, y, x2, y2 = CANVAS.bbox(CANVAS.image_ref)
            w = x2 - x
            h = y2 - y
            good_x = rw // 2 - w // 2
            good_y = rh // 2 - h // 2
            # canvas.move(canvas.image_ref, -x + canvas.winfo_width() // 2, -y + canvas.winfo_height() // 2)
            CANVAS.move(CANVAS.image_ref, good_x - x, good_y - y)
        except TypeError as ex:
            log.error(ex)

        # canvas.move(canvas.image_ref, 10, 0)
        ERROR_OVERLAY.lower()
    except MemoryError as ex:
        log.error("Out of memory. Scaling down. %s", ex)
        ROOT.im_scale = max(SCALE_MIN, min(ROOT.im_scale * 0.9, SCALE_MAX))
        return

    zip_info = (
        f" {ROOT.i_zip + 1}/{len(ROOT.info['Names'])} {ROOT.info['Names'][ROOT.i_zip]}"
        if "Names" in ROOT.info
        else ""
    )
    msg = (
        f"{ROOT.i_path+1}/{len(ROOT.paths)}{zip_info} {'%sx%s' % ROOT.im.size}"
        f" @ {'%sx%s' % im.size} {ROOT.paths[ROOT.i_path]}"
    )
    ROOT.title(msg + " - " + TITLE)
    if ROOT.show_info and (
        not hasattr(ROOT, "i_path_old")
        or ROOT.i_path != ROOT.i_path_old
        or not hasattr(ROOT, "i_path_old")
        or ROOT.i_zip != ROOT.i_zip_old
    ):
        ROOT.i_path_old = ROOT.i_path
        ROOT.i_zip_old = ROOT.i_zip
        info_set(msg + info_get())
    scrollbars_set()


def info_decode(b: bytes, encoding: str) -> str:
    """Decodes a sequence of bytes, as stated by the method signature."""
    if not isinstance(b, bytes):
        return str(b)
    print("BYTES!", str(b[:80]), "->", str(b.replace(b"\0", b"")))
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
                log.debug("info_decode %s", enc)
                return b.decode(enc)
            except UnicodeDecodeError:
                pass
    return b.decode("ansi")
    # return str(b.replace(b"\0", b""))


def info_get() -> str:
    """Get image info."""
    msg = ""
    for k, v in ROOT.info.items():
        if k in ("exif", "icc_profile", "photoshop", "XML:com.adobe.xmp", "Names"):
            continue

        if k == "comment":
            try:
                v = v.decode("utf8")
            except UnicodeDecodeError:
                v = v.decode("utf_16_be")
        # Image File Directories (IFD)
        elif k == "tag_v2":
            meta_dict = {TiffTags.TAGS_V2[k2]: v2 for k2, v2 in v}
            log.debug("tag_v2: %s", meta_dict)
            msg += "\ntag_v2: {meta_dict}\n"
        else:
            msg += f"\n{k}: {v}"
            # msg += f"\n{k}: {(str(v)[:80] + '...') if len(str(v)) > 80 else v}"
    if not ROOT.im:
        return msg

    msg += f"\nFormat: {ROOT.im.format}"
    try:
        msg += f"\nMIME type: {ROOT.im.get_format_mimetype()}"  # type: ignore
    except AttributeError:
        pass

    for fun in (info_exif, info_icc, info_iptc, info_xmp, info_psd, info_exiftool):
        s = fun()
        if s:
            msg += "\n\n" + s

    return msg


def info_exif() -> str:
    """Return Exchangeable Image File (EXIF) info."""
    # Workaround from https://github.com/python-pillow/Pillow/issues/5863
    if not hasattr(ROOT.im, "_getexif"):
        return ""

    exif = ROOT.im._getexif()  # type: ignore  # pylint: disable=protected-access
    if not exif:
        return ""
    log.debug("Got exif dict: %s", exif)
    log.debug("im.exif bytes: %s", ROOT.info["exif"].replace(b"\0", b""))
    encoding = "utf_16_be" if b"MM" in ROOT.info["exif"][:8] else "utf_16_le"
    log.debug("Encoding: %s", encoding)
    s = f"EXIF: {encoding}"
    for key, val in exif.items():
        print("EXIF TAG", key, ExifTags.TAGS.get(key, key))
        decoded_val = info_decode(val, encoding)
        log.debug("decoded_val %s", decoded_val)
        if key in ExifTags.TAGS:
            key_name = ExifTags.TAGS[key]
            s += f"\n{key_name}: "
            if key_name == "ColorSpace":
                s += "Uncalibrated" if val == 65535 else val
            elif key_name == "ComponentsConfiguration":
                s += "Y, Cb, Cr, -" if val == b"\x01\x02\x03\x00" else str(val)
            elif key_name == "Orientation":
                s += (
                    "",
                    "Normal",
                    "FLIP_LEFT_RIGHT",
                    "ROTATE_180",
                    "FLIP_TOP_BOTTOM",
                    "TRANSPOSE",
                    "ROTATE_90",
                    "TRANSVERSE",
                    "ROTATE_270",
                )[val]
            elif key_name == "ResolutionUnit":
                s += {2: "inch", 3: "cm"}.get(val, val)
            elif key_name == "YCbCrPositioning":
                s += {
                    1: "Centered",
                }.get(val, val)
            else:
                s += f"{decoded_val}"
        else:
            s += f"\nUnknown EXIF tag {key}: {val}"

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
        # with ExifToolHelper() as et:
        #     for d in et.get_metadata(paths[path_index]):
        #         for k, v in d.items():
        #             s += f"\n{k}: {v}"
        output = subprocess.run(
            ["exiftool", ROOT.paths[ROOT.i_path]],
            capture_output=True,
            check=False,
            text=False,
        )  # text=False to avoid dead thread with uncatchable UnicodeDecodeError: 'charmap' codec can't decode byte 0x8f in position 1749: character maps to <undefined> like https://github.com/smarnach/pyexiftool/issues/20
        s += (
            output.stdout and output.stdout.decode("utf8").replace("\r", "") or ""
        ) + output.stderr.decode("utf8").replace("\r", "")
    except (
        FileNotFoundError,  # Exiftool not on PATH.
        UnicodeDecodeError,  # PyExifTool can't handle Parameters data of naughty test\00032-1238577453.png which Exiftool itself handles fine.
    ) as ex:
        log.debug("exiftool read fail: %s", ex)
    return s.strip()


def info_icc() -> str:
    """Return the ICC color profile info."""
    s = ""
    icc = ROOT.im.info.get("icc_profile")  # type: ignore
    if icc:
        p = ImageCms.ImageCmsProfile(BytesIO(icc))
        intent = ImageCms.getDefaultIntent(p)
        man = ImageCms.getProfileManufacturer(p).strip()
        model = ImageCms.getProfileModel(p).strip()
        s += f"""ICC Profile:
Copyright: {ImageCms.getProfileCopyright(p).strip()}
Description: {ImageCms.getProfileDescription(p).strip()}
Intent: {('Perceptual', 'Relative colorimetric', 'Saturation', 'Absolute colorimetric')[intent]}
isIntentSupported: {ImageCms.isIntentSupported(p, intent, 1)}"""
        if man:
            s += f"\nManufacturer: {man}"
        if model:
            s += f"\nModel: {model}"
    return s.strip()


def info_iptc() -> str:
    """Return IPTC metadata."""
    s = ""
    iptc = IptcImagePlugin.getiptcinfo(ROOT.im)
    if iptc:
        s += "IPTC:"
        for k, v in iptc.items():
            s += "\nKey:{} Value:{}".format(k, repr(v))
    return s.strip()


def info_psd() -> str:
    """Return PhotoShop Document info."""
    if "photoshop" not in ROOT.info:
        return ""
    s = "Photoshop:\n"
    for k, v in ROOT.info["photoshop"].items():
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
    if hasattr(ROOT.im, "getxmp"):
        xmp = ROOT.im.getxmp()  # type: ignore
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
    if not ROOT.show_info or CANVAS.itemcget(canvas_info, "text").startswith("C - Set"):
        info_set(ROOT.title() + info_get())
        log.debug("Showing info:\n%s", CANVAS.itemcget(canvas_info, "text"))
        info_show()
    else:
        info_hide()


def info_show():
    """Show info overlay."""
    ROOT.show_info = True
    CANVAS.lift(CANVAS.overlay)
    CANVAS.lift(canvas_info)
    scrollbars_set()


def info_hide():
    """Hide info overlay."""
    ROOT.show_info = False
    CANVAS.lower(CANVAS.overlay)
    CANVAS.lower(canvas_info)
    info_set(CANVAS.itemcget(canvas_info, "text")[:7])
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
    filename = filedialog.askopenfilename(filetypes=ROOT.SUPPORTED_FILES_READ)
    if filename:
        paths_update(None, filename)


@log_this
def path_save(event=None):
    """Save file as...."""
    if "Names" in ROOT.info:
        p = pathlib.Path(
            str(ROOT.paths[ROOT.i_path]) + "." + ROOT.info["Names"][ROOT.i_zip]
        )
    else:
        p = ROOT.paths[ROOT.i_path]

    log.debug("Image info to be saved: %s", ROOT.im.info)
    filename = filedialog.asksaveasfilename(
        initialfile=p.absolute(),
        defaultextension=p.suffix,
        filetypes=ROOT.SUPPORTED_FILES_WRITE,
    )
    if filename:
        log.info("Saving %s", filename)
        try:
            ROOT.im.save(
                filename,
                # dpi=INFO.get("dpi", b""),
                # icc_profile=INFO.get("icc_profile", b""),
                **ROOT.im.info,
                lossless=True,
                optimize=True,
                save_all=hasattr(ROOT.im, "n_frames"),  # All frames.
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
    log.debug("Sorting %s", ROOT.sort)
    if path:
        try:
            ROOT.i_path = ROOT.paths.index(pathlib.Path(path))
        except ValueError:
            pass
    elif ROOT.paths:
        path = ROOT.paths[ROOT.i_path]
    else:
        return

    for s in ROOT.sort.split(","):
        if s == "natural":
            ROOT.paths.sort(key=natural_sort)
        elif s == "ctime":
            ROOT.paths.sort(key=os.path.getmtime)
        elif s == "mtime":
            ROOT.paths.sort(key=os.path.getmtime)
        elif s == "random":
            random.shuffle(ROOT.paths)
        elif s == "size":
            ROOT.paths.sort(key=os.path.getsize)
        elif s == "string":
            ROOT.paths.sort()

    try:
        ROOT.i_path = ROOT.paths.index(pathlib.Path(path))
        im_load()
    except ValueError as ex:
        error_show("Not found: %s" % ex)


@log_this
def paths_update(event=None, path=None):
    """Update path info."""
    if not path:
        path = ROOT.paths[ROOT.i_path]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent
    log.debug("Reading %s...", p)
    ROOT.paths = list(p.glob("*"))
    log.debug("Found %s files.", len(ROOT.paths))
    log.debug("Filter?")
    paths_sort(path)


def refresh_loop():
    """Autoupdate paths."""
    if ROOT.update_interval > 0:
        paths_update()
        if hasattr(ROOT, "path_updater"):
            ROOT.after_cancel(ROOT.path_updater)
        ROOT.path_updater = ROOT.after(ROOT.update_interval, refresh_loop)


def refresh_toggle(event=None):
    """Toggle autoupdate."""
    ROOT.update_interval = -ROOT.update_interval
    if ROOT.update_interval > 0:
        toast(f"Refreshing every {ROOT.update_interval/1000:.2}s.")
        refresh_loop()
    else:
        toast("Refresh off.")


def resize_handler(event=None):
    """Handle Tk resize event."""
    new_size = ROOT.winfo_geometry().split("+", maxsplit=1)[0]
    # Resize selection?
    if ROOT.s_geo != new_size:
        ERROR_OVERLAY.config(wraplength=event.width)
        TOAST.config(wraplength=event.width)
        bb = CANVAS.bbox(canvas_info)
        CANVAS.itemconfig(canvas_info, width=event.width - 16)
        CANVAS.coords(CANVAS.im_bg, 0, 0, event.width, event.height)

        if bb != CANVAS.bbox(canvas_info):
            info_bg_update()

        if ROOT.s_geo and ROOT.fit:
            im_resize()
        else:
            scrollbars_set()
        ROOT.s_geo = new_size


def scroll(event):
    """Scroll."""
    k = event.keysym
    if k == "Left":
        CANVAS.xview_scroll(-10, "units")
    elif k == "Right":
        CANVAS.xview_scroll(10, "units")
    if k == "Up":
        CANVAS.yview_scroll(-10, "units")
    elif k == "Down":
        CANVAS.yview_scroll(10, "units")


def scrollbars_set():
    """Hide/show scrollbars."""
    try:
        x, y, x2, y2 = CANVAS.bbox(CANVAS.image_ref, canvas_info)
        w = x2 - x
        h = y2 - y
        sv = max(0, y) + h > ROOT.winfo_height()
        # Vertical scrollbar causing horizontal scrollbar.
        sh = max(0, x) + w > ROOT.winfo_width() - 16 * sv
        # Horizontal scrollbar causing vertical scrollbar.
        sv = max(0, y) + h > ROOT.winfo_height() - 16 * sh
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
        CANVAS.config(scrollregion=scrollregion)
        if ROOT.i_path != ROOT.i_scroll:
            CANVAS.xview_moveto(0)
            CANVAS.yview_moveto(0)
            ROOT.i_scroll = ROOT.i_path
    except TypeError as ex:
        log.error(ex)


def set_bg(event=None):
    """Set background color."""
    ROOT.i_bg += 1
    if ROOT.i_bg >= len(BG_COLORS):
        ROOT.i_bg = 0
    bg = BG_COLORS[ROOT.i_bg]
    ROOT.config(bg=bg)
    CANVAS.config(bg=bg)
    CANVAS.itemconfig(CANVAS.im_bg, fill=bg)
    ERROR_OVERLAY.config(bg=bg)
    MENU.config(bg=bg, fg="black" if ROOT.i_bg == len(BG_COLORS) - 1 else "white")


@log_this
def set_order(event=None):
    """Set order."""
    i = SORTS.index(ROOT.sort) if ROOT.sort in SORTS else -1
    i = (i + 1) % len(SORTS)
    ROOT.sort = SORTS[i]
    s = "Sort: " + ROOT.sort
    log.info(s)
    toast(s)
    paths_sort()


def set_stats(path):
    """Set stats."""
    stats = os.stat(path)
    log.debug("Stat: %s", stats)
    ROOT.info = {
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

    ROOT.SUPPORTED_FILES_READ = [
        (
            "All supported files",
            " ".join(sorted(list(k for k, v in exts.items() if v in Image.OPEN))),
        ),
        ("All files", "*"),
        ("Archives", ".eml .mht .mhtml .zip"),
        *sorted((k, v) for k, v in type_exts.items() if k in Image.OPEN),
    ]
    ROOT.SUPPORTED_FILES_WRITE = [
        (
            "All supported files",
            " ".join(sorted(list(k for k, v in exts.items() if v in Image.SAVE))),
        ),
        *sorted((k, v) for k, v in type_exts.items() if k in Image.SAVE),
    ]

    log.debug("Supports %s", ", ".join(s[1:].upper() for s in sorted(list(exts))))
    log.debug(
        "Open: %s",
        ", ".join(
            sorted(
                [k[1:].upper() for k, v in exts.items() if v in Image.OPEN]
                + ["EML", "MHT", "MHTML", "SVG", "SVGZ", "ZIP"]
            )
        ),
    )
    log.debug(
        "Save: %s",
        ", ".join(sorted(k[1:].upper() for k, v in exts.items() if v in Image.SAVE)),
    )
    log.debug(
        "Save all frames: %s",
        ", ".join(
            sorted(k[1:].upper() for k, v in exts.items() if v in Image.SAVE_ALL)
        ),
    )


def quality_set(event=None):
    """Set resize quality."""
    i = RESIZE_QUALITY.index(ROOT.quality)
    i += -1 if event and event.keysym == "Q" else 1
    if i >= len(RESIZE_QUALITY):
        i = 0
    if i < 0:
        i = len(RESIZE_QUALITY) - 1
    ROOT.quality = RESIZE_QUALITY[i]
    toast(f"Quality: {Image.Resampling(ROOT.quality).name}")
    im_resize()


@log_this
def set_verbosity(event=None):
    """Set verbosity."""
    ROOT.verbosity -= 10
    if ROOT.verbosity < 10:
        ROOT.verbosity = logging.CRITICAL

    logging.basicConfig(level=ROOT.verbosity)  # Show up in nested shells in Windows 11.
    log.setLevel(ROOT.verbosity)
    s = "Log level %s" % logging.getLevelName(log.getEffectiveLevel())
    toast(s)
    print(s)


def slideshow_run(event=None):
    """Run slideshow."""
    if ROOT.b_slideshow:
        browse()
        ROOT.after(ROOT.slideshow_pause, slideshow_run)


def slideshow_toggle(event=None):
    """Toggle slideshow."""
    ROOT.b_slideshow = not ROOT.b_slideshow
    if ROOT.b_slideshow:
        toast("Starting slideshow.")
        ROOT.after(ROOT.slideshow_pause, slideshow_run)
    else:
        toast("Stopping slideshow.")


def toast(msg: str, ms: int = 2000, fg="#00FF00"):
    """Temporarily show a status message."""
    TOAST.config(text=msg, fg=fg)
    TOAST.lift()
    if hasattr(ROOT, "toast_timer"):
        ROOT.after_cancel(ROOT.toast_timer)
    ROOT.toast_timer = ROOT.after(ms, TOAST.lower)


@log_this
def transpose_set(event=None):
    """Transpose image."""
    ROOT.transpose_type += -1 if event and event.keysym == "T" else 1
    if ROOT.transpose_type >= len(Transpose):
        ROOT.transpose_type = -1
    if ROOT.transpose_type < -1:
        ROOT.transpose_type = len(Transpose) - 1

    if ROOT.transpose_type >= 0:
        toast(f"Transpose: {Transpose(ROOT.transpose_type).name}")
    else:
        toast("Transpose: Normal")
    im_resize()


@log_this
def fit_handler(event=None):
    """Resize type to fit window."""
    ROOT.fit = (ROOT.fit + 1) % len(Fits)
    toast(str(Fits(ROOT.fit)))
    im_resize()


@log_this
def fullscreen_toggle(event=None):
    """Toggle fullscreen."""
    if not ROOT.overrideredirect():
        ROOT.old_geometry = ROOT.geometry()
        ROOT.old_state = ROOT.state()
        log.debug("Old widow geometry: %s", ROOT.old_geometry)
        ROOT.overrideredirect(True)
        ROOT.state("zoomed")
    else:
        ROOT.overrideredirect(False)
        ROOT.state(ROOT.old_state)
        if ROOT.state() == "normal":
            new_geometry = (
                # Happens when window wasn't visible yet.
                "300x200+300+200"
                if ROOT.old_geometry.startswith("1x1")
                else ROOT.old_geometry
            )
            log.debug("Restoring geometry: %s", new_geometry)
            ROOT.geometry(new_geometry)
    # Keeps using display 1
    # root.attributes("-fullscreen", not root.attributes("-fullscreen"))


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
        ROOT.im_scale *= 1.1
    elif k == "minus":
        ROOT.im_scale *= 0.9
    else:
        ROOT.im_scale = 1
    ROOT.im_scale = max(SCALE_MIN, min(ROOT.im_scale, SCALE_MAX))
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
        ROOT.f_text_scale *= 1.1
    elif k == "minus":
        ROOT.f_text_scale *= 0.9
    else:
        ROOT.f_text_scale = 1
    ROOT.f_text_scale = max(0.1, min(ROOT.f_text_scale, 20))
    new_font_size = int(FONT_SIZE * ROOT.f_text_scale)
    new_font_size = max(1, min(new_font_size, 200))
    log.info("Text scale: %s New font size: %s", ROOT.f_text_scale, new_font_size)

    ERROR_OVERLAY.config(font=("Consolas", new_font_size))
    TOAST.config(font=("Consolas", new_font_size * 2))
    CANVAS.itemconfig(canvas_info, font=("Consolas", new_font_size))
    info_bg_update()


ROOT = TkinterDnD.Tk()  # notice - use this instead of tk.Tk()
ROOT.drop_target_register(DND_FILES)
ROOT.dnd_bind("<<Drop>>", drop_handler)
ROOT.show_info = False
ROOT.title(TITLE)
root_w, root_h = int(ROOT.winfo_screenwidth() * 0.75), int(
    ROOT.winfo_screenheight() * 0.75
)
geometry = f"{root_w}x{root_h}+{int(root_w * 0.125)}+{int(root_h * 0.125)}"
ROOT.geometry(geometry)

TOAST = tkinter.Label(
    ROOT,
    text="status",
    font=("Consolas", FONT_SIZE * 2),
    fg="#00FF00",
    bg="black",
    wraplength=root_w,
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
CANVAS.overlay = CANVAS.create_image(0, 0, anchor="nw")  # type: ignore
canvas_info = CANVAS.create_text(
    1,  # If 0, bbox starts at -1.
    0,
    anchor="nw",
    text="status",
    fill="#ff0",
    font=("Consolas", FONT_SIZE),
    width=root_w,
)
CANVAS.im_bg = CANVAS.create_rectangle(0, 0, root_w, root_h, fill="black", width=0)  # type: ignore
CANVAS.image_ref = CANVAS.create_image(root_w // 2, root_h // 2, anchor="center")  # type: ignore
ROOT.update()
scrollx = tkinter.Scrollbar(ROOT, orient="horizontal", command=CANVAS.xview)
scrollx.place(x=0, y=1, relwidth=1, relx=1, rely=1, anchor="se")
scrolly = tkinter.Scrollbar(ROOT, command=CANVAS.yview)
scrolly.place(x=1, y=0, relheight=1, relx=1, rely=1, anchor="se")
CANVAS.config(
    xscrollcommand=scrollx.set,
    xscrollincrement=1,
    yscrollcommand=scrolly.set,
    yscrollincrement=1,
)
ERROR_OVERLAY = tkinter.Label(
    ROOT,
    compound="center",
    fg="red",
    font=("Consolas", FONT_SIZE),
    width=root_w,
    height=root_h,
    wraplength=root_w,
)
ERROR_OVERLAY.place(x=0, y=0, relwidth=1, relheight=1)

# root.bind_all("<Key>", debug_keys)
binds = [
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
    (
        browse,
        "x Left Right Up Down BackSpace space MouseWheel Button-4 Button-5 Home End Key-1",
    ),
    (set_order, "o"),
    (delete_file, "d Delete"),
    (path_open, "p"),
    (path_save, "s"),
    (paths_update, "u F5"),
    (refresh_toggle, "U"),
    (clipboard_copy, "Control-c Control-Insert"),
    (clipboard_paste, "Control-v Shift-Insert"),
    (set_verbosity, "v"),
    (select, "B1-Motion"),
    (drag, "B2-Motion"),
    (drag_begin, "ButtonPress"),
    (drag_end, "ButtonRelease"),
    (menu_show, "Button-3"),  # Or rather tk_popup in Ubuntu?
    (lines_toggle, "l"),
    (resize_handler, "Configure"),
]

MENU = tkinter.Menu(ROOT, tearoff=0)


def main(args):
    """Main function."""
    ROOT.b_animate = True
    ROOT.b_lines = False
    ROOT.b_slideshow = False
    ROOT.i_bg = -1
    ROOT.i_path = 0
    ROOT.i_scroll = -1
    ROOT.i_zip = 0
    ROOT.im_scale = 1.0
    ROOT.info = {}
    ROOT.f_text_scale = 1.0
    ROOT.s_geo = ""
    ROOT.transpose_type = -1
    ROOT.update_interval = -4000
    if args.verbose:
        ROOT.verbosity = VERBOSITY_LEVELS[
            min(len(VERBOSITY_LEVELS) - 1, 1 + args.verbose)
        ]
        set_verbosity()

    log.debug("Args: %s", args)
    ROOT.paths = []

    set_supported_files()

    ROOT.fit = args.resize or 0
    ROOT.quality = RESIZE_QUALITY[args.quality]
    ROOT.transpose_type = args.transpose

    # Needs visible window so wait for mainloop.
    ROOT.after(50, paths_update, None, args.path)

    if args.fullscreen:
        ROOT.after(100, fullscreen_toggle)

    if args.geometry:
        ROOT.geometry(args.geometry)

    ROOT.sort = args.order if args.order else "natural"

    if args.update:
        ROOT.update_interval = args.update
        ROOT.after(1000, refresh_loop)

    if args.slideshow:
        ROOT.slideshow_pause = args.slideshow
        slideshow_toggle()
    else:
        ROOT.slideshow_pause = 4000

    for b in binds:
        func = b[0]
        for event in b[1].split(" "):
            ROOT.bind(f"<{event}>", func)

    for fun, keys in binds:
        if fun in (
            browse_frame,
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

    set_bg()
    ROOT.mainloop()


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
