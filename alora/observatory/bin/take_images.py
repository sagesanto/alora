#! python

def main():
    import os
    from os.path import exists, join
    import argparse
    argparser = argparse.ArgumentParser(description="Take a dataset.")
    argparser.add_argument("exptime", type=float, help="Exposure time (seconds)")
    argparser.add_argument("nframes", type=int, help="Number of images to take.")
    argparser.add_argument("filter", type=str, help="Filter to use (str).")
    argparser.add_argument("outdir", type=str, help="Path to save images.")
    argparser.add_argument("prefix", type=str, help="Image prefix.")
    argparser.add_argument("-b","--binning", type=int, default=0, help="Binning factor.")
    argparser.add_argument("-d","--delay", type=float, default=0, help="Delay between exposures.")
    argparser.add_argument("-s", "--solve", action="store_true", default=False, help="Solve the images.")
    
    args = argparser.parse_args()    
    from alora.observatory.observatory import Observatory
    from alora.observatory.config import config
    o = Observatory()
    o.connect()
    binning = args.binning
    if binning == 0:
        binning = config["DEFAULTS"]["BIN"]

    existing_ims = []
    if args.solve:
        if exists(args.outdir):
            existing_ims = [f for f in os.listdir(args.outdir) if f.endswith(".fit")]

    print("Taking dataset...")
    o.camera.take_dataset(args.nframes,args.exptime,args.filter,args.outdir,name_prefix=args.prefix,binning=binning,exp_delay=args.delay)
    print("Done taking data.")

    if args.solve:
        to_solve = [f for f in os.listdir(args.outdir) if f.endswith(".fit") and f not in existing_ims]
        print("Solving {len(to_solve)} images...")
        if len(to_solve) == 1:
            print(o.camera.solve(join(args.outdir,to_solve[0])))
        if len(to_solve) > 1:
            print(o.camera.batch_solve([join(args.outdir,f) for f in to_solve]))

if __name__ == "__main__":
    main()