def main():
    from os.path import join
    from astroquery.gaia import Gaia
    import numpy as np
    from python_tsp.heuristics import solve_tsp_local_search
    import time
    import matplotlib.pyplot as plt

    from astropy.table import Table
    from astropy.coordinates import SkyCoord
    import astropy.units as u

    from alora.observatory.skyx import SkyXCamera, SkyXTelescope
    from alora.maestro.scheduleLib.tmo import TMO
    from alora.observatory.observatory import Observatory
    from alora.maestro.scheduleLib.observing_utils import current_dt_utc, ang_sep
    from alora.observatory.config import config, configure_logger, logging_dir
    
    logger = configure_logger("pointing_model",join(logging_dir,"pointing_model.log"))

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

    FIELD_WIDTH = cam_config["FIELD_WIDTH"]/60 
    FIELD_HEIGHT = cam_config["FIELD_HEIGHT"]/60 

    MAG_LIM = 11
    RADIUS = 0.5  # search radius, degrees
    NSAMPLES = 5
    
    
    rng = np.random.default_rng()
    tmo = TMO()

    coords = []
    t=current_dt_utc()
    lst = tmo.get_current_tmo_sidereal_time()
    
    best_ras, best_decs, best_nums = [], [], []
    while len(best_ras) < NSAMPLES:
        RA = rng.uniform(0,360)
        DEC = rng.uniform(-90,90)
        if not tmo.observation_viable(dt=t,ra=RA*u.deg,dec=DEC*u.deg, current_sidereal_time=lst):
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

        if best_num < 3:
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
    fname = f"{t.strftime('%Y_%m_%d')}_pointing.csv"
    fields.write(fname,overwrite=True)
    logger.info(f"Wrote path to {fname}")

    plt.plot(fields["ra"],fields["dec"])
    plt.title("Proposed Pointing Model Run {t}")
    plt.xlabel("RA (deg)")
    plt.xlabel("Dec (deg)")
    plt.show()

    o = Observatory()
    o.connect(telescope=SkyXTelescope,camera=SkyXCamera)

    for i,(ra,dec) in enumerate(zip(fields["ra"], fields["dec"])):
        logger.info(f"{i+1}/{len(fields)} Slewing to ({ra},{dec})")
        o.telescope.slew(SkyCoord(ra*u.deg,dec*u.deg),closed_loop=False)
        o.telescope.track_sidereal()
        time.sleep(2) # give it some time to start tracking
        logger.info(o.camera.add_to_pointing_model(2))

    # generate points
        # determine zenith coords
        # query for bright groups of stars in v large area

    # for each point:
        # slew to location
        # start tracking
        # add_to_pointing_model

if __name__ == "__main__":
    main()