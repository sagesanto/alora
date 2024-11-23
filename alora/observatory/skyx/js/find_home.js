var out;

sky6RASCOMTele.Connect();
sky6RASCOMTele.Asynchronous=false;
sky6RASCOMTele.FindHome();

sky6RASCOMTele.SetTracking(0,1,0,0) // stop tracking
out = sky6RASCOMTele.LastSlewError