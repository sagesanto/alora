#! python

def main():
    import argparse
    argparser = argparse.ArgumentParser(description="Take a dataset.")
    argparser.add_argument("exptime", type=float, help="Exposure time (seconds)")
    argparser.add_argument("nframes", type=int, help="Number of images to take.")
    argparser.add_argument("filter", type=str, help="Filter to use (str).")
    argparser.add_argument("outdir", type=str, help="Path to save images.")
    argparser.add_argument("prefix", type=str, help="Image prefix.")
    argparser.add_argument("-b","--binning", type=int, default=0, help="Binning factor.")
    argparser.add_argument("-d","--delay", type=float, default=0, help="Delay between exposures.")
    
    args = argparser.parse_args()    
    from alora.observatory.observatory import Observatory
    from alora.observatory.config import config
    o = Observatory()
    o.connect()
    binning = args.binning
    if binning == 0:
        binning = config["DEFAULTS"]["BIN"]

    print("Taking dataset...")
    o.camera.take_dataset(args.nframes,args.exptime,args.filter,args.outdir,name_prefix=args.prefix,binning=binning,exp_delay=args.delay)
    print("Done.")
if __name__ == "__main__":
    main()