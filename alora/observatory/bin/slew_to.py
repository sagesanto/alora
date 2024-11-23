#! python

def main():
    from alora.observatory.observatory import Observatory
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    
    o = Observatory()
    o.connect()

    ra = 0*u.deg 
    dec = 34*u.deg
    coord = SkyCoord(ra,dec)
    print(f"Attempting to slew to {coord}.")
    o.telescope.slew(coord,closed_loop=False)

if __name__ == "__main__":
    main()