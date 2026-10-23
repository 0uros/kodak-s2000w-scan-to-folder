# Connecting a Windows 10 / 11 PC

1. **This PC → Map network drive**.
2. Drive **S:**, folder `\\<server>\<Share>` (for example `\\scans.example.org\FrontDesk`).
3. Tick **Reconnect at sign-in** and **Connect using different credentials**.
4. User `<server-name>\<user>` (for example `scans\frontdesk`) and the share password. Tick
   **Remember my credentials**.

Or from `cmd` (the `*` makes it ask for the password without showing it):

```
net use S: \\scans.example.org\FrontDesk /user:scans\frontdesk * /persistent:yes /savecred
```

| Problem | Fix |
|---|---|
| System error 1219 ("multiple connections … by the same user") | Windows allows one user per server. Remove the old mapping (`net use * /delete`) and map again. A PC that needs several shares should use the admin user. |
| Asks for the password at every sign-in | **Remember my credentials** was not ticked. Remove the entry in **Credential Manager → Windows Credentials** and map again. |
| Server not found | Try `\\<server-ip>\<Share>`. If the IP works, the PC is not using the DNS server that knows the name. |
| Access denied right away on Windows 11 24H2 | The server must allow signing and refuse guest access; `samba/smb.conf.global` already does. |

Deleted files go to the hidden `.recycle` folder inside the share (**View → Show → Hidden items**) for 30 days.
