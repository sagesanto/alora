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
        return "0 " + "%{"+e+"}% ";
    }
    r = ImageLinkResults;
    if(r.succeeded){
        return "1 " ;
    } else {
        return "0 "+ "%{" + r.errorText+"}% ";
    }
}
const impaths = [{{impaths}}];
for (i = 0; i < impaths.length; ++i) {
    const im = impaths[i];
    out = out + solve(im)
}
out = out