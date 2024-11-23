var out = 0;

sky6RASCOMTele.Connect();

if (!sky6RASCOMTele.IsConnected)
{
    out = "Could not connect to telescope";
    throw ""
}

sky6RASCOMTele.Asynchronous=false;
sky6RASCOMTele.ParkAndDoNotDisconnect();

out = sky6RASCOMTele.SlewToRaDec({{ra}}, {{dec}}, "object");