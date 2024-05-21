"""Metadata functions.
2024-05-13 Refactored by Cees Timmerman.
"""

# pylint: disable=comparison-with-callable, line-too-long, multiple-imports, too-many-branches
import logging, re, subprocess  # noqa: E401
from io import BytesIO
from typing import Literal, cast

import yaml
from PIL import ExifTags, Image, ImageCms, IptcImagePlugin, TiffTags

# Add a handler to stream to sys.stderr warnings from all modules.
logging.basicConfig(format="%(levelname)s: %(message)s")
# Add a logging namespace.
LOG = logging.getLogger(__name__)

ByteOrderType = Literal["big", "little"]

# From https://www.iptc.org/std/photometadata/specification/iptc-pmd-techreference_2023.2.json
IIM_NAMES = {
    (2, 90): "cityName",
    (2, 116): "copyrightNotice",
    (2, 101): "countryName",
    (2, 100): "countryCode",
    (2, 80): "creatorNames",
    (2, 85): "jobtitle",
    (2, 110): "creditLine",
    (2, 55): "dateCreated",
    (2, 120): "description",
    (2, 122): "captionWriter",
    (2, 105): "headline",
    (2, 40): "instructions",
    (2, 4): "intellectualGenre",
    (2, 103): "jobid",
    (2, 25): "keywords",
    (2, 95): "provinceState",
    (2, 115): "source",
    (2, 12): "subjectCodes",
    (2, 92): "sublocationName",
    (2, 5): "title",
}

EXIF_TAGS = {
    **ExifTags.TAGS,
    769: "Exif 0x0301",
    771: "Rendering Intent",
    20752: "Pixel Units",
    20753: "Pixels Per Unit X",
    20754: "Pixels Per Unit Y",
}

# From https://gist.github.com/ertaquo/b1d12c37a21268e3d095d39e196f5863
PSD_RESOURCE_IDS = {
    1000: "Ps2Info",
    1001: "MacPrintManagerInfo",
    1002: "MacPageFormatInfo",
    1003: "Ps2IndexedColorTable",
    1005: "ResolutionInfo",
    1006: "AlphaChannelsNames",
    1007: "OldDisplayInfo",
    1008: "Caption",
    1009: "BorderInfo",
    1010: "BackgroundColor",
    1011: "PrintFlags",
    1012: "GrayscaleAndMultichannelHalftoningInfo",
    1013: "ColorHalftoningInfo",
    1014: "DuotoneHalftoningInfo",
    1015: "GrayscaleAndMultichannelTransferFunction",
    1016: "ColorTransferFunctions",
    1017: "DuotoneTransferFunctions",
    1018: "DuotoneImageInfo",
    1019: "EffectiveBlackAndWhiteValues",
    1021: "EpsOptions",
    1022: "QuickMaskInfo",
    1024: "LayerStateInfo",
    1025: "WorkingPath",
    1026: "LayersGroupInfo",
    1028: "UptcNaaRecord",
    1029: "RawFormatFilesImageMode",
    1030: "JpegQuality",
    1032: "GridAndGuidesInfo",
    1033: "Ps4Thumbnail",
    1034: "CopyrightFlag",
    1035: "Url",
    1036: "Thumbnail",
    1037: "GlobalAngle",
    1039: "IccProfile",
    1040: "Watermark",
    1041: "IccUntaggedProfile",
    1042: "EffectsVisible",
    1043: "SpotHalftone",
    1044: "IdSeedNumber",
    1045: "UnicodeAlphaNames",
    1046: "IndexedColorTableCount",
    1047: "TransparencyIndex",
    1049: "GlobalAltitude",
    1050: "Slices",
    1051: "WorkflowUrl",
    1052: "JumpToXpep",
    1053: "AlphaIndentifiers",
    1054: "UrlList",
    1057: "VersionInfo",
    1058: "ExifData1",
    1059: "ExifData3",
    1060: "XmpMetadata",
    1061: "CaptionDigest",
    1062: "PrintScale",
    1064: "PixelAspectRatio",
    1065: "LayerComps",
    1066: "AlternateDuotoneColors",
    1067: "AlternateSpotColors",
    1069: "LayerSelectionIds",
    1070: "HdrToningInfo",
    1071: "PrintInfo",
    1072: "LayerGroupsEnabledId",
    1073: "ColorSamplers",
    1074: "MeasurementScale",
    1075: "TimelineInfo",
    1076: "SheetDisclosure",
    1077: "DisplayInfo",
    1078: "OnionSkins",
    1080: "CountInfo",
    1082: "PrintSettings",
    1083: "PrintStyle",
    1084: "NsPrintInfo",
    1086: "AutoSaveFilePath",
    1087: "AutoSaveFormat",
    1088: "PathSelectionState",
    2999: "ClippingPathName",
    3000: "OriginPathInfo",
    10000: "PrintFlagsInfo",
}

RENDERING_INTENT = (
    "Perceptual",
    "Relative colorimetric",
    "Saturation",
    "Absolute colorimetric",
)


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


def info_get(im: Image.Image, info: dict, path: str = "") -> str:
    """Get image info."""
    msg = ""
    for k, v in info.items():
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

        if k == "adobe":
            v = f"DCT v{v}"
        elif k == "adobe_transform":
            v = {1: "YCbCr"}.get(v, v)
        elif k == "comment":
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
    if not im:
        return msg.replace("\0", "\\0")

    msg += f"\nFormat: {im.format}"
    try:
        msg += f"\nMIME type: {im.get_format_mimetype()}"  # type: ignore
    except AttributeError:
        pass
    try:
        msg += f"\nBit Depth: {im.bits}"  # type: ignore
    except AttributeError:
        pass
    pixels = im.width * im.height
    msg += (
        f"\nColor Type: {im.mode}"
        + f"\nColors: {len(im.getcolors(pixels)):,}"
        + f"\nPixels: {pixels:,}"
    )
    for fun in (info_exif, info_icc, info_iptc, info_xmp, info_psd, info_exiftool):
        s = fun(path) if fun == info_exiftool else fun(im)  # type: ignore
        if s:
            msg += "\n\n" + s

    return msg.replace("\0", "\\0")


def info_exif(im: Image.Image) -> str:
    """Return Exchangeable Image File (EXIF) info."""
    # Workaround from https://github.com/python-pillow/Pillow/issues/5863
    if not hasattr(im, "_getexif"):
        return ""

    exif = im._getexif()  # type: ignore  # pylint: disable=protected-access
    if not exif:
        return ""
    byte_order = cast(
        ByteOrderType, "big" if b"MM" in im.info["exif"][:8] else "little"
    )
    s = f"EXIF:\nByte order: {byte_order}-endian"
    for k, v in exif.items():
        if k not in EXIF_TAGS:
            s += f"\nUnknown EXIF tag {k}: {v}"
            continue
        key_name = EXIF_TAGS[k]
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
        elif k == 771:
            v = RENDERING_INTENT[int.from_bytes(v, byteorder=byte_order)]
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
        elif isinstance(v, bytes) and len(v) < 5:
            v = int.from_bytes(v, byteorder=byte_order)
        else:
            v = info_decode(v, "utf_16_be" if byte_order == "big" else "utf_16_le")

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


def info_exiftool(path: str) -> str:
    """Uses exiftool on path."""
    s = ""
    try:
        output = subprocess.run(
            [
                "exiftool",
                "-duplicates",
                "-groupHeadings",
                "-unknown2",
                # "-charset", "filename=utf8",  # Breaks finding regular files on Windows 10 but doesn't matter for Hebrew names.
                path,
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


def info_icc(im: Image.Image) -> str:
    """Return the ICC color profile info."""
    s = ""
    icc = im.info.get("icc_profile")  # type: ignore
    if icc:
        p = ImageCms.ImageCmsProfile(BytesIO(icc))
        intent = ImageCms.getDefaultIntent(p)
        man = ImageCms.getProfileManufacturer(p).strip()
        model = ImageCms.getProfileModel(p).strip()
        s += f"""ICC Profile:
Copyright: {ImageCms.getProfileCopyright(p).strip()}
Description: {ImageCms.getProfileDescription(p).strip()}
Intent: {RENDERING_INTENT[intent]}
isIntentSupported: {ImageCms.isIntentSupported(p, ImageCms.Intent(intent), ImageCms.Direction(1))}"""
        if man:
            s += f"\nManufacturer: {man}"
        if model:
            s += f"\nModel: {model}"
    return s.strip()


def info_iptc(im: Image.Image) -> str:
    """Return International Press Telecommunications Council (IPTC) Information Interchange Model (IIM) metadata.
    https://en.wikipedia.org/wiki/IPTC_Information_Interchange_Model#Overview says:
    Almost all the IIM attributes are supported by the Exchangeable image file format (Exif), a specification for the image file format used by digital cameras.
    IIM metadata can be embedded into JPEG/Exif, TIFF, JPEG2000 or Portable Network Graphics formatted image files. Other file formats such as GIF or PCX do not support IIM.
    IIM's file structure technology has largely been overtaken by the Extensible Metadata Platform (XMP), but the IIM attribute definitions are the basis for the IPTC Core schema for XMP.
    """
    s = ""
    iptc = IptcImagePlugin.getiptcinfo(im)
    if iptc:
        s += "IPTC:"
        for k, v in iptc.items():
            if k == (1, 90):
                k = "Coded Character Set"
                v = [{b"\x1b%G": "UTF8"}.get(i, i) for i in v]
            elif k == (2, 0):
                k = "Application Record Version"
                v = int.from_bytes(v, "little")
            else:
                k = IIM_NAMES.get(k, k)
            s += f"\n{k}: {repr(v)}"
    return s.strip()


def info_psd(im: Image.Image) -> str:
    """Return PhotoShop Document info."""
    info = im.info
    if "photoshop" not in info:
        return ""
    s = "Photoshop:\n"
    for k, v in info["photoshop"].items():
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
            s += f"{PSD_RESOURCE_IDS.get(k, k)}: {(str(v)[:200] + '...') if len(str(v)) > 200 else v}\n"
        else:
            s += f"{PSD_RESOURCE_IDS.get(k, k)}: {readable_v[:200] + '...' if len(readable_v) > 200 else readable_v}\n"
        if (
            k == 1036
        ):  # PS5 thumbnail, https://www.awaresystems.be/imaging/tiff/tifftags/docs/photoshopthumbnail.html
            continue

    return s.strip()


def info_xmp(im: Image.Image) -> str:
    """Return Extensible Metadata Platform (XMP) metadata."""
    if not hasattr(im, "getxmp"):
        return ""
    try:
        xmp = im.getxmp()  # type: ignore
        if not xmp:
            return ""
    except ValueError as ex:
        return f"XMP: {ex}"
    s = "XMP:\n"
    s += yaml.safe_dump(xmp)
    # Ugly:
    # import json
    # s += json.dumps(xmp, indent=2, sort_keys=True)
    # import toml
    # s += toml.dumps(xmp)
    # s += "\n\n" + str(xmp)
    return s.strip()
