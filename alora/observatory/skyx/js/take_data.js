//Make a shorter named variable to represent the built in camera
var cam = ccdsoftCamera;
var out

// these will be replaced by the python code before being sent 
var nframes = {{nframes}}
var exptime = {{exptime}}
var filter = {{filter}}
var asynchronous = {{asynchronous}}
var outdir = "{{outdir}}"
var prefix = "{{prefix}}" // image prefix
var expdelay = {{exp_delay}} // delay between exposures

cam.asynchronous = 0;
try {
	cam.Disconnect();
    cam.Connect();
} catch (e) {
    out = "SkyX Camera Connection Error: " + e;
    throw 'a';
}

cam.AutoSavePath = outdir;
cam.AutoSavePrefix = prefix;
cam.AutoSaveOn = 1;
cam.SaveImagesWithUTC = 1;

if (filter != "None") {
	try {
		cam.filterWheelConnect();
	} catch (e) {
		out = "SkyX filter wheel Connection Error: " + e;
		throw 'b';
	}
	cam.FilterIndexZeroBased = filter;
}
cam.asynchronous = asynchronous;
cam.ExposureTime = exptime;
cam.Delay = exp_delay;
cam.Series = nframes;

try{
	cam.TakeImage();
} catch (e) {
	out = "SkyX Camera Error during exposure: " + e;
	throw 'c';
}

out = cam.ExposureStatus + " success"