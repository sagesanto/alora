var out = 0;

sky6RASCOMTele.Connect();

if (!sky6RASCOMTele.IsConnected)
{
    out = "Could not connect to telescope";
    throw ""
}

sky6RASCOMTele.Asynchronous=false;

sky6RASCOMTele.SetTracking(1,0,{{dRA}},{{dDec}})  // start tracking at custom rate
out = sky6RASCOMTele.IsTracking;