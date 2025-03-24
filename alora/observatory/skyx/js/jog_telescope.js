var out;

sky6RASCOMTele.Connect();

if (!sky6RASCOMTele.IsConnected)
{
    out = "Could not connect to telescope";
    throw ""
}

sky6RASCOMTele.Asynchronous=false;

if ({{dRA}} != 0) {
    sky6RASCOMTele.Jog({{dRA}},"{{ra_dir}}");
}

if ({{dDec}} != 0) {
    sky6RASCOMTele.Jog({{dDec}},"{{dec_dir}}");
}

out = 0;