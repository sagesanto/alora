
# SHOULD LOOK AT THIS: https://github.com/dam90/tpoint

def main():
    import sys, os

    if len(sys.argv) != 2:
        print("Usage: python pointing_model.py <num points>")
        sys.exit(1)

    from os.path import dirname, abspath, join
    from astroquery.gaia import Gaia
    import numpy as np
    from python_tsp.heuristics import solve_tsp_local_search
    import time
    import matplotlib.pyplot as plt    
    from datetime import datetime
    from pytz import UTC

    from astropy.table import Table
    from astropy.coordinates import SkyCoord
    import astropy.units as u
    from astropy.io import fits
    from astropy.coordinates import Angle, SkyCoord, Latitude, Longitude
    from astropy.time import Time
    from astropy.coordinates import ICRS, FK5

    from alora.observatory.skyx import SkyXCamera, SkyXTelescope
    from alora.astroutils.obs_constraints import ObsConstraint
    from alora.observatory.observatory import Observatory
    from alora.astroutils.observing_utils import current_dt_utc, ang_sep
    from alora.config import config, configure_logger, logging_dir, observatory_location

    
    logger = configure_logger("pointing_model",join(logging_dir,"pointing_model.log"))

    logger.warning("RUNNING WITH CLOSED LOOP - WILL NOT PRODUCE A VALID POINTING MODEL")

    def dist_matrix(coords:SkyCoord):
        M = np.zeros((len(coords), len(coords)))
        indices = range(len(coords))
        for i in indices:
            for j in indices:
                if i < j:
                    s1, s2 = coords[i], coords[j]
                    t = ang_sep(s1,s2).to_value("degree")
                    M[i, j] = M[j, i] = t
        # because we're solving tsp but not returning to beginning: 
        M[:, 0] = 0
        return M

    cam_config = config["CAMERA"]
    pointing_config = config["POINTING_MODEL"]

    FIELD_WIDTH = cam_config["FIELD_WIDTH"]/60 
    FIELD_HEIGHT = cam_config["FIELD_HEIGHT"]/60 


    MAG_LIM = 11
    EXPTIME = pointing_config["EXPTIME"]
    FILTER = pointing_config["FILTER"]
    RADIUS = 0.5  # search radius, degrees
    NSAMPLES = sys.argv[1]
    BINNING = pointing_config["BIN"]
    MIN_BRIGHT_STARS = pointing_config["MIN_BRIGHT_STARS"]
    OUTDIR = join(pointing_config["OUTDIR"],current_dt_utc().strftime("%Y_%m_%d"))
    IMG_OUTDIR = join(OUTDIR,"imgs")
    os.makedirs(IMG_OUTDIR,exist_ok=True)
    
    rng = np.random.default_rng()
    tmo = ObsConstraint()

    coords = []
    t=current_dt_utc()
    lst = tmo.get_obs_lst()
    best_ras, best_decs, best_nums = [], [], []
    while len(best_ras) < NSAMPLES:
        RA = rng.uniform(0,360)
        DEC = rng.uniform(-90,90)
        if not tmo.observation_viable(dt=t,ra=RA*u.deg,dec=DEC*u.deg, current_sidereal_time=lst,ignore_night=True):
            continue
        query = f"""
        SELECT
        source_id,
        ra,
        dec,
        phot_g_mean_mag
        FROM
        gaiadr3.gaia_source
        WHERE
        1=CONTAINS(
            POINT('ICRS', ra, dec),
            CIRCLE('ICRS', {RA}, {DEC}, {RADIUS})
        )
        AND phot_g_mean_mag < {MAG_LIM}
        """

        logger.info(f"querying {RADIUS} degrees around {RA},{DEC}")
        job = Gaia.launch_job(query)

        results = job.get_results()
        logger.info(f"Found {len(results)} stars with mag < {MAG_LIM}")
        # results

        RESOLUTION = 50

        ras = np.linspace(RA-RADIUS,RA+RADIUS, RESOLUTION)
        decs = np.linspace(DEC-RADIUS,DEC+RADIUS, RESOLUTION)

        nums = np.empty((len(ras),len(decs)))


        best_num = 0
        best_ra, best_dec = None, None
        for i, ra in enumerate(ras):
            for j, dec in enumerate(decs):
                n_in_box = np.sum((results["ra"] >= ra-0.5*FIELD_WIDTH) & (results["ra"] <= ra+0.5*FIELD_WIDTH) & (results["dec"] >= dec-0.5*FIELD_HEIGHT) & (results["dec"] <= dec + 0.5*FIELD_HEIGHT))
                nums[i,j] = n_in_box
                if n_in_box > best_num:
                    best_ra = ra
                    best_dec = dec
                    best_num = n_in_box

        if best_num < MIN_BRIGHT_STARS:
            print(f"Could only find a spot with {best_num} sources. Moving on...")
            continue

        logger.info(f"Best spot: ({best_ra}, {best_dec}): {best_num} sources")
        best_ras.append(best_ra)
        best_decs.append(best_dec)
        best_nums.append(best_num)

    fields = Table()
    fields["ra"] = best_ras 
    fields["dec"] = best_decs
    fields["n_bright"] = best_nums
    fields = fields[fields["n_bright"] > 2]
    logger.info(fields)

    c = SkyCoord(fields["ra"]*u.deg,fields["dec"]*u.deg)
    M = dist_matrix(c)
    start = time.perf_counter()
    permutation, distance = solve_tsp_local_search(M)
    logger.info(f"Solved with n={len(c)} in t={time.perf_counter()-start}s")
    
    fields = fields[permutation]
    fname = join(OUTDIR,f"{t.strftime('%Y_%m_%d')}_pointing.csv")
    fields.write(fname,overwrite=True)
    logger.info(f"Wrote path to {fname}")

    plt.plot(fields["ra"],fields["dec"])
    plt.title(f"Proposed Pointing Model Run {t}")
    plt.xlabel("RA (deg)")
    plt.xlabel("Dec (deg)")
    plt.show()

    o = Observatory()
    o.connect(telescope=SkyXTelescope,camera=SkyXCamera)

    for i,(ra,dec) in enumerate(zip(fields["ra"], fields["dec"])):
        logger.info(f"{i+1}/{len(fields)} Slewing to ({ra},{dec})")
        o.telescope.slew(SkyCoord(ra*u.deg,dec*u.deg),closed_loop=True)   # WARNING CLOSED LOOP
        o.telescope.track_sidereal()
        time.sleep(2) # give it some time to start tracking
        prefiles = set(os.listdir(IMG_OUTDIR))
        o.camera.take_dataset(1,EXPTIME,FILTER,IMG_OUTDIR,name_prefix=f"im{i}",binning=BINNING)
        try:
            img = [f for f in os.listdir(IMG_OUTDIR) if f not in prefiles][0]
        except Exception as e:
            logger.error(f"Couldn't find a file for pointing {i+1}: {e}. (Is SkyX using a date-based subfolder?) Moving on.")
            continue

        o.plate_solver.solve(join(IMG_OUTDIR,img))


    # make tpoint file
    LATITUDE = str(Latitude(observatory_location.latitude*u.deg).to_string(sep=" ",pad=True,alwayssign=True))
    fitsfiles = [join(IMG_OUTDIR,f) for f in os.listdir(IMG_OUTDIR) if f.endswith(config["IMAGE_EXTENSION"])]
    with fits.open(fitsfiles[0]) as hdul:
        DATE = datetime.strptime(hdul[0].header["DATE-OBS"],"%Y-%m-%dT%H:%M:%S.%f")
    
    outfile = join(OUTDIR,f"pointing_{DATE.strftime('%Y%m%d')}.dat")
    d = {"temp":"10.00","pressure":"1000.00", "altitude":"1103.00","humidity":"0.50","wavelength":"0.5500","lapse rate":"0.0065"}
    fk5_apparent = FK5(equinox=Time(datetime.now(tz=UTC).year,format="jyear"))
    with open(outfile,"w+") as f:
        f.write(f"! Pointing Model: {DATE.strftime('%Y%m%d')}"+"\n")
        f.write("! Alora Observatory\n")
        f.write(":NODA\n")
        f.write(":EQUAT\n")  # is this right?
        f.write(f"{LATITUDE} {DATE.strftime('%Y %m %d')} {d['temp']} {d['pressure']} {d['altitude']} {d['humidity']} {d['wavelength']} {d['lapse rate']}\n")

        dRAs = []
        dDecs = []
        for fit in fitsfiles:
            with fits.open(fit) as hdul:
                header = hdul[0].header
            try:
                ra_ac = Angle(header["CRVAL1"]*u.deg)
            except KeyError:  # didnt solve
                continue
            dec_ac = Angle(header["CRVAL2"]*u.deg)

            coord = SkyCoord(ra_ac, dec_ac, frame='fk5')
            c2 = coord.transform_to(fk5_apparent)
            lst = header["LST"]
            lst_ang = Angle(lst,u.hourangle)
            round(lst_ang.hour,4)

            ra_ac_str = c2.ra.to_string(sep=" ",pad=True,unit="hourangle",precision=4)
            dec_ac_str = c2.dec.to_string(sep=" ",alwayssign=True,pad=True,precision=4)
            dRAs.append((Longitude(Angle(header['OBJCTRA'],unit="hourangle"))-Longitude(c2.ra)).degree)
            dDecs.append((Angle(header['OBJCTDEC'],unit="degree")-c2.dec).degree)
            lst_minute = (lst_ang.hour - int(lst_ang.hour)) * 60
            # plt.plot([(lst_ang-Angle(header['OBJCTRA'],unit="hourangle")).degree,(lst_ang-c2.ra).degree], [Angle(header['OBJCTDEC'],u.deg).degree,c2.dec.degree])
            f.write(f"{ra_ac_str} {dec_ac_str} {header['OBJCTRA']} {header['OBJCTDEC']}  {round(lst_ang.hour):02} {str(round(lst_minute,3)).rjust(6)} \n")
                # skyx already writes RA, Dec, LST to header

    print("All done!")
        # get RA, Dec from telescope
        # write telescope RA, Dec, sidereal time to fits header
        # lst = tmo.get_obs_lst(kind="apparent")
        # tele_pos = o.telescope.pos

        # with fits.open(join(IMG_OUTDIR,img)) as hdul:
        #     header = hdul[0].header
        #     header["RAW_RA"] = str(tele_pos.ra.to_value("deg"))
        #     header["RAW_DEC"] = str(tele_pos.dec.to_value("deg"))
        #     header["LST"] = str(lst.to_value("hourangle"))

    # generate points
        # determine zenith coords
        # query for bright groups of stars in v large area

    # for each point:
        # slew to location
        # start tracking
        # add_to_pointing_model

if __name__ == "__main__":
    main()