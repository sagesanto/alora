var out=0;

sky6StarChart.RightAscension = {{ra}};
sky6StarChart.Declination = {{dec}};

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
let orig_bin = ccdsoftCamera.BinX;
ccdsoftCamera.BinX = {{binning}};
ccdsoftCamera.BinY = {{binning}};

try{
    ClosedLoopSlew.exec();
    ccdsoftCamera.BinX = orig_bin;
    ccdsoftCamera.BinY = orig_bin;
}
catch(e){
    ccdsoftCamera.BinX = orig_bin;
    ccdsoftCamera.BinY = orig_bin;
    out = "SkyX Closed Loop Slew Error: " + e;
    throw out;
}
    // sky6RASCOMTele.SetTracking(1,1,0,0)  // start tracking at sidereal rate
out = sky6RASCOMTele.LastSlewError;