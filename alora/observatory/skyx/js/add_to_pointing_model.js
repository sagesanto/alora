// take image, add to pointing model
var out;
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

cam.ExposureTime = {{exptime}};

try{
	cam.TakeImage();
} catch (e) {
	out = "SkyX Camera Error during exposure: " + e;
	throw 'c';
}

iml = ImageLink;
iml.pathToFITS = cam.LastImageFileName;
iml.Scale = {{image_scale}};
iml.unknownScale = 0;

sky6RASCOMTheSky.AutoMap()