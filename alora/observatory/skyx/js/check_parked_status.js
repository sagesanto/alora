var out;
sky6RASCOMTele.ConnectAndDoNotUnpark();

if (sky6RASCOMTele.IsConnected==0) {out = "Not connected"}
else {
    out = sky6RASCOMTele.IsParked()
}