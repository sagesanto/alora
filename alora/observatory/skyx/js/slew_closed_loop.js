var out=0;

c = sky6StarChart
c.RightAscension = {{ra}};
c.Declination = {{dec}};
c.ClickFind(c.WidthInPixels/2,c.HeightInPixels/2)

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

try{
    ClosedLoopSlew.exec();
    ccdsoftCamera.BinX = orig_bin;
    ccdsoftCamera.BinY = orig_bin;
}
catch(e){
    ccdsoftCamera.BinX = orig_bin;
    ccdsoftCamera.BinY = orig_bin;
    out = "SkyX Closed Loop Slew Error: " + String(e);
    throw out;
}
    // sky6RASCOMTele.SetTracking(1,1,0,0)  // start tracking at sidereal rate
out = sky6RASCOMTele.LastSlewError;