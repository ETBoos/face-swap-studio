FaceSwap Studio Camera — optional Windows component

This component registers the FaceSwap Studio Camera video device for 64-bit
and 32-bit DirectShow applications. Installation requires administrator rights.

Install this component only if you want to send the app's video output to
another desktop application. The main FaceSwap Studio installer does not
install or register it automatically.

Close applications that are using this camera before upgrading or uninstalling.
To remove the component, use Windows Settings > Apps > FaceSwap Studio Camera.
Removing the main FaceSwap Studio app leaves this optional component installed.
The component uses its own device IDs and does not replace UnityCapture or OBS.

Compatibility is experimental. Device registration and a local camera smoke test
do not establish compatibility with WeChat, WhatsApp, or every desktop app.
This is a DirectShow source, not a kernel camera driver or a mobile camera.

Based on UnityCapture; see LICENSE.txt and UPSTREAM.md for attribution.
