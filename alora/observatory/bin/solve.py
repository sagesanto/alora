#! python

def main():
    import argparse
    import os
    from os.path import join, abspath
    from alora.config import config
    from alora.observatory.astrometry import Astrometry
    
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="+", type=str, help="The images to solve or directory to solve")
    parser.add_argument("--scale","-s",default=config["CAMERA"]["FIELD_WIDTH"], help="The width of the field, in arcmin")
    args = parser.parse_args()

    paths = args.paths
    ast = Astrometry()
    ast.scale = args.scale
    for path in paths:
        path = abspath(path)
        if os.path.isdir(path):
            print("Solving dir")
            for f in os.listdir(path):
                ast.solve(join(path,f),synchronous=True)
        else:
            ast.solve(path,sync=True)

if __name__ == "__main__":
    main()