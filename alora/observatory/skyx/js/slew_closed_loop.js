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

//Do the closed loop slew synchronously
out = ClosedLoopSlew.exec();