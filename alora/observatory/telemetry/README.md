# Telemetry
The Telemetry service serves as a central hub for collecting data from various `Sensor` services. Sensors subclass the provided `Sensor` class. 

The Telemetry service creates database tables based on `Sensor` blueprints (descriptions of the types and format of the data that a `Sensor` will send), aggregates data from multiple of the same type of sensor, and keeps track of sensor uptime. `Sensor` objects will log data in local databases if they lose connection to the central Telemetry service, then merge the database back in when connection is regained. The Telemetry service then provides a data API that can be used to access the recorded data, and the python `DataFriend` object provides an object-oriented way to interact with the data API.

`Sensor` objects operate as a service and log measurements at some specified interval for the duration of their run.

The Telemetry and `Sensor` services interact through RPyC. 

[TOC]

## Sensor
### Overview
Sensors have a simple workflow:
- connect to the Telemetry service and provide a blueprint of the data they'll supply
- collect measurements at some interval
- report measurements to Telemetry

A sensor's blueprint outlines the names, types, and units of the data that will be provided with each sensor reading.
For example, a weather sensor's blueprint might look like 
```python
blueprint = {'air_density': ["FLOAT","kg/m3"],
'air_temperature': ["FLOAT", "C"],
'barometric_pressure': ["FLOAT", "mb"],
'brightness': ["INT","lux"],
'lightning_strike_count': ["INT", "unitless"],
'precip': ["FLOAT","mm"],
'precip_accum_last_1hr': ["FLOAT","mm"],
'pressure_trend': ['TEXT','unitless'],
'wind_direction': ["INT","degrees"],
'wind_gust': ["FLOAT", "m/s"],
'wind_lull': ["FLOAT", "m/s"]}
```
When initialized, `Sensor` implementations supply their friendly `sensor_name`, their `table_name` (a general name for the category of data that they'll be supplying), their `blueprint`, and a `polling_interval`. 
**NOTE:** Multiple `Sensor` objects that share the same `table_name` will have their data logged to the same to the same database table, so they must share the same blueprint!  
Example sensors in `alora.observatory.telemetry.sensors` are a good place to start when trying to write a sensor.

To start a Sensor, call its `run` method. *This is non-blocking, so will only run for as long as the script that called it continues to run.*

### Sensor services
`Sensor` objects come with a `write_service` method that writes a simple (and very bad!) batch script that can be run as a service to host the service perpetually. The script does not respond well to stop commands :\(. You probably shouldn't use it and should instead write your own simple script to run them as a service. 

## Data API
Sensor data can be accessed through the API at `http://127.0.0.1:<TELEM_API_PORT>`
### `/query` [GET] 
Get the results of a SQL SELECT query run against the Telemetry database
- Params:
    - `query` - `str`: SQL SELECT query to run against the database
- Response:
    - `result` - `dict`: dictionary representations of each row returned in response to query
    - `error` - `str`: error message if the query failed. Will be '' if query succeeded.
### `/blueprint` [GET]
Get the blueprint of each sensor currently connected to the telemetry service
- Response:
    - `result` - `list[dict]`:
        - `Blueprint` - `str`: the blueprint of the sensor
        - `SensorName` - `str`: the name of the sensor
        - `TableName` - `str`: the table that the sensor's measurements are written to
    - `error` - `str`: error message if this operation failed. Will be '' if it succeeded.

### `/status` [GET]
Get the latest connected status of each sensor
- Response:
    - `error` - `str`: '' if the operation succeeded. Exception will have been raised otherwise
    - `result` - `dict`: dictionary of sensor name to boolean (1 or 0) connected value
 
### `/weather` [GET]
Get the latest result from the Weather table
- `error` - `str`: '' if the operation succeeded. Exception will have been raised otherwise
- `result` - `dict`: weather data

## DataFriend
