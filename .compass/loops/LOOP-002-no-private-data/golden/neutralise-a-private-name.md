# Golden pattern: neutralise a private name and a home path

A research finding that names a private project and a user's home directory keeps its numbers and its conclusion; only the identifying text changes. The names below are invented.

## Before

```
| `F:\Clientco\Python\billing-sync` | 388 | |
Probes ran in `C:\Users\jdoe\AppData\Local\Temp\claude\F--repo\<a 36-character session uuid>\scratchpad\probe\`.
```

## After

```
| work project A | 388 | |
Probes ran in `~\AppData\Local\Temp\claude\F--repo\<session>\scratchpad\probe\`.
```

## Why

The count, the table row and the location's kind survive; the client, the project, the user name and the session id do not. The same name maps to the same placeholder everywhere in one file.
