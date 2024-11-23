var out = 0;

sky6RASCOMTele.Connect();

if (!sky6RASCOMTele.IsConnected)
{
    out = "Could not connect to telescope";
    throw ""
}

sky6RASCOMTele.Asynchronous=false;

sky6RASCOMTele.SetTracking(0,1,0,0)  // stop tracking
out = sky6RASCOMTele.IsTracking;