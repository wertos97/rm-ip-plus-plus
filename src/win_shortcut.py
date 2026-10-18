"""Create/refresh the Start Menu shortcut with AppUserModelID (ctypes COM).

Windows 11 resolves the taskbar icon through the shortcut registered for the
app's AUMID; a plain window icon is not always enough for unpackaged apps.
No external dependencies (IShellLinkW + IPropertyStore via ctypes).
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes

ole32 = ctypes.OleDLL("ole32")

CLSCTX_INPROC_SERVER = 1
STGM_READ = 0x00000000


class GUID(ctypes.Structure):
    _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]


class PROPERTYKEY(ctypes.Structure):
    _fields_ = [("fmtid", GUID), ("pid", wintypes.DWORD)]


class PROPVARIANT(ctypes.Structure):
    _fields_ = [("vt", ctypes.c_ushort), ("r1", ctypes.c_ushort),
                ("r2", ctypes.c_ushort), ("r3", ctypes.c_ushort),
                ("p", ctypes.c_void_p), ("p2", ctypes.c_void_p)]


def _guid(text: str) -> GUID:
    g = GUID()
    if ole32.CLSIDFromString(ctypes.c_wchar_p(text), ctypes.byref(g)) != 0:
        raise OSError("CLSIDFromString failed: " + text)
    return g


IID_ISHELLLINKW = _guid("{000214F9-0000-0000-C000-000000000046}")
IID_IPERSISTFILE = _guid("{0000010B-0000-0000-C000-000000000046}")
IID_IPROPERTYSTORE = _guid("{886D8EEB-8CF2-4446-8D02-CDBA1DBDCF99}")
CLSID_SHELLLINK = _guid("{00021401-0000-0000-C000-000000000046}")
PKEY_APPID = PROPERTYKEY(_guid("{9F4C2855-9F79-4B39-A8D0-E1D42DE1D5F3}"), 5)
VT_LPWSTR = 31

# IShellLinkW vtable indexes
SL_QUERYINTERFACE = 0
SL_GETPATH = 3
SL_SETDESCRIPTION = 7
SL_SETICONLOCATION = 17
SL_SETPATH = 20
# IPersistFile vtable indexes
PF_LOAD = 5
PF_SAVE = 6
# IPropertyStore vtable indexes
PS_SETVALUE = 6
PS_COMMIT = 7


def _call(ptr, index, restype, *argtypes):
    vtable = ctypes.cast(ptr, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p)))[0]
    proto = ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *argtypes)
    return proto(vtable[index])


def _release(ptr) -> None:
    try:
        _call(ptr, 2, ctypes.c_ulong)(ptr)
    except Exception:
        pass


def _co_init() -> None:
    """Ensure COM is initialized on this thread (idempotent)."""
    try:
        ole32.CoInitializeEx(None, 2)  # COINIT_APARTMENTTHREADED
    except Exception:
        pass


def _new_shell_link():
    ptr = ctypes.c_void_p()
    hr = ole32.CoCreateInstance(ctypes.byref(CLSID_SHELLLINK), None,
                                CLSCTX_INPROC_SERVER,
                                ctypes.byref(IID_ISHELLLINKW), ctypes.byref(ptr))
    if hr != 0 or not ptr.value:
        raise OSError(f"CoCreateInstance failed: 0x{hr & 0xFFFFFFFF:08x}")
    return ptr


def _query(obj, iid):
    out = ctypes.c_void_p()
    hr = _call(obj, SL_QUERYINTERFACE, ctypes.HRESULT,
               ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
        obj, ctypes.byref(iid), ctypes.byref(out))
    if hr != 0 or not out.value:
        raise OSError(f"QueryInterface failed: 0x{hr & 0xFFFFFFFF:08x}")
    return out


def shortcut_target(lnk_path: str) -> str:
    """Target path stored in an existing .lnk ('' when unreadable)."""
    if not os.path.exists(lnk_path):
        return ""
    _co_init()
    link = _new_shell_link()
    persist = None
    try:
        persist = _query(link, IID_IPERSISTFILE)
        hr = _call(persist, PF_LOAD, ctypes.HRESULT,
                   wintypes.LPCWSTR, wintypes.DWORD)(persist, lnk_path, STGM_READ)
        if hr != 0:
            return ""
        buf = ctypes.create_unicode_buffer(1024)
        hr = _call(link, SL_GETPATH, ctypes.HRESULT, wintypes.LPWSTR,
                   ctypes.c_int, ctypes.c_void_p, wintypes.DWORD)(
            link, buf, 1024, None, 0)
        return buf.value if hr == 0 else ""
    finally:
        if persist is not None:
            _release(persist)
        _release(link)


def ensure_shortcut(lnk_path: str, target: str, icon: str, aumid: str,
                    description: str = "RM IP++") -> bool:
    """Create/update the shortcut when missing or pointing elsewhere.

    Returns True when the file was written.
    """
    if shortcut_target(lnk_path).lower() == target.lower():
        return False
    os.makedirs(os.path.dirname(lnk_path), exist_ok=True)
    _co_init()
    link = _new_shell_link()
    persist = None
    store = None
    buf = None
    try:
        _call(link, SL_SETPATH, ctypes.HRESULT, wintypes.LPCWSTR)(link, target)
        _call(link, SL_SETDESCRIPTION, ctypes.HRESULT, wintypes.LPCWSTR)(link, description)
        _call(link, SL_SETICONLOCATION, ctypes.HRESULT,
              wintypes.LPCWSTR, ctypes.c_int)(link, icon, 0)
        store = _query(link, IID_IPROPERTYSTORE)
        buf = ctypes.create_unicode_buffer(aumid)
        pv = PROPVARIANT()
        pv.vt = VT_LPWSTR
        pv.p = ctypes.cast(buf, ctypes.c_void_p)
        hr = _call(store, PS_SETVALUE, ctypes.HRESULT,
                   ctypes.POINTER(PROPERTYKEY), ctypes.POINTER(PROPVARIANT))(
            store, ctypes.byref(PKEY_APPID), ctypes.byref(pv))
        if hr == 0:
            _call(store, PS_COMMIT, ctypes.HRESULT)(store)
        persist = _query(link, IID_IPERSISTFILE)
        hr = _call(persist, PF_SAVE, ctypes.HRESULT,
                   wintypes.LPCWSTR, wintypes.BOOL)(persist, lnk_path, True)
        return hr == 0
    finally:
        if store is not None:
            _release(store)
        if persist is not None:
            _release(persist)
        _release(link)
