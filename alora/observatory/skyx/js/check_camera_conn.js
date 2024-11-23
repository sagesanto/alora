var cam = ccdsoftCamera;
out = 0;
try {
    out = cam.Connect();
    out = 1;
} catch (e) {
    out = "SkyX Camera Connection Error: " + e;
}