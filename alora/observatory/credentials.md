# Credential Management
The observatory accesses credentials through the `keyring` module. To add credentials, do the following from a python shell:

```
>>> import keyring
>>> keyring.set_password("system", "username", "password")
```

# Credentials
The package expects *all* of the following credentials to appear in the computer's `keyring`:

## Telemetry
### Weather
- `weather`, username `token`
    - token to access weather info


## Dome
- `dome`, username `addr`
    - address to dome
- `dome`, username `user`
    - dome login username
- `dome`, username `password`
    - dome login password

## Choir
### Slack
- `slack`, username `token`
    - self-explanatory