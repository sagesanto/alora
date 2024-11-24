cam = ccdsoftCamera;
var Out="";
iml = ImageLink;
function solve(impath)
{
    //ImageLink.pathToFITS = cam.LastImageFileName;
    iml.pathToFITS = impath
    iml.Scale = {{imscale}};
    iml.unknownScale = 0;

    try{
        iml.execute();
    } catch(e){
        return e
    }
    r = ImageLinkResults;
    if(r.succeeded){
        return "success " + String(r.imageScale) +" " + String(r.imageFWHMInArcSeconds) ;
    } else {
        return "Solving image failed: "+ r.errorText
    }
}

out = solve("{{impath}}")
