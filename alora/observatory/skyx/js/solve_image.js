cam = ccdsoftCamera;
var Out="";
iml = ImageLink;
function solve(impath)
{
    //ImageLink.pathToFITS = cam.LastImageFileName;
    iml.pathToFITS = impath
    iml.Scale = {{scale}};
    iml.unknownScale = 0;

    iml.execute();

    r = ImageLinkResults;
    if(r.succeeded){
        return "success " + String(r.imageScale) +" " + String(r.imageFWHMInArcSeconds) ;
    } else {
        return r.errorCode
    }
}

out = solve({{impath}})
