# Choir: Notification Service
Choir is the notification service for Alora Observatory. The observer-subscriber model allows arbitrary subscribers to recieve notification events for distribution to outside services (eg Slack).

The `Vocalist` object is a lightweight Python interface for programs to use to send notifications to Choir for distribution.
[TOC]

## Choir API
Choir offers the following endpoints on `http://127.0.0.1:{CHOIR_PORT}`:
### `/subscribe` [POST] 
Sign a `Subcriber` up for notifications from Choir
- Params:
    - `webhook_url` - `str`: the url to which Choir should send notifications (see `Subscriber`'s `setup_routes` and `receive` methods)
    - `severity` - `str`: the minimum severity level of notifications that the subscriber would like to receive events for. must be one of `'info'`, `'warning'`, `'error'`, `'critical'`
    - `name` - `str`: friendly name of the subscriber. for logging purposes 
- Response:
        - `status` - `str`: `'success'` if the operation succeeded.
### `/unsubscribe` [POST]
As a `Subscriber`, use `/unsubscribe` to no longer recieve notifications from Choir
- Params:
    - `webhook_url` - `str`: the same url which was used when the `Subscriber` signed up with `/subscribe`
- Response:
    - `status` - `str`: `'success'` if the operation succeeded.

### `/health` [GET]
Check the health of Choir
- Response:
    - `status` - `str`: `'healthy'` (if a response is recieved, the service is healthy)
    - `subscribers` - `dict[str:str]`: a dictionary of `{webhook_url : severity}` for each registered `Subscriber`
### `/notify` [POST]
Prompt Choir to create and distribute a notification
- Params:
    - `source` - `str`: display name for the source of this alert. should help the end users understand the origin and relevance of the alert.
    - `topic` - `str`: like a 'subject line' for the alert. should *very briefly* give an idea of the topic of the alert (eg: "Dome Watchdog")
    - `severity` - `str`: the severity of the alert. must be one of `'info'`, `'warning'`, `'error'`, `'critical'`
    - `msg` - `str`: the content of the alert.
- Response:
    - `status` - `str`: `'success'` if the operation succeeded.

## Subscriber API
Each `Subscriber` implementation listens on its own `webhook_url` for the following events:
### `/` [POST]
The Choir service uses this endpoint to provide the `Subscriber` with alerts. The `Subscriber` should override the `setup_routes` Python function to do something useful with the alert.
- Params:
    - `source` - `str`: the display name of the internal system/service that generated this alert
    - `topic` - `str`: a brief summary of the general topic of the alert
    - `severity` - `str`: the severity level of the alert. will be one of `'info'`, `'warning'`, `'error'`, `'critical'`
    - `msg` - `str`: the content of the alert
    - `timestamp` - `str`: the UTC time that the alert was generated. The datetime format is `'%Y-%m-%d %H:%M:%S UTC'`
- Response:
    - `status` - `str`: `'success'` if the operation succeeded.

## Vocalist
The `Vocalist` object can be imported from `alora.observatory.choir` and provides a simple interface for programs to easily generate Choir alerts.
### Usage
We begin by initializing the `Vocalist` object with the display name (source) that this Vocalist's objects will be associated with. this name should help end users understand/trace the origin of the alert.
```python
from alora.observatory.choir import Vocalist
vocalist = Vocalist("Weather Watchdog")  
```
We can use this `Vocalist` object to send an alert to Choir for distribution. We must specify the `severity` as one of `'info'`, `'warning'`, `'error'`, `'critical'`. `Subscriber` objects specify to Choir the minimum severity level of alert that they want to receive to avoid oversaturating their end users. Think carefully about the severity of your message - will you drown out other alerts from other services?  
```python
vocalist.notify(severity="critical",topic="Weather Alert!",msg=f"Weather safety check failed due to error: {e}")
```
An equivalent way to send an identical alert would be to call `Vocalist.critical` instead of specifying the severity as "critical":
```python
vocalist.critical(topic="Weather Alert!",msg=f"Weather safety check failed due to error: {e}")
```
`Vocalist.info`, `Vocalist.warning`, and `Vocalist.error` work analogously. 

By default, the `source` of this message will be the `name` that we initialized the Vocalist object with. We can override that for specific messages if we want to, but this is generally discouraged as it makes things more confusing. This message would appear to come from the "Backup Weather Watchdog:"
 ```python
vocalist.critical(topic="Different weather alert!",msg="Weather safety check failed on secondary weather station!", source="Backup Weather Watchdog")
```