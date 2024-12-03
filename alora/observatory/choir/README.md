# Choir: Notification Service
Choir is the notification service for Alora Observatory. The observer-subscriber model allows arbitrary subscribers to recieve notification events for distribution to outside services (eg Slack).

The `Vocalist` object is a lightweight Python interface for programs to use to send notifications to Choir for distribution.
[TOC]

## Choir API
Choir offers the following endpoints on `http://127.0.0.1:{CHOIR_PORT}`:
### `/subscribe` [POST] 
Sign a `Subcriber` up for notifications from Choir
- Params:
    - `webhook_url` - `str`: the url to which Choir should send notifications (see `Subscriber`'s `receive` method)
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
    - `subscribers` - `dict[str:str]`: a dictionary of `{webhook_url : severity}` for each registered subscriber
### `/notify` [POST]
Prompt Choir to create and distribute a notification
- Params:
    - `source` - `str`: display name for the source of this alert. should help the end users understand the origin and relevance of the alert.
    - `topic` - `str`: like a 'subject line' for the alert. should *very briefly* give an idea of the topic of the alert (eg: "Dome Watchdog")
    - `severity` - `str`: the severity of the alert. must be one of `'info'`, `'warning'`, `'error'`, `'critical'`
    - `msg` - `str`: the content of the alert.
- Response:
    - `status` - `str`: `'success'` if the operation succeeded.