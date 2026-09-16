"""Print HRESULTs for the same capture graph used by OpenCV on Windows.

Only the product's own CLSID is opened; no physical camera is accessed.
"""
import ctypes as c
import uuid


def main():
    class GUID(c.Structure):
        _fields_ = [("bytes", c.c_ubyte * 16)]

    def guid(value):
        return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)

    class MediaType(c.Structure):
        _fields_ = [("major", GUID), ("subtype", GUID), ("fixed", c.c_int),
                    ("temporal", c.c_int), ("size", c.c_ulong), ("format", GUID),
                    ("unknown", c.c_void_p), ("format_size", c.c_ulong), ("data", c.c_void_p)]

    ole = c.WinDLL("ole32")
    ole.CoInitializeEx(None, 0)
    ole.CoCreateInstance.argtypes = [c.POINTER(GUID), c.c_void_p, c.c_ulong,
                                    c.POINTER(GUID), c.POINTER(c.c_void_p)]
    ole.CoTaskMemFree.argtypes = [c.c_void_p]
    objects = []

    def call(obj, index, types, *args):
        table = c.cast(obj, c.POINTER(c.POINTER(c.c_void_p))).contents
        return c.WINFUNCTYPE(c.c_long, c.c_void_p, *types)(table[index])(obj, *args)

    def report(label, result, required=True):
        print(f"{label}: 0x{result & 0xffffffff:08X}", flush=True)
        if result < 0 and required:
            raise RuntimeError(f"DirectShow graph failed at {label}")

    def create(label, clsid, iid):
        obj = c.c_void_p()
        report(label, ole.CoCreateInstance(c.byref(guid(clsid)), None, 1,
                                           c.byref(guid(iid)), c.byref(obj)))
        objects.append(obj)
        return obj

    def query(label, obj, iid):
        result = c.c_void_p()
        report(label, call(obj, 0, [c.POINTER(GUID), c.POINTER(c.c_void_p)],
                           c.byref(guid(iid)), c.byref(result)))
        objects.append(result)
        return result

    base_filter = "56A86895-0AD4-11CE-B03A-0020AF0BA770"
    capture_category = guid("FB6C4281-0353-11D1-905F-0000C0CC16BA")
    preview_category = guid("FB6C4282-0353-11D1-905F-0000C0CC16BA")
    video = guid("73646976-0000-0010-8000-00AA00389B71")
    try:
        source = create("Create product camera", "E3B79076-C56E-4E15-95B9-4B6F523A0010", base_filter)
        builder = create("Create capture graph builder", "BF87B6E1-8C27-11D0-B3F0-00AA003761C5",
                         "93E5A4E0-2D50-11D2-ABFA-00A0C9C6E38D")
        graph = create("Create filter graph", "E436EBB3-524F-11CE-9F53-0020AF0BA770",
                       "56A868A9-0AD4-11CE-B03A-0020AF0BA770")
        report("Set filter graph", call(builder, 3, [c.c_void_p], graph))
        control = query("Query media control", graph, "56A868B1-0AD4-11CE-B03A-0020AF0BA770")
        report("Add camera filter", call(graph, 3, [c.c_void_p, c.c_wchar_p], source, "Camera"))
        config = c.c_void_p()
        report("Find capture IAMStreamConfig", call(builder, 6,
            [c.POINTER(GUID), c.POINTER(GUID), c.c_void_p, c.POINTER(GUID), c.POINTER(c.c_void_p)],
            c.byref(capture_category), c.byref(video), source,
            c.byref(guid("C6E13340-30AC-11D0-A18C-00A0C9118956")), c.byref(config)))
        objects.append(config)
        media = c.POINTER(MediaType)()
        report("Get capture format", call(config, 4, [c.POINTER(c.POINTER(MediaType))], c.byref(media)))
        print(f"Format bytes: {media.contents.format_size}; sample bytes: {media.contents.size}", flush=True)
        ole.CoTaskMemFree(media.contents.data)
        ole.CoTaskMemFree(media)
        grabber = create("Create sample grabber", "C1F400A0-3F08-11D3-9F0B-006008039E37", base_filter)
        report("Add sample grabber", call(graph, 3, [c.c_void_p, c.c_wchar_p], grabber, "Grabber"))
        sample = query("Query sample grabber", grabber, "6B652FFF-11FE-4FCE-92AD-0266B5D7C78F")
        desired = MediaType()
        desired.major = video
        desired.subtype = guid("E436EB7D-524F-11CE-9F53-0020AF0BA770")
        desired.format = guid("05589F80-C356-11CE-BF01-00AA0055595A")
        report("Set sample RGB24", call(sample, 4, [c.POINTER(MediaType)], c.byref(desired)))
        renderer = create("Create null renderer", "C1F400A4-3F08-11D3-9F0B-006008039E37", base_filter)
        report("Add null renderer", call(graph, 3, [c.c_void_p, c.c_wchar_p], renderer, "Renderer"))
        report("Render preview stream", call(builder, 7,
            [c.POINTER(GUID), c.POINTER(GUID), c.c_void_p, c.c_void_p, c.c_void_p],
            c.byref(preview_category), c.byref(video), source, grabber, renderer))
        report("Run graph", call(control, 7, []))
        report("Stop graph", call(control, 9, []))
    finally:
        for obj in reversed(objects):
            call(obj, 2, [])
        ole.CoUninitialize()


if __name__ == "__main__":
    main()
