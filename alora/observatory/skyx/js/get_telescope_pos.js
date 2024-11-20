var out;
sky6RASCOMTele.Connect();
out = sky6RASCOMTele.IsConnected; 

if (sky6RASCOMTele.IsConnected==0) {out = "Not connected"}
else {
    sky6RASCOMTele.GetRaDec();
    out  = String(sky6RASCOMTele.dRa) +" " + String(sky6RASCOMTele.dDec);
}