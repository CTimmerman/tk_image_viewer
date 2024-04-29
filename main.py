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
    root.b_animate = not root.b_animate
    if root.b_animate:
        toast("Starting animation.")
        im_resize(root.b_animate)
    else:
        s = (
            "Stopping animation."
            + f" Frame {1 + (1 + root.im_frame) % root.im.n_frames}/{root.im.n_frames}"
            if hasattr(root.im, "n_frames")
            else ""
        )
        log.info(s)
        toast(s)


@log_this
def browse(event=None):
    """Browse."""
    new_index = root.i_path

    if "Names" in root.info:
        new_index = root.i_zip

    k = event.keysym if event else "Next"
    if k in ("1", "Home"):
        new_index = 0
    elif k == "End":
        new_index = root.i_path - 1
    elif k == "x":
        new_index = random.randint(0, len(root.paths) - 1)
    elif (
        k in ("Left", "Up", "Button-4", "BackSpace")
        or event
        and (event.num == 4 or event.delta > 0)
    ):
        new_index -= 1
    else:
        new_index += 1

    if "Names" in root.info:
        if new_index < 0:
            new_index = root.i_path - 1
        elif new_index >= len(root.info["Names"]):
            new_index = root.i_path + 1
        else:
            root.i_zip = new_index
            im_load()
            return

    if new_index < 0:
        new_index = len(root.paths) - 1
    if new_index >= len(root.paths):
        new_index = 0

    root.i_path = new_index
    root.i_zip = 0
    im_load()


def browse_frame(event=None):
    """Browse animation frames."""
    if not hasattr(root.im, "n_frames"):
        toast("No frames.")
        return
    n = root.im.n_frames - 1
    k = event.keysym
    if k == "comma":
        root.im_frame -= 1
        if root.im_frame < 0:
            root.im_frame = n
    else:
        root.im_frame += 1
        if root.im_frame > n:
            root.im_frame = 0

    root.im.seek(root.im_frame)
    im_resize()
    toast(f"Frame {1 + root.im_frame}/{1 + n}", 1000)


def clipboard_copy(event=None):
    """Copy info to clipboard."""
    pyperclip.copy(canvas.itemcget(canvas_info, "text"))
    toast("Copied info.")


def clipboard_paste(event=None):
    """Paste image from clipboard."""
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
        root.paths = [pathlib.Path(s) for s in im]
        log.debug("Set paths to %s", root.paths)
        root.i_path = 0
        im_load()
        return
    root.im = im
    root.info = {"Pasted": time.ctime()}
    root.i_path = 0
    root.paths = ["pasted"]
    im_resize(root.im)


@log_this
def close(event=None):
    """Close fullscreen or app."""
    if root.overrideredirect():
        fullscreen_toggle()
    else:
        root.quit()


@log_this
def debug_keys(event=None):
    """Show all keys."""


def delete_file(event=None):
    """Delete file. Bypasses Trash."""
    path = root.paths[root.i_path]
    msg = f"Delete? {path}"
    log.warning(msg)
    answer = messagebox.showwarning(
        "Delete File", f"Permanently delete {path}?", type=messagebox.YESNO
    )
    if answer == "yes":
        log.warning("Deleting %s", path)
        os.remove(path)
        paths_update()


def drag_begin(event):
    """Keep drag begin pos for delta move."""
    if event.widget != canvas:
        return
    canvas.dragx = canvas.canvasx(event.x)
    canvas.dragy = canvas.canvasy(event.y)
    canvas.config(cursor="tcross" if event.num == 1 else "fleur")


def drag_end(event):
    """End drag."""
    if event.widget != canvas:
        return
    canvas.config(cursor="")
    if (
        canvas.canvasx(event.x) == canvas.dragx
        and canvas.canvasy(event.y) == canvas.dragy
    ):
        lines_toggle(off=True)


def drag(event):
    """Drag image."""
    if event.widget != canvas:
        return

    evx, evy = canvas.canvasx(event.x), canvas.canvasy(event.y)
    x, y, x2, y2 = canvas.bbox(canvas.image_ref)
    w = x2 - x
    h = y2 - y
    dx, dy = int(evx - canvas.dragx), int(evy - canvas.dragy)
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
    canvas.dragx, canvas.dragy = evx, evy


def select(event):
    """Select area."""
    if event.widget != canvas:
        return
    lines_toggle(on=True)
    x = canvas.dragx
    y = canvas.dragy
    x2 = canvas.canvasx(event.x)
    y2 = canvas.canvasy(event.y)
    canvas.coords(canvas.lines[0], x, y, x2, y, x, y2, x2, y2)
    canvas.coords(canvas.lines[1], x, y2, x, y, x2, y2, x2, y)


@log_this
def drop_handler(event):
    """Handles dropped files."""
    log.debug("Dropped %r", event.data)
    root.paths = [
        pathlib.Path(line.strip('"'))
        for line in re.findall("{(.+?)}" if "{" in event.data else "[^ ]+", event.data)
    ]  # Windows 11.
    if isinstance(root.paths, list):
        log.debug("Set paths to %s", root.paths)
        root.i_path = 0
        im_load()


def error_show(msg: str):
    """Show error."""
    root.title(msg + " - " + TITLE)
    log.error(msg)
    ERROR_OVERLAY.config(text=msg)
    ERROR_OVERLAY.lift()
    info_set(msg)  # To copy.
    root.last_index = -1  # To refresh image info.


def help_toggle(event=None):
    """Toggle help."""
    if root.show_info and canvas.itemcget(canvas_info, "text").startswith("C - Set"):
        info_hide()
    else:
        lines = []
        for fun, keys in binds:
            if keys in ("ButtonPress", "ButtonRelease", "Configure"):
                continue
            lines.append(
                re.sub(
                    "((^|-)[a-z])",
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
    canvas.itemconfig(canvas_info, text=msg)  # type: ignore
    info_bg_update()


def info_bg_update():
    """Update info overlay."""
    x1, y1, x2, y2 = canvas.bbox(canvas_info)
    canvas.overlay_tkim = ImageTk.PhotoImage(  # type: ignore
        Image.new("RGBA", (x2 - x1, y2 - y1), "#000a")
    )
    canvas.itemconfig(canvas.overlay, image=canvas.overlay_tkim)  # type: ignore
    canvas.coords(canvas.im_bg, x1, y1, x2, y2)


def lines_toggle(event=None, on=None, off=None):
    """Toggle line overlay."""
    root.b_lines = True if on else False if off else not root.b_lines  # NOSONAR
    if not root.b_lines and canvas.lines:
        for line in canvas.lines:
            canvas.delete(line)
        canvas.lines = []
    if root.b_lines and not canvas.lines:
        w = root.winfo_width() - 1
        h = root.winfo_height() - 1
        canvas.lines.append(canvas.create_line(0, 0, w, 0, 0, h, w, h, fill="#f00"))  # type: ignore
        canvas.lines.append(canvas.create_line(0, h, 0, 0, w, h, w, 0, fill="#f00"))  # type: ignore


def load_mhtml(path):
    """Load EML/MHT/MHTML."""
    with open(path, "r", encoding="utf8") as f:
        mhtml = f.read()
    boundary = re.search('boundary="(.+)"', mhtml).group(1)
    parts = mhtml.split(boundary)[1:-1]
    root.info["Names"] = []
    new_parts = []
    for p in parts:
        meta, data = p.split("\n\n", maxsplit=1)
        m = meta.lower()
        if "\ncontent-transfer-encoding: base64" not in m:
            continue
        if "\ncontent-type:" in m and "\ncontent-type: image" not in m:
            continue
        name = sorted(meta.strip().split("\n"))[0].split("/")[-1]
        root.info["Names"].append(name)
        new_parts.append(data)
    data = new_parts[root.i_zip]
    try:
        im_file = BytesIO(base64.standard_b64decode(data.rstrip()))
        root.im = Image.open(im_file)
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
    root.im = Image.open(bf)


def load_zip(path):
    """Load a zip file."""
    with zipfile.ZipFile(path, "r") as zf:
        names = zf.namelist()
        root.info["Names"] = names
        log.debug("Loading name index %s", root.i_zip)
        # pylint: disable=consider-using-with
        root.im = Image.open(zf.open(names[root.i_zip]))


def im_load(path=None):
    """Load image."""
    if not path and root.paths:
        path = root.paths[root.i_path]
    else:
        return

    msg = f"{root.i_path+1}/{len(root.paths)}"
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
                root.im = Image.open(path)
        log.debug("Cached %s PIL_IMAGE", root.im.size)
        root.im_frame = 0
        if hasattr(root.im, "n_frames"):
            root.info["Frames"] = root.im.n_frames
        root.info.update(**root.im.info)
        for k, v in root.info.items():
            log.debug(
                "%s: %s",
                k,
                str(v)[:80] + "..." if len(str(v)) > 80 else v,
            )
        im_resize(root.b_animate)
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
        root.im = None
        msg = f"{msg} {err_msg} {path}"
        error_show(msg)
        raise


def get_fit_ratio(im_w, im_h):
    """Get fit ratio."""
    ratio = 1.0
    w = root.winfo_width()
    h = root.winfo_height()
    if (
        ((root.fit == Fits.ALL) and (im_w != w or im_h != h))
        or ((root.fit == Fits.BIG) and (im_w > w or im_h > h))
        or ((root.fit == Fits.SMALL) and (im_w < w and im_h < h))
    ):
        ratio = min(w / im_w, h / im_h)
    return ratio


def im_fit(im):
    """Fit image to window."""
    w, h = im.size
    ratio = get_fit_ratio(w, h)
    if ratio != 1.0:  # NOSONAR
        im = im.resize((int(w * ratio), int(h * ratio)), root.quality)
    return im


def im_scale(im):
    """Scale image."""
    im_w, im_h = im.size
    ratio = root.im_scale * get_fit_ratio(im_w, im_h)
    try:
        new_w = int(ratio * im_w)
        new_h = int(ratio * im_h)
        if new_w < 1 or new_h < 1:
            log.error("Too small. Scaling up.")
            root.im_scale = max(SCALE_MIN, min(root.im_scale * 1.1, SCALE_MAX))
            im = im_scale(im)
        else:
            im = root.im.resize((new_w, new_h), root.quality)
    except MemoryError as ex:
        log.error("Out of memory. Scaling down. %s", ex)
        root.im_scale = max(SCALE_MIN, min(root.im_scale * 0.9, SCALE_MAX))

    return im


def im_resize(loop=False):
    """Resize image."""
    if not root.im:
        return

    im = root.im.copy()

    if root.fit:
        im = im_fit(root.im)

    if root.im_scale != 1:
        im = im_scale(root.im)

    if root.transpose_type != -1:
        log.debug("Transposing %s", Transpose(root.transpose_type))
        im = im.transpose(root.transpose_type)

    im_show(im)

    if loop and hasattr(root.im, "n_frames") and root.im.n_frames > 1:
        root.im_frame = (root.im_frame + 1) % root.im.n_frames
        try:
            root.im.seek(root.im_frame)
        except EOFError as ex:
            log.error("IMAGE EOF. %s", ex)
        duration = (root.info["duration"] or 100) if "duration" in root.info else 100
        if hasattr(root, "animation"):
            root.after_cancel(root.animation)
        root.animation = root.after(duration, im_resize, root.b_animate)


def im_show(im):
    """Show PIL image in Tk image widget."""
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
        root.im_scale = max(SCALE_MIN, min(root.im_scale * 0.9, SCALE_MAX))
        return

    zip_info = (
        f" {root.i_zip + 1}/{len(root.info['Names'])} {root.info['Names'][root.i_zip]}"
        if "Names" in root.info
        else ""
    )
    msg = (
        f"{root.i_path+1}/{len(root.paths)}{zip_info} {'%sx%s' % root.im.size}"
        f" @ {'%sx%s' % im.size} {root.paths[root.i_path]}"
    )
    root.title(msg + " - " + TITLE)
    if root.show_info and (
        not hasattr(root, "last_index") or root.last_index != root.i_path
    ):
        root.last_index = root.i_path
        info_set(msg + info_get())
    scrollbars_set()


def info_decode(b: bytes, encoding: str) -> str:
    """Decodes a sequence of bytes, as stated by the method signature."""
    if not isinstance(b, bytes):
        return str(b)
    print("BYTES!", str(b[:80]), "->", str(b.replace(b"\0", b"")))
    if b.startswith(b"ASCII\0\0\0"):
        return str(b[8:])
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
    return str(b.replace(b"\0", b""))


def info_get() -> str:
    """Get image info."""
    msg = ""
    for k, v in root.info.items():
        if k in ("exif", "icc_profile", "photoshop", "XML:com.adobe.xmp"):
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
    if not root.im:
        return msg

    msg += f"\nFormat: {root.im.format}"
    try:
        msg += f"\nMIME type: {root.im.get_format_mimetype()}"  # type: ignore
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
    if not hasattr(root.im, "_getexif"):
        return ""

    exif = root.im._getexif()  # type: ignore  # pylint: disable=protected-access
    if not exif:
        return ""
    log.debug("Got exif dict: %s", exif)
    log.debug("im.exif bytes: %s", root.info["exif"].replace(b"\0", b""))
    encoding = "utf_16_be" if b"MM" in root.info["exif"][:8] else "utf_16_le"
    log.debug("Encoding: %s", encoding)
    s = f"EXIF: {encoding}"
    for key, val in exif.items():
        print("EXIF TAG", key, ExifTags.TAGS.get(key, key))
        decoded_val = info_decode(val, encoding)
        log.debug("decoded_val %s", decoded_val)
        if key in ExifTags.TAGS:
            s += f"\n{ExifTags.TAGS[key]}: {decoded_val}"
            if ExifTags.TAGS[key] == "Orientation":
                s += (
                    " "
                    + (
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
                )
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
            ["exiftool", root.paths[root.i_path]],
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
    icc = root.im.info.get("icc_profile")  # type: ignore
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
    iptc = IptcImagePlugin.getiptcinfo(root.im)
    if iptc:
        s += "IPTC:"
        for k, v in iptc.items():
            s += "\nKey:{} Value:{}".format(k, repr(v))
    return s.strip()


def info_psd() -> str:
    """Return PhotoShop Document info."""
    if "photoshop" not in root.info:
        return ""
    s = "Photoshop:\n"
    for k, v in root.info["photoshop"].items():
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
    if hasattr(root.im, "getxmp"):
        xmp = root.im.getxmp()  # type: ignore
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
    if not root.show_info or canvas.itemcget(canvas_info, "text").startswith("C - Set"):
        info_set(root.title() + info_get())
        log.debug("Showing info:\n%s", canvas.itemcget(canvas_info, "text"))
        info_show()
    else:
        info_hide()


def info_show():
    """Show info overlay."""
    root.show_info = True
    canvas.lift(canvas.overlay)
    canvas.lift(canvas_info)
    scrollbars_set()


def info_hide():
    """Hide info overlay."""
    root.show_info = False
    canvas.lower(canvas.overlay)
    canvas.lower(canvas_info)
    info_set(canvas.itemcget(canvas_info, "text")[:7])
    scrollbars_set()


def menu_show(event):
    """Show menu."""
    menu.post(event.x_root, event.y_root)


def natural_sort(s):
    """Sort by number and string."""
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", str(s))]


@log_this
def path_open(event=None):
    """Pick a file to open...."""
    filename = filedialog.askopenfilename(filetypes=root.SUPPORTED_FILES_READ)
    if filename:
        paths_update(None, filename)


@log_this
def path_save(event=None):
    """Save file as...."""
    if "Names" in root.info:
        p = pathlib.Path(
            str(root.paths[root.i_path]) + "." + root.info["Names"][root.i_zip]
        )
    else:
        p = root.paths[root.i_path]

    log.debug("Image info to be saved: %s", root.im.info)
    filename = filedialog.asksaveasfilename(
        initialfile=p.absolute(),
        defaultextension=p.suffix,
        filetypes=root.SUPPORTED_FILES_WRITE,
    )
    if filename:
        log.info("Saving %s", filename)
        try:
            root.im.save(
                filename,
                # dpi=INFO.get("dpi", b""),
                # icc_profile=INFO.get("icc_profile", b""),
                **root.im.info,
                lossless=True,
                optimize=True,
                save_all=hasattr(root.im, "n_frames"),  # All frames.
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
    log.debug("Sorting %s", root.sort)
    if path:
        try:
            root.i_path = root.paths.index(pathlib.Path(path))
        except ValueError:
            pass
    elif root.paths:
        path = root.paths[root.i_path]
    else:
        return

    for s in root.sort.split(","):
        if s == "natural":
            root.paths.sort(key=natural_sort)
        elif s == "ctime":
            root.paths.sort(key=os.path.getmtime)
        elif s == "mtime":
            root.paths.sort(key=os.path.getmtime)
        elif s == "random":
            random.shuffle(root.paths)
        elif s == "size":
            root.paths.sort(key=os.path.getsize)
        elif s == "string":
            root.paths.sort()

    try:
        root.i_path = root.paths.index(pathlib.Path(path))
        im_load()
    except ValueError as ex:
        error_show("Not found: %s" % ex)


@log_this
def paths_update(event=None, path=None):
    """Update path info."""
    if not path:
        path = root.paths[root.i_path]

    p = pathlib.Path(path)
    if not p.is_dir():
        p = p.parent
    log.debug("Reading %s...", p)
    root.paths = list(p.glob("*"))
    log.debug("Found %s files.", len(root.paths))
    log.debug("Filter?")
    paths_sort(path)


def refresh_loop():
    """Autoupdate paths."""
    if root.update_interval > 0:
        paths_update()
        if hasattr(root, "path_updater"):
            root.after_cancel(root.path_updater)
        root.path_updater = root.after(root.update_interval, refresh_loop)


def refresh_toggle(event=None):
    """Toggle autoupdate."""
    root.update_interval = -root.update_interval
    if root.update_interval > 0:
        toast(f"Refreshing every {root.update_interval/1000:.2}s.")
        refresh_loop()
    else:
        toast("Refresh off.")


def resize_handler(event=None):
    """Handle Tk resize event."""
    new_size = root.winfo_geometry().split("+", maxsplit=1)[0]
    # Resize selection?
    if root.s_geo != new_size:
        ERROR_OVERLAY.config(wraplength=event.width)
        TOAST.config(wraplength=event.width)
        bb = canvas.bbox(canvas_info)
        canvas.itemconfig(canvas_info, width=event.width - 16)
        canvas.coords(canvas.im_bg, 0, 0, event.width, event.height)

        if bb != canvas.bbox(canvas_info):
            info_bg_update()

        if root.s_geo and root.fit:
            im_resize()
        else:
            scrollbars_set()
        root.s_geo = new_size


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
        if root.i_path != root.i_scroll:
            canvas.xview_moveto(0)
            canvas.yview_moveto(0)
            root.i_scroll = root.i_path
    except TypeError as ex:
        log.error(ex)


def set_bg(event=None):
    """Set background color."""
    root.i_bg += 1
    if root.i_bg >= len(BG_COLORS):
        root.i_bg = 0
    bg = BG_COLORS[root.i_bg]
    root.config(bg=bg)
    canvas.config(bg=bg)
    canvas.itemconfig(canvas.im_bg, fill=bg)
    ERROR_OVERLAY.config(bg=bg)
    menu.config(bg=bg, fg="black" if root.i_bg == len(BG_COLORS) - 1 else "white")


@log_this
def set_order(event=None):
    """Set order."""
    i = SORTS.index(root.sort) if root.sort in SORTS else -1
    i = (i + 1) % len(SORTS)
    root.sort = SORTS[i]
    s = "Sort: " + root.sort
    log.info(s)
    toast(s)
    paths_sort()


def set_stats(path):
    """Set stats."""
    stats = os.stat(path)
    log.debug("Stat: %s", stats)
    root.info = {
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

    root.SUPPORTED_FILES_READ = [
        (
            "All supported files",
            " ".join(sorted(list(k for k, v in exts.items() if v in Image.OPEN))),
        ),
        ("All files", "*"),
        ("Archives", ".eml .mht .mhtml .zip"),
        *sorted((k, v) for k, v in type_exts.items() if k in Image.OPEN),
    ]
    root.SUPPORTED_FILES_WRITE = [
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


@log_this
def quality_set(event=None):
    """Set resize quality."""
    i = RESIZE_QUALITY.index(root.quality)
    i += -1 if event and event.keysym == "Q" else 1
    if i >= len(RESIZE_QUALITY):
        i = 0
    if i < 0:
        i = len(RESIZE_QUALITY) - 1
    root.quality = RESIZE_QUALITY[i]
    toast(f"Quality: {Image.Resampling(root.quality).name}")
    im_resize()


@log_this
def set_verbosity(event=None):
    """Set verbosity."""
    root.verbosity -= 10
    if root.verbosity < 10:
        root.verbosity = logging.CRITICAL

    logging.basicConfig(level=root.verbosity)  # Show up in nested shells in Windows 11.
    log.setLevel(root.verbosity)
    s = "Log level %s" % logging.getLevelName(log.getEffectiveLevel())
    toast(s)
    print(s)


def slideshow_run(event=None):
    """Run slideshow."""
    if root.b_slideshow:
        browse()
        root.after(root.slideshow_pause, slideshow_run)


def slideshow_toggle(event=None):
    """Toggle slideshow."""
    root.b_slideshow = not root.b_slideshow
    if root.b_slideshow:
        toast("Starting slideshow.")
        root.after(root.slideshow_pause, slideshow_run)
    else:
        toast("Stopping slideshow.")


def toast(msg: str, ms: int = 2000, fg="#00FF00"):
    """Temporarily show a status message."""
    TOAST.config(text=msg, fg=fg)
    TOAST.lift()
    if hasattr(root, "toast_timer"):
        root.after_cancel(root.toast_timer)
    root.toast_timer = root.after(ms, TOAST.lower)


@log_this
def transpose_set(event=None):
    """Transpose image."""
    root.transpose_type += -1 if event and event.keysym == "T" else 1
    if root.transpose_type >= len(Transpose):
        root.transpose_type = -1
    if root.transpose_type < -1:
        root.transpose_type = len(Transpose) - 1

    if root.transpose_type >= 0:
        toast(f"Transpose: {Transpose(root.transpose_type).name}")
    else:
        toast("Transpose: Normal")
    im_resize()


@log_this
def fit_handler(event=None):
    """Resize type to fit window."""
    root.fit = (root.fit + 1) % len(Fits)
    toast(str(Fits(root.fit)))
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
        root.im_scale *= 1.1
    elif k == "minus":
        root.im_scale *= 0.9
    else:
        root.im_scale = 1
    root.im_scale = max(SCALE_MIN, min(root.im_scale, SCALE_MAX))
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
        root.f_text_scale *= 1.1
    elif k == "minus":
        root.f_text_scale *= 0.9
    else:
        root.f_text_scale = 1
    root.f_text_scale = max(0.1, min(root.f_text_scale, 20))
    new_font_size = int(FONT_SIZE * root.f_text_scale)
    new_font_size = max(1, min(new_font_size, 200))
    log.info("Text scale: %s New font size: %s", root.f_text_scale, new_font_size)

    ERROR_OVERLAY.config(font=("Consolas", new_font_size))
    TOAST.config(font=("Consolas", new_font_size * 2))
    canvas.itemconfig(canvas_info, font=("Consolas", new_font_size))
    info_bg_update()


root = TkinterDnD.Tk()  # notice - use this instead of tk.Tk()
root.drop_target_register(DND_FILES)
root.dnd_bind("<<Drop>>", drop_handler)
root.show_info = False
root.title(TITLE)
root_w, root_h = int(root.winfo_screenwidth() * 0.75), int(
    root.winfo_screenheight() * 0.75
)
geometry = f"{root_w}x{root_h}+{int(root_w * 0.125)}+{int(root_h * 0.125)}"
root.geometry(geometry)

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

canvas = tkinter.Canvas(bg="blue", borderwidth=0, highlightthickness=0, relief="flat")
canvas.lines = []  # type: ignore
canvas.place(x=0, y=0, relwidth=1, relheight=1)
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
canvas.im_bg = canvas.create_rectangle(0, 0, root_w, root_h, fill="black", width=0)  # type: ignore
canvas.image_ref = canvas.create_image(root_w // 2, root_h // 2, anchor="center")  # type: ignore
root.update()
scrollx = tkinter.Scrollbar(root, orient="horizontal", command=canvas.xview)
scrollx.place(x=0, y=1, relwidth=1, relx=1, rely=1, anchor="se")
scrolly = tkinter.Scrollbar(root, command=canvas.yview)
scrolly.place(x=1, y=0, relheight=1, relx=1, rely=1, anchor="se")
canvas.config(
    xscrollcommand=scrollx.set,
    xscrollincrement=1,
    yscrollcommand=scrolly.set,
    yscrollincrement=1,
)
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

menu = tkinter.Menu(root, tearoff=0)


def main(args):
    """Main function."""
    root.b_animate = True
    root.b_lines = False
    root.b_slideshow = False
    root.i_bg = -1
    root.i_path = 0
    root.i_scroll = -1
    root.i_zip = 0
    root.im_scale = 1.0
    root.info = {}
    root.f_text_scale = 1.0
    root.s_geo = ""
    root.transpose_type = -1
    root.update_interval = -4000
    if args.verbose:
        root.verbosity = VERBOSITY_LEVELS[
            min(len(VERBOSITY_LEVELS) - 1, 1 + args.verbose)
        ]
        set_verbosity()

    log.debug("Args: %s", args)
    root.paths = []

    set_supported_files()

    root.fit = args.resize or 0
    root.quality = RESIZE_QUALITY[args.quality]
    root.transpose_type = args.transpose

    # Needs visible window so wait for mainloop.
    root.after(50, paths_update, None, args.path)

    if args.fullscreen:
        root.after(100, fullscreen_toggle)

    if args.geometry:
        root.geometry(args.geometry)

    root.sort = args.order if args.order else "natural"

    if args.update:
        root.update_interval = args.update
        root.after(1000, refresh_loop)

    if args.slideshow:
        root.slideshow_pause = args.slideshow
        slideshow_toggle()
    else:
        root.slideshow_pause = 4000

    for b in binds:
        func = b[0]
        for event in b[1].split(" "):
            root.bind(f"<{event}>", func)

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
            menu.add_command(label=lbl, command=fun, underline=len(lbl) - 2)
        else:
            menu.add_command(label=fun.__doc__[:-1].title(), command=fun)

    set_bg()
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
