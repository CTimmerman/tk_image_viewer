#!python
"""https://stackoverflow.com/a/21320589/819417"""

from io import BytesIO
from ctypes import c_size_t, memmove, windll
from ctypes.wintypes import BOOL, HANDLE, HWND, LPVOID, UINT

from PIL import Image


HGLOBAL = HANDLE
SizeT = c_size_t
GHND = 0x0042
GMEM_SHARE = 0x2000

GlobalAlloc = windll.kernel32.GlobalAlloc
GlobalAlloc.restype = HGLOBAL
GlobalAlloc.argtypes = [UINT, SizeT]

GlobalLock = windll.kernel32.GlobalLock
GlobalLock.restype = LPVOID
GlobalLock.argtypes = [HGLOBAL]

GlobalUnlock = windll.kernel32.GlobalUnlock
GlobalUnlock.restype = BOOL
GlobalUnlock.argtypes = [HGLOBAL]

CF_DIB = 8

OpenClipboard = windll.user32.OpenClipboard
OpenClipboard.restype = BOOL
OpenClipboard.argtypes = [HWND]

EmptyClipboard = windll.user32.EmptyClipboard
EmptyClipboard.restype = BOOL
EmptyClipboard.argtypes = None

SetClipboardData = windll.user32.SetClipboardData
SetClipboardData.restype = HANDLE
SetClipboardData.argtypes = [UINT, HANDLE]

CloseClipboard = windll.user32.CloseClipboard
CloseClipboard.restype = BOOL
CloseClipboard.argtypes = None


def copy(image: Image.Image) -> None:
    """
    >>> im_in = Image.new("RGB", (10, 11), (120, 130, 140))
    >>> copy(im_in)
    >>> from PIL import ImageGrab
    >>> im_out = ImageGrab.grabclipboard()
    >>> list(im_in.getdata()) == list(im_out.getdata())
    True
    """
    output = BytesIO()
    image.convert("RGB").save(output, "BMP")
    data = output.getvalue()[14:]
    output.close()

    h_data = GlobalAlloc(GHND | GMEM_SHARE, len(data))
    p_data = GlobalLock(h_data)
    memmove(p_data, data, len(data))
    GlobalUnlock(h_data)

    OpenClipboard(None)
    EmptyClipboard()
    SetClipboardData(CF_DIB, p_data)
    CloseClipboard()
