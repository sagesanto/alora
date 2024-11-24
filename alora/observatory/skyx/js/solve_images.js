cam = ccdsoftCamera;
var out="";
iml = ImageLink;
iml.Scale = {{imscale}};
iml.unknownScale = 0;

function solve(impath)
{
    iml.pathToFITS = impath

    try{
        iml.execute();
    } catch(e){
        // return "0 " + "%{"+e+"}% ";
    }
    r = ImageLinkResults;
    if(r.succeeded){
        return "1 " ;
    } else {
        return "0 "+ "%{" + r.errorText+"}% ";
    }
}
for (let im of [{{impaths}}]){
    out = out + solve(im)
}