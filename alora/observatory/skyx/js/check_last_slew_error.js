var out;
sky6RASCOMTele.Connect();
out = sky6RASCOMTele.IsConnected; 

if (sky6RASCOMTele.IsConnected==0) {out = "Not connected"}
else {
    out = sky6RASCOMTele.LastSlewError;
}