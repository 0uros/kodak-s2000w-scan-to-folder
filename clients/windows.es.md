# Conectar una PC con Windows 10 / 11

[English](windows.md) · **Español**

1. **Este equipo → Conectar unidad de red**.
2. Unidad **S:**, carpeta `\\<servidor>\<Carpeta>` (por ejemplo `\\escaneos.ejemplo.org\MesaDeEntradas`).
3. Marcar **Conectar de nuevo al iniciar sesión** y **Conectar con otras credenciales**.
4. Usuario `<nombre-del-servidor>\<usuario>` (por ejemplo `escaneos\mesa`) y la clave de la carpeta. Marcar
   **Recordar mis credenciales**.

O desde `cmd` (el `*` hace que pida la clave sin mostrarla):

```
net use S: \\escaneos.ejemplo.org\MesaDeEntradas /user:escaneos\mesa * /persistent:yes /savecred
```

| Problema | Solución |
|---|---|
| Error del sistema 1219 ("no se permiten varias conexiones … del mismo usuario") | Windows permite un solo usuario por servidor. Quitar la conexión anterior (`net use * /delete`) y volver a conectar. Una PC que necesita varias carpetas debería usar el usuario de administración. |
| Pide la clave en cada inicio de sesión | No se marcó **Recordar mis credenciales**. Borrar la entrada en **Administrador de credenciales → Credenciales de Windows** y volver a conectar. |
| No encuentra el servidor | Probar con `\\<ip-del-servidor>\<Carpeta>`. Si con la IP funciona, la PC no está usando el servidor DNS que conoce el nombre. |
| Acceso denegado enseguida en Windows 11 24H2 | El servidor tiene que permitir la firma y rechazar el acceso como invitado; `samba/smb.conf.global` ya lo hace. |

Lo que se borra va a la carpeta oculta `.recycle`, dentro de la carpeta compartida (**Vista → Mostrar →
Elementos ocultos**), y se conserva 30 días.
