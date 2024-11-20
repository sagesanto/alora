var out;
sky6RASCOMTele.Connect();

if (!sky6RASCOMTele.IsConnected)
{
    out = "Could not connect to telescope";
    throw ""
}

sky6RASCOMTele.Asynchronous=false;
sky6RASCOMTele.Park();

// the park function disconnects the mount once it's done.
// therefore by returning the connection status we're checking whether park completed 
out = !sky6RASCOMTele.IsConnected; 