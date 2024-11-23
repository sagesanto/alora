var out;

sky6RASCOMTele.Connect();
sky6RASCOMTele.Asynchronous=false;
sky6RASCOMTele.FindHome();

out = sky6RASCOMTele.LastSlewError
sky6RASCOMTele.SetTracking(0,1,0,0) // stop tracking