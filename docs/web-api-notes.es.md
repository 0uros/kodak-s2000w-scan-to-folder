# Web API de los Kodak Alaris S2000w: notas de campo

[English](web-api-notes.md) · **Español**

Lo que aprendimos al hacer que un Kodak Alaris **S2080w** escanee a una carpeta de red sin PC. Estas notas
deberían valer también para el **S2060w**, el otro modelo de red de la serie S2000w. Probado con los firmwares
**210503** (2021) y **230802** (diciembre de 2023, el último disponible al escribir esto).

## La documentación oficial

Kodak Alaris publicó un **"WebAPI Toolkit"** para sus escáneres de red: la guía *A-61872, "WebAPI Guide for
Alaris Network Enabled Scanners"* (septiembre de 2023), un PDF de inicio rápido ("Easy Start") y ejemplos en
Python. El más parecido a este proyecto es `KaBgbScanningApp.py`, la aplicación del "botón verde grande".

**Ya no está en el sitio de Kodak**: el enlace de descarga devuelve "Page Not Found". El Internet Archive
guardó una copia de la versión 2.2 (13/10/2023, 37 MB):

<https://web.archive.org/web/20250108033544/https://resources.kodakalaris.com/docimaging/drivers/Kodak_Alaris_WebAPI%20_Toolkit_v2.2.20231013115131.zip>

No se incluye en este repositorio porque no tiene una licencia que permita redistribuirlo.

## Los "destinos FTP" ocultos no funcionan

La página web interna del escáner tiene una pestaña oculta **Destinations**. Kodak la sacó del menú
(`setup.html` tiene el comentario "remove destination tab"), pero `/scripts/ftp.js` y los endpoints siguen ahí:

| Llamada | Resultado con los firmwares 210503 y 230802 |
|---|---|
| `GET /api/scanner/DestInfo?PCID=Destination:FTP-1234-5678-90ABCD&ADMIN_PASSWORD=` | Siempre `"NumDests":"0"` |
| `POST /api/scanner/destftp` (perfil en JSON: sitio FTP, usuario, clave, nombre de lote, color, DPI, dúplex, saltar blancos, inicio automático; en el código web `ButtonNumber` empieza en 1) | **HTTP 200** y devuelve el perfil, pero **no guarda nada**: la lista sigue vacía y no aparece nada en la pantalla |
| `POST /api/scanner/testFTP?PCID=...&ButtonNumber=1` | **501 Not Implemented** |

El FTP no aparece en ninguna nota de versión del firmware ni en la guía oficial de la API. Parece una función
que quedó sin terminar. **No vale la pena perder tiempo con eso.** Los escáneres tampoco tienen eSCL/AirScan
(`/eSCL/ScannerCapabilities` da 404), así que el backend `airscan` de SANE tampoco puede manejarlos.

## Lo que funciona: la API de sesión

Todas las llamadas son por HTTPS a la IP del escáner (certificado autofirmado). Los cuerpos van en JSON.

```
POST   /api/session                         {"OCPUserName": "Escanear a Mesa"}   → {"SessionId": "..."}
PUT    /api/session?SessionId=ID            {"Configuration": {"DPI":300, "ScanSide":"Duplex", ...}}
POST   /api/session/StartScan?SessionId=ID
GET    /api/session/status?SessionId=ID     → {"Status": {"State", "NumImagesScanned", "PaperDetected", ...}}
GET    /api/session/image/N?SessionId=ID    → image/jpeg (N = 1, 2, ...)
DELETE /api/session/image/N?SessionId=ID    → libera memoria del escáner
DELETE /api/session?SessionId=ID            → termina la sesión, el escáner queda libre
GET    /api/scanner/status                  → estado y OCPUserName, sin sesión
GET    /api/scanner/capabilities?V2         → todas las opciones y sus valores posibles
```

- **`OCPUserName`** se muestra en la pantalla del escáner (OCP = Operator Control Panel) mientras la sesión
  está abierta. Sirve para indicar a dónde va a parar el escaneo.
- Después de `StartScan` el escáner espera el papel. Con `"AutoStart": 1` arranca al detectar el papel,
  aunque la pantalla puede pedir confirmación. `PaperDetected` indica si hay papel en la bandeja.
- **Las imágenes llegan mientras escanea**: consultar el estado más o menos una vez por segundo, bajar
  `image/N` hasta `NumImagesScanned` y después hacer `DELETE`, para que los lotes largos no llenen la memoria
  del escáner.
- Cada cara es un JPEG aparte: en dúplex son dos imágenes por hoja, frente y dorso. A 300 dpi en color, una A4
  mide unos 2474×3516 px y pesa entre 180 y 550 KB.
- Cuando `State` pasa a `Done Scanning`, el lote está completo.

### Trampas

1. **`NumImagesScanned` vuelve a 0 en cada `StartScan`.** El contador de imágenes tiene que ser por lote, no
   por sesión. Si no, el segundo lote nunca se baja (así perdimos un lote durante las pruebas).
2. **Una sesión sirve para muchos lotes.** Después de `Done Scanning`, se vuelve a llamar a `StartScan` en la
   misma sesión.
3. **La sesión vence a los 5 minutos sin llamadas de sesión.** `GET /api/session/status` la renueva;
   `GET /api/scanner/status`, no.
4. **Una sesión bloquea el escáner.** Cualquier otro cliente (Smart Touch, el driver TWAIN, otro script)
   recibe **HTTP 423 Locked** hasta que la sesión termina o vence. Por eso este proyecto dedica cada escáner a
   una carpeta.
5. **HTTP 408** al crear la sesión significa que el escáner se está despertando: reintentar al segundo.
6. **`SkipBlankPages: 1` no descartó los dorsos en blanco en modo color** en nuestros S2080w. Este proyecto
   saca las páginas en blanco por su cuenta: una hoja en blanco tenía 0,0002 % de puntos oscuros, y la página
   real con menos contenido, 2,1 %.
7. Según la guía, los firmwares nuevos validan en forma estricta: los números tienen que ir como números
   (`"AutoStart": 1`, no `"1"`) o se recibe HTTP 406. Nosotros siempre mandamos números.

## Tiempos medidos con un S2080w real

| Lote | Escáner → servidor | PDF con OCR en español (contenedor de 4 vCPU) |
|---|---|---|
| 1 hoja, dúplex | 2 s | 3,5 s |
| 4 páginas (+1 en blanco salteada) | inmediato | 10 s |
| 15 páginas | inmediato | 34–35 s |
