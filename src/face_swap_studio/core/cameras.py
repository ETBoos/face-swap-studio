"""Enumerate camera names without opening devices, using the capture API order."""

from __future__ import annotations

import ctypes
import sys
import uuid


def directshow_camera_names() -> list[str]:
    """Read IPropertyBag names from the same DirectShow enumerator as OpenCV.

    Qt's Media Foundation enumerator omits some DirectShow virtual cameras.
    Monikers are bound to storage only, never to the capture filter itself.
    """
    if sys.platform != "win32":
        return []
    from ctypes import wintypes as w

    class GUID(ctypes.Structure):
        _fields_ = [("bytes", ctypes.c_ubyte * 16)]

    def guid(value):
        return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

    class Record(ctypes.Structure):
        _fields_ = [("value", ctypes.c_void_p), ("info", ctypes.c_void_p)]

    class Value(ctypes.Union):
        _fields_ = [("bstr", ctypes.c_void_p), ("record", Record), ("number", ctypes.c_double)]

    class Variant(ctypes.Structure):
        _fields_ = [("vt", w.WORD), ("r1", w.WORD), ("r2", w.WORD), ("r3", w.WORD), ("value", Value)]

    oleaut32 = ctypes.WinDLL("oleaut32")
    # WinDLL keeps HRESULT as a signed value so S_FALSE is handled explicitly.
    ole32 = ctypes.WinDLL("ole32")
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, w.DWORD]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [ctypes.POINTER(GUID), ctypes.c_void_p, w.DWORD,
                                     ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p)]
    ole32.CoCreateInstance.restype = ctypes.c_long
    oleaut32.VariantClear.argtypes = [ctypes.POINTER(Variant)]
    oleaut32.VariantClear.restype = ctypes.c_long

    def method(obj, index, restype, *args):
        table = ctypes.cast(obj, ctypes.POINTER(ctypes.POINTER(ctypes.c_void_p))).contents
        return ctypes.WINFUNCTYPE(restype, ctypes.c_void_p, *args)(table[index])

    def release(obj):
        if obj:
            method(obj, 2, w.ULONG)(obj)

    def checked(result):
        if result < 0:
            raise RuntimeError(f"无法读取摄像头列表（Windows COM 0x{result & 0xffffffff:08x}）")
        return result

    initialized = ole32.CoInitializeEx(None, 0)
    if initialized not in (0, 1, -2147417850):  # RPC_E_CHANGED_MODE: use existing apartment
        checked(initialized)
    device_enum, monikers = ctypes.c_void_p(), ctypes.c_void_p()
    names = []
    try:
        checked(ole32.CoCreateInstance(
            ctypes.byref(guid("62BE5D10-60EB-11D0-BD3B-00A0C911CE86")), None, 1,
            ctypes.byref(guid("29840822-5B84-11D0-BD3B-00A0C911CE86")), ctypes.byref(device_enum),
        ))
        result = checked(method(device_enum, 3, ctypes.c_long, ctypes.POINTER(GUID),
                                ctypes.POINTER(ctypes.c_void_p), w.DWORD)(
            device_enum, ctypes.byref(guid("860BB310-5D01-11D0-BD3B-00A0C911CE86")),
            ctypes.byref(monikers), 0,
        ))
        if result == 1:
            return []
        while True:
            moniker, bag = ctypes.c_void_p(), ctypes.c_void_p()
            result = checked(method(monikers, 3, ctypes.c_long, w.ULONG,
                                    ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p)(
                monikers, 1, ctypes.byref(moniker), None,
            ))
            if result == 1:
                break
            name = f"摄像头 {len(names) + 1}"
            value = Variant()
            try:
                bound = method(moniker, 9, ctypes.c_long, ctypes.c_void_p, ctypes.c_void_p,
                               ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))(
                    moniker, None, None, ctypes.byref(guid("55272A00-42CB-11CE-8135-00AA004BB851")),
                    ctypes.byref(bag),
                )
                if bound >= 0:
                    result = method(bag, 3, ctypes.c_long, w.LPCWSTR, ctypes.POINTER(Variant),
                                    ctypes.c_void_p)(bag, "FriendlyName", ctypes.byref(value), None)
                    if result >= 0 and value.vt == 8 and value.value.bstr:
                        name = ctypes.wstring_at(value.value.bstr)
                names.append(name)
            finally:
                oleaut32.VariantClear(ctypes.byref(value))
                release(bag)
                release(moniker)
        return names
    finally:
        release(monikers)
        release(device_enum)
        if initialized >= 0:
            ole32.CoUninitialize()


def camera_names() -> list[str]:
    if sys.platform == "win32":
        return directshow_camera_names()
    from PySide6.QtMultimedia import QMediaDevices

    return [device.description() for device in QMediaDevices.videoInputs()]
