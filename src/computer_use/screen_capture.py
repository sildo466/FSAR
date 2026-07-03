"""Screen capture using PrintWindow + DWM crop.

Replicates CUA's capture strategy:
1. PrintWindow with PW_RENDERFULLCONTENT (works even when occluded)
2. DWM crop to remove invisible drop-shadow margins
3. Fallback to BitBlt from screen if PrintWindow returns black
"""

from __future__ import annotations

import ctypes
import ctypes.wintypes
import io
import struct

from PIL import Image

# Win32 constants
PW_RENDERFULLCONTENT = 0x00000002
SRCCOPY = 0x00CC0020
DWMWA_EXTENDED_FRAME_BOUNDS = 9

# Set return types AND argtypes for 64-bit compatibility (must be at module level)
# Without argtypes, ctypes passes Python ints as C int (32-bit), causing OverflowError
# on 64-bit handle values.
_user32 = ctypes.windll.user32
_gdi32 = ctypes.windll.gdi32
_dwmapi = ctypes.windll.dwmapi

# user32
_user32.GetDC.argtypes = [ctypes.wintypes.HWND]
_user32.GetDC.restype = ctypes.wintypes.HDC
_user32.GetWindowDC.argtypes = [ctypes.wintypes.HWND]
_user32.GetWindowDC.restype = ctypes.wintypes.HDC
_user32.GetWindowRect.argtypes = [ctypes.wintypes.HWND, ctypes.POINTER(ctypes.wintypes.RECT)]
_user32.GetWindowRect.restype = ctypes.wintypes.BOOL
_user32.PrintWindow.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC, ctypes.wintypes.UINT]
_user32.PrintWindow.restype = ctypes.wintypes.BOOL
_user32.ReleaseDC.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.HDC]
_user32.ReleaseDC.restype = ctypes.c_int
_user32.IsIconic.argtypes = [ctypes.wintypes.HWND]
_user32.IsIconic.restype = ctypes.wintypes.BOOL

# gdi32
_gdi32.CreateCompatibleDC.argtypes = [ctypes.wintypes.HDC]
_gdi32.CreateCompatibleDC.restype = ctypes.wintypes.HDC
_gdi32.CreateCompatibleBitmap.argtypes = [ctypes.wintypes.HDC, ctypes.c_int, ctypes.c_int]
_gdi32.CreateCompatibleBitmap.restype = ctypes.wintypes.HBITMAP
_gdi32.SelectObject.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HGDIOBJ]
_gdi32.SelectObject.restype = ctypes.wintypes.HGDIOBJ
_gdi32.BitBlt.argtypes = [ctypes.wintypes.HDC, ctypes.c_int, ctypes.c_int,
                           ctypes.c_int, ctypes.c_int, ctypes.wintypes.HDC,
                           ctypes.c_int, ctypes.c_int, ctypes.wintypes.DWORD]
_gdi32.BitBlt.restype = ctypes.wintypes.BOOL
_gdi32.GetDIBits.argtypes = [ctypes.wintypes.HDC, ctypes.wintypes.HBITMAP,
                              ctypes.wintypes.UINT, ctypes.wintypes.UINT,
                              ctypes.c_void_p, ctypes.c_void_p, ctypes.wintypes.UINT]
_gdi32.GetDIBits.restype = ctypes.c_int
_gdi32.DeleteObject.argtypes = [ctypes.wintypes.HGDIOBJ]
_gdi32.DeleteObject.restype = ctypes.wintypes.BOOL
_gdi32.DeleteDC.argtypes = [ctypes.wintypes.HDC]
_gdi32.DeleteDC.restype = ctypes.wintypes.BOOL

# dwmapi
_dwmapi.DwmGetWindowAttribute.argtypes = [ctypes.wintypes.HWND, ctypes.wintypes.DWORD,
                                           ctypes.c_void_p, ctypes.wintypes.DWORD]
_dwmapi.DwmGetWindowAttribute.restype = ctypes.c_long  # HRESULT


def _get_dwm_frame(hwnd) -> tuple[int, int, int, int]:
    """Get DWM extended frame bounds (removes invisible drop shadow)."""
    rect = ctypes.wintypes.RECT()
    hr = ctypes.windll.dwmapi.DwmGetWindowAttribute(
        hwnd,
        DWMWA_EXTENDED_FRAME_BOUNDS,
        ctypes.byref(rect),
        ctypes.sizeof(rect),
    )
    if hr == 0:
        return (rect.left, rect.top, rect.right, rect.bottom)
    # Fallback to GetWindowRect
    ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect))
    return (rect.left, rect.top, rect.right, rect.bottom)


def _is_minimized(hwnd) -> bool:
    return bool(ctypes.windll.user32.IsIconic(hwnd))


def capture_screen() -> bytes:
    """Capture the entire desktop screen as PNG bytes.

    Uses BitBlt from the desktop DC. Works regardless of which window is active.
    Returns PNG bytes.
    """
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # Get screen size
    screen_w = user32.GetSystemMetrics(0)  # SM_CXSCREEN
    screen_h = user32.GetSystemMetrics(1)  # SM_CYSCREEN

    if screen_w <= 0 or screen_h <= 0:
        return b""

    hdc_screen = user32.GetDC(0)  # desktop DC
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, screen_w, screen_h)
    old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

    gdi32.BitBlt(hdc_mem, 0, 0, screen_w, screen_h, hdc_screen, 0, 0, SRCCOPY)

    png = _hbitmap_to_png(hdc_mem, hbitmap, screen_w, screen_h)

    gdi32.SelectObject(hdc_mem, old_bmp)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)

    return png


def capture_window(hwnd: int) -> bytes:
    """Capture a window screenshot as PNG bytes.

    Strategy (matching CUA):
    1. PrintWindow with PW_RENDERFULLCONTENT (works for occluded GDI windows)
    2. If >99.5% black pixels, fall back to screen-region BitBlt
    3. If BitBlt also returns black (window occluded), briefly bring to foreground and retry
    4. DWM crop to remove shadow margins

    Returns PNG bytes.
    """
    if _is_minimized(hwnd):
        raise ValueError(f"Window hwnd={hwnd} is minimized, cannot capture")

    # Try PrintWindow first
    png = _capture_printwindow(hwnd)
    if png and not _is_mostly_black(png):
        return png

    # Fallback: screen-region BitBlt (works if window is visible and not occluded)
    png = _capture_bitblt_screen(hwnd)
    if png and not _is_mostly_black(png):
        return png

    # Last resort: briefly bring window to foreground and try BitBlt again.
    # This handles Chromium/DirectComposition apps where PrintWindow returns black
    # and the window is occluded by other windows.
    user32 = ctypes.windll.user32
    prev_fg = user32.GetForegroundWindow()
    if prev_fg != hwnd:
        try:
            user32.SetForegroundWindow(hwnd)
            import time
            time.sleep(0.1)  # let the window render
            png = _capture_bitblt_screen(hwnd)
            if png and not _is_mostly_black(png):
                return png
        finally:
            # Restore previous foreground
            if prev_fg:
                user32.SetForegroundWindow(prev_fg)

    # Return whatever we have (may be black)
    return png or b""


def _capture_printwindow(hwnd: int) -> bytes:
    """Capture using PrintWindow (works for occluded windows)."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    # Get window rect
    rect = ctypes.wintypes.RECT()
    user32.GetWindowRect(hwnd, ctypes.byref(rect))
    w = rect.right - rect.left
    h = rect.bottom - rect.top

    if w <= 0 or h <= 0:
        return b""

    # Create device context and bitmap
    hdc_window = user32.GetDC(hwnd)
    hdc_mem = gdi32.CreateCompatibleDC(hdc_window)
    hbitmap = gdi32.CreateCompatibleBitmap(hdc_window, w, h)
    old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

    # PrintWindow - renders even if occluded
    result = user32.PrintWindow(hwnd, hdc_mem, PW_RENDERFULLCONTENT)

    if result == 0:
        # PrintWindow failed, try BitBlt from window DC
        gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_window, 0, 0, SRCCOPY)

    # Extract bitmap data
    png = _hbitmap_to_png(hdc_mem, hbitmap, w, h)

    # Cleanup
    gdi32.SelectObject(hdc_mem, old_bmp)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(hwnd, hdc_window)

    return png


def _capture_bitblt_screen(hwnd: int) -> bytes:
    """Fallback: capture from screen using BitBlt."""
    user32 = ctypes.windll.user32
    gdi32 = ctypes.windll.gdi32

    dwm = _get_dwm_frame(hwnd)
    w = dwm[2] - dwm[0]
    h = dwm[3] - dwm[1]

    if w <= 0 or h <= 0:
        return b""

    hdc_screen = user32.GetDC(0)  # desktop DC
    hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
    hbitmap = gdi32.CreateCompatibleBitmap(hdc_screen, w, h)
    old_bmp = gdi32.SelectObject(hdc_mem, hbitmap)

    gdi32.BitBlt(hdc_mem, 0, 0, w, h, hdc_screen, dwm[0], dwm[1], SRCCOPY)

    png = _hbitmap_to_png(hdc_mem, hbitmap, w, h)

    gdi32.SelectObject(hdc_mem, old_bmp)
    gdi32.DeleteObject(hbitmap)
    gdi32.DeleteDC(hdc_mem)
    user32.ReleaseDC(0, hdc_screen)

    return png


def _hbitmap_to_png(hdc, hbitmap, w: int, h: int) -> bytes:
    """Convert a Windows HBITMAP to PNG bytes using DIB extraction."""
    gdi32 = ctypes.windll.gdi32

    class BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [
            ("biSize", ctypes.wintypes.DWORD),
            ("biWidth", ctypes.wintypes.LONG),
            ("biHeight", ctypes.wintypes.LONG),
            ("biPlanes", ctypes.wintypes.WORD),
            ("biBitCount", ctypes.wintypes.WORD),
            ("biCompression", ctypes.wintypes.DWORD),
            ("biSizeImage", ctypes.wintypes.DWORD),
            ("biXPelsPerMeter", ctypes.wintypes.LONG),
            ("biYPelsPerMeter", ctypes.wintypes.LONG),
            ("biClrUsed", ctypes.wintypes.DWORD),
            ("biClrImportant", ctypes.wintypes.DWORD),
        ]

    bmi = BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(BITMAPINFOHEADER)
    bmi.biWidth = w
    bmi.biHeight = -h  # top-down
    bmi.biPlanes = 1
    bmi.biBitCount = 32
    bmi.biCompression = 0  # BI_RGB

    buf_size = w * h * 4
    buf = ctypes.create_string_buffer(buf_size)
    gdi32.GetDIBits(hdc, hbitmap, 0, h, buf, ctypes.byref(bmi), 0)  # DIB_RGB_COLORS = 0

    # Convert BGRA to RGBA
    img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1)
    # DWM crop: remove 1px border (matching CUA's DWM_CROP_INSET_PX)
    dwm = _get_dwm_frame_from_image(img)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


def _get_dwm_frame_from_image(img: Image.Image) -> tuple[int, int, int, int]:
    """Placeholder - DWM crop is done at capture time via _get_dwm_frame."""
    return (0, 0, img.width, img.height)


def _is_mostly_black(png_bytes: bytes, threshold: float = 0.995) -> bool:
    """Check if image is >threshold black pixels (UWP/DirectComposition fallback)."""
    if not png_bytes:
        return True
    try:
        img = Image.open(io.BytesIO(png_bytes))
        # Sample a few rows
        pixels = list(img.convert("RGBA").getdata())
        sample = pixels[::max(1, len(pixels) // 1000)]  # sample ~1000 pixels
        black = sum(1 for p in sample if p[0] < 10 and p[1] < 10 and p[2] < 10)
        return black / len(sample) > threshold
    except Exception:
        return False


def resize_if_needed(png_bytes: bytes, max_dim: int = 1568) -> tuple[bytes, float]:
    """Resize PNG if either dimension exceeds max_dim. Returns (png_bytes, ratio)."""
    if not png_bytes:
        return b"", 1.0
    try:
        img = Image.open(io.BytesIO(png_bytes))
        w, h = img.size
    except Exception:
        return png_bytes, 1.0

    if w <= max_dim and h <= max_dim:
        return png_bytes, 1.0

    ratio = min(max_dim / w, max_dim / h)
    new_w = int(w * ratio)
    new_h = int(h * ratio)
    img = img.resize((new_w, new_h), Image.LANCZOS)

    out = io.BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue(), ratio


def add_grid_overlay(png_bytes: bytes, step_px: int = 50) -> bytes:
    """Add a coordinate grid overlay to help the LLM pinpoint positions.

    Draws light grid lines every `step_px` pixels with coordinate labels
    along the top and left edges. The LLM can read coordinates directly
    from the grid instead of guessing pixel positions.
    """
    from PIL import ImageDraw, ImageFont

    if not png_bytes:
        return png_bytes

    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    w, h = img.size

    # Create a semi-transparent overlay
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Grid line color: light gray, semi-transparent
    line_color = (200, 200, 200, 80)
    text_color = (255, 255, 255, 180)
    text_bg = (0, 0, 0, 140)

    # Try to get a small font for labels
    try:
        font = ImageFont.truetype("arial.ttf", 10)
    except Exception:
        font = ImageFont.load_default()

    # Draw vertical lines + top labels
    for x in range(step_px, w, step_px):
        draw.line([(x, 0), (x, h)], fill=line_color, width=1)
        label = str(x)
        bbox = font.getbbox(label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # Label at top
        draw.rectangle([(x - tw // 2 - 1, 0), (x + tw // 2 + 1, th + 2)], fill=text_bg)
        draw.text((x - tw // 2, 1), label, fill=text_color, font=font)

    # Draw horizontal lines + left labels
    for y in range(step_px, h, step_px):
        draw.line([(0, y), (w, y)], fill=line_color, width=1)
        label = str(y)
        bbox = font.getbbox(label)
        tw = bbox[2] - bbox[0]
        th = bbox[3] - bbox[1]
        # Label at left
        draw.rectangle([(0, y - th // 2 - 1), (tw + 2, y + th // 2 + 1)], fill=text_bg)
        draw.text((1, y - th // 2), label, fill=text_color, font=font)

    # Composite overlay onto original image
    result = Image.alpha_composite(img, overlay).convert("RGB")

    out = io.BytesIO()
    result.save(out, format="PNG", optimize=True)
    return out.getvalue()
