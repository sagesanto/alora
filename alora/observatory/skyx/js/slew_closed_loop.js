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

//Do the closed loop slew synchronously
ClosedLoopSlew.exec();
// sky6RASCOMTele.SetTracking(1,1,0,0)  // start tracking at sidereal rate
out = sky6RASCOMTele.LastSlewError;