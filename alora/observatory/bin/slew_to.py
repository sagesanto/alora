#! python

def main():
    import argparse
    argparser = argparse.ArgumentParser(description="Slew the telescope to a given coordinate.")
    argparser.add_argument("ra", type=float, help="Right ascension in degrees.")
    argparser.add_argument("dec", type=float, help="Declination in degrees.")
    argparser.add_argument("-c","--closed-loop", action="store_true", default=False, help="Use closed-loop slew.")
    argparser.add_argument("-t","--track", action="store_true", default=False, help="Begin tracking at sidereal rate after slewing.")
    
    args = argparser.parse_args()

    from alora.observatory.observatory import Observatory
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    o = Observatory()
    o.connect()

    ra = args.ra*u.deg 
    dec = args.dec*u.deg
    coord = SkyCoord(ra,dec)
    print(f"Attempting to slew to {coord}.")
    o.telescope.slew(coord,closed_loop=args.closed_loop)
    print("Slew complete.")
    print(f"Telescope is at {o.telescope.pretty_pos()}.")
    if args.track:
        o.telescope.track_sidereal()
        print("Tracking at sidereal rate.")

if __name__ == "__main__":
    main()