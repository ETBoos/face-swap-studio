# Virtual camera component

Based on UnityCapture (MIT), commit `3ed54c325e0ad71afcf4f246c07e5e17b3d7f2d2`.
Source: https://github.com/schellingb/UnityCapture

Preserved source notices, including DirectShow base class attribution.
Changes: separate FaceSwap Studio device name, CLSIDs and IPC namespace; bounded module-name buffer size and compiler stack protection; single-camera registration/unregistration confined to this product's exact CLSIDs; checked registry handles and released temporary COM strings.

64-bit service CLSID: `{E3B79076-C56E-4E15-95B9-4B6F523A0010}`.
64-bit properties CLSID: `{E3B79076-C56E-4E15-95B9-4B6F523A0011}`.
32-bit service CLSID ends `0020`; properties ends `0021`.
IPC names: `FSSCapture_Mutx`, `FSSCapture_Want`, `FSSCapture_Sent`, `FSSCapture_Data` (camera zero).

This DirectShow component is experimental until actual receiving-app compatibility is tested.
Registration is owned by the separate machine-level installer, not app startup.

Product defaults: missing, stopped or resolution-mismatched frames render black instead of colored patterns; user-visible sender labels identify FaceSwap Studio. Original copyright notices and internal upstream symbol names remain intact.

Lifecycle fixes: unmap the shared-memory view before closing mapping handles; measure sender inactivity using GetTickCount64 and the advertised millisecond timeout, rather than estimating elapsed time from missed-frame counts.
