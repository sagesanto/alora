// take image, add to pointing model

t = sky6RASCOMTele
t.Connect()
t.SetTracking(1,1,0,0)

// will save images to last directory used
try {
    ccdsoftCamera.Connect();
} catch (e) {
    out = "SkyX Camera Connection Error: " + e;
    throw 'a';
}
ccdsoftCamera.AutoSaveOn = 1;
ccdsoftCamera.ExposureTime = {{exptime}};
AutomatedImageLinkSettings.exposureTimeAILS = {{exptime}};
AutomatedImageLinkSettings.imageScale = {{image_scale}};
var orig_bin = ccdsoftCamera.BinX;
ccdsoftCamera.BinX = 2;
ccdsoftCamera.BinY = 2;

sky6RASCOMTheSky.AutoMap()