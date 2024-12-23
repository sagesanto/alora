# Alora Config Files

### logging.json
Change this to change the logging format. See https://docs.python.org/3/library/logging.config.html

### config.toml
The primary config file for the Alora package.

### horizon_box.json
A json file that stores the telescope pointing limits. Limits are stored in the following format:
[
    [min DEC_0, max DEC_0], [min HA_0, max HA_0],
    [min DEC_1, max DEC_1], [min HA_1, max HA_1],
    ...
    [min DEC_N, max DEC_N], [min HA_N, max HA_N],
]
where min HA_i and max HA_i are the minimum and maximum allowed pointing hour angles for the dec range (min DEC_i, max DEC_i)
DEC ranges over (-90, 90) and HA over (-180,180).  