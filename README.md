
ComensalQR

Sistema web para el control de almuerzos de trabajadores mediante códigos QR.

Estado del proyecto

MVP v0.1 — En desarrollo

La primera versión de ComensalQR tiene un objetivo simple:

«Permitir que un restaurante registre quién almorzó, a qué empresa pertenece y cuándo lo hizo.»

El sistema está diseñado para comenzar de forma sencilla y permitir nuevas funcionalidades en futuras versiones.

---

🎯 Objetivo del MVP

ComensalQR debe permitir al restaurante responder rápidamente:

- ¿Cuántas personas almorzaron hoy?
- ¿Quiénes almorzaron?
- ¿De qué empresa pertenece cada persona?
- ¿A qué hora almorzó cada trabajador?

---

🔄 Funcionamiento básico

El flujo principal es:

Trabajador
↓
Muestra su QR
↓
Operador escanea QR
↓
Sistema identifica al trabajador
↓
Obtiene su empresa
↓
Verifica si ya almorzó ese día
↓
Registra el consumo
↓
Guarda fecha y hora
↓
Actualiza el dashboard

El proceso debe ser rápido y sencillo para que pueda utilizarse durante un servicio de almuerzos con muchas personas.

---

👤 Roles

Administrador

El administrador puede:

- Crear y administrar empresas.
- Crear y administrar locales del restaurante.
- Crear y administrar trabajadores.
- Generar y administrar códigos QR.
- Consultar los consumos.
- Consultar el dashboard.
- Consultar el historial.

Operador

El operador es la persona encargada de registrar los almuerzos.

Puede:

- Abrir el escáner.
- Escanear un QR.
- Ver el nombre del trabajador, la empresa y el resultado.

Un QR válido registra el consumo automáticamente si el trabajador aún tiene
cupo diario («Almuerzo 1 de 2 registrado»). Si el cupo está agotado, el sistema
lo informa y no crea otro registro.

El escáner ocupa toda la pantalla del teléfono: el resultado aparece en grande
sobre la cámara (verde **Registrado**, naranja **Cupo agotado**, rojo **No válido**)
con sonido y vibración distintos, y la cámara nunca se pausa, por lo que el
siguiente trabajador puede escanear de inmediato. Arriba se muestra el total de
almuerzos del día; abajo están la linterna (si el teléfono la tiene), el registro
manual y los últimos 5 registros del operador. La pantalla no se apaga mientras
el escáner está abierto.

**Registro manual por RUT:** si el trabajador no trae ni tarjeta ni teléfono, el
operador busca su RUT y elige la empresa. El consumo respeta el mismo cupo, queda
marcado como «manual» en el historial y registra qué operador lo hizo.

El operador solo consulta el historial del día en curso. El administrador
puede desactivar operadores, cambiarles el local o asignarles una clave nueva
desde **Operadores**.

Cada operador está asignado a un local, y cada consumo guarda el local del
operador que lo registró. El historial se puede filtrar por local y el
dashboard muestra el total por local cuando hay más de uno. Los consumos que
registra un administrador quedan sin local. Un local con operadores o consumos
no se puede eliminar, solo desactivar.

El operador no debe tener acceso a información administrativa innecesaria.

---

🏢 Empresas

Cada trabajador pertenece a una empresa.

Ejemplo:

Empresa:
Constructora ABC

Trabajadores:
- Juan Pérez
- María Soto
- Pedro Díaz

El sistema debe permitir consultar cuántos trabajadores de cada empresa han almorzado.

---

👤 Trabajadores

Cada trabajador debe tener:

- Nombre.
- Apellido.
- RUT.
- Empresa.
- Estado.
- Identificador único para su QR.

El trabajador no necesita una cuenta de usuario para utilizar el sistema.

---

📱 Código QR

Cada trabajador tendrá un QR único.

El QR no debe contener directamente información personal.

No debe incluir:

- RUT.
- Nombre.
- Apellido.
- Empresa.

El QR debe contener solamente un identificador o token aleatorio que permita al sistema identificar al trabajador.

Ejemplo conceptual:

worker_token = 8f72a91c-4e21-...

El teléfono del operador escanea el código y consulta al sistema.

### Importación masiva de trabajadores

Desde el listado de trabajadores de una empresa (o su perfil), **Importar desde Excel** permite cargar la nómina completa:

1. Descarga la plantilla Excel (columnas `nombre`, `apellido`, `rut` y `almuerzos_diarios` opcional).
2. Sube el archivo `.xlsx` o `.csv` (se aceptan `,` y `;`, y codificación UTF-8 o la de Excel en Windows). Máximo 2 MB y 2000 filas.
3. Revisa la vista previa. Si alguna fila tiene errores (RUT inválido, repetido en el archivo o ya vigente en la empresa, nombre faltante, cupo fuera de 1–10) no se importa nada.
4. Confirma: se crean todos los trabajadores en una sola transacción, cada uno con su QR.

### Tarjetas QR: papel y teléfono

Cada trabajador recibe el **mismo QR en dos formatos**, para que uno respalde al otro:

- **Tarjeta impresa:** PDF A4 con 6 tarjetas por hoja y líneas de corte.
- **Imagen para teléfono:** PNG vertical de 1080×1920 para guardar en la galería.

Se pueden descargar por trabajador, para los seleccionados en el listado, para todos los trabajadores activos de la empresa o, tras una importación, para los recién importados. Los archivos se generan al momento y no se guardan en el servidor.

Si un trabajador pierde la tarjeta o el teléfono, o comparte la imagen, usa **Regenerar QR**: se invalidan ambos formatos y hay que entregarle los nuevos.

### Desvinculación de trabajadores

El administrador puede usar **Eliminar trabajador** desde el listado de una empresa. Esta operación es lógica: conserva el registro, el UUID QR y los consumos históricos, y almacena la fecha y el administrador que realizó la desvinculación. El trabajador queda inactivo, desaparece del listado vigente y no puede registrar nuevos consumos. Los registros desvinculados se consultan con el filtro «Ver trabajadores eliminados». La eliminación física está deshabilitada en Django Admin.

Cada empresa es un universo independiente. El RUT es único **por empresa** entre trabajadores vigentes: una misma persona puede trabajar en varias empresas a la vez, con un registro, un QR y un historial separados en cada una. Si se desvincula de una empresa, solo se bloquea el QR de esa empresa.

---

🍽️ Registro de consumo

Cuando un trabajador almuerza:

QR → Identificación → Empresa → Registro

El sistema registra:

- Trabajador.
- Empresa.
- Fecha.
- Hora.
- Operador que realizó el registro.

Ejemplo

Juan Pérez
Constructora ABC

Almuerzo registrado
30/09/2026 - 13:07

---

🚫 Cupo diario de almuerzos

Cada empresa define cuántos almuerzos diarios autoriza por trabajador
(campo «Almuerzos diarios por trabajador», por defecto 1). En el formulario
del trabajador se puede definir una excepción individual; si se deja vacío,
se usa el cupo de la empresa.

Los cupos son independientes por empresa. Ejemplo: el RUT 12492336-0 con cupo
1 en la empresa A y 2 en la empresa B puede almorzar 3 veces al día: 1 pagado
por A y 2 pagados por B, cada uno con su propio QR.

Cada consumo guarda su número del día (1, 2, ...) y la base de datos impide
dos consumos con el mismo número para el mismo trabajador y fecha.

Si el cupo está agotado:

⚠️ CUPO DIARIO AGOTADO (2 de 2)

Juan Pérez
Constructora ABC

Registrado:
13:07

El sistema no debe crear un consumo adicional.

Esta regla debe estar protegida tanto en la lógica de la aplicación como, cuando corresponda, mediante una restricción adecuada en la base de datos.

---

📊 Dashboard

El dashboard inicial debe mostrar información sencilla.

Indicadores

- Total de almuerzos del día.
- Total por empresa.
- Últimos consumos.

Ejemplo:

ALMUERZOS HOY

247

EMPRESAS

Constructora ABC 67
Transportes XYZ 94
Empresa C 58
Empresa D 28

TOTAL 247

También debe ser posible consultar el detalle:

Juan Pérez Constructora ABC 13:07
María Soto Constructora ABC 13:09
Pedro Díaz Empresa C 13:12

---

📅 Historial

El sistema debe conservar los registros de consumo.

Se puede consultar desde el menú Historial, con filtros por:

- Consumos de un día.
- Consumos de una empresa.
- Consumos de un trabajador.
- RUT: muestra todos los consumos de la persona en todas sus empresas, con el total.

El operador solo ve los consumos del día en curso.

---

🛠️ Tecnología

Backend

Python + Django

### Protección del inicio de sesión

Las claves de operador son de exactamente 8 dígitos (las claves de 6 dígitos creadas antes siguen funcionando hasta que se cambien). Los intentos se limitan por cuenta y por IP; por defecto se usa `REMOTE_ADDR`, adecuado para una conexión directa. Si el servicio se publica detrás de un proxy confiable, configura `DJANGO_TRUSTED_PROXY_IP_HEADER` con la clave WSGI del encabezado que el proxy sobrescribe (por ejemplo, `HTTP_X_REAL_IP`) y `DJANGO_TRUSTED_PROXY_IPS` con las IP de origen de los proxies. Solo se usará el encabezado si la conexión viene de una de esas IP. El proxy debe eliminar cualquier valor entrante de ese encabezado y escribir una única IP validada; no confíes en encabezados enviados directamente por el cliente. Si la infraestructura aún no está definida, deja ambas variables vacías.

Base de datos

PostgreSQL

Frontend

Django Templates
Bootstrap
JavaScript

QR

Identificador/token único por trabajador.

Dispositivo del operador

Teléfono o dispositivo con cámara y navegador web compatible.

El MVP no requiere una aplicación móvil nativa.

---

📁 Estructura conceptual

La estructura inicial del proyecto contempla:

ComensalQR/
│
├── AGENTS.md
├── README.md
│
├── config/
│
├── empresas/
│
├── trabajadores/
│
├── consumos/
│
├── templates/
│
├── static/
│
└── ...

La estructura real puede evolucionar durante el desarrollo siempre que se mantenga la arquitectura definida para el proyecto.

---

🔐 Seguridad

El sistema debe:

- Proteger las cuentas de usuario.
- Controlar permisos según rol.
- No almacenar información personal dentro del QR.
- No exponer información administrativa al operador.
- Registrar correctamente fecha y hora de los consumos.
- Evitar registros duplicados.
- Validar los datos recibidos desde el QR.

---

🚧 Funcionalidades fuera del MVP

Estas funciones están contempladas para futuras versiones, pero no forman parte del MVP v0.1:

- Menús.
- Registro del menú consumido.
- Costos.
- IVA.
- Rentabilidad.
- Precios diferenciados por empresa.
- Facturación.
- Portal para empresas.
- Importación masiva avanzada.
- NFC.
- Biometría.
- Reconocimiento facial.
- Aplicación móvil nativa.
- Integraciones externas.
- Estadísticas avanzadas.

Su implementación requiere una decisión explícita antes de comenzar el desarrollo.

---

🗺️ Evolución prevista

El proyecto podrá crecer progresivamente:

MVP v0.1
│
├── Empresas
├── Trabajadores
├── QR
├── Consumos
└── Dashboard
│
▼
Futuras versiones
│
├── Menús
├── Autorizaciones avanzadas
├── Costos
├── IVA
├── Rentabilidad
├── Reportes
├── Facturación
└── Portal de empresas

La incorporación de nuevas funcionalidades debe hacerse progresivamente, validando primero el funcionamiento del MVP.

---

📌 Principio del proyecto

ComensalQR debe priorizar:

Simplicidad → rapidez → confiabilidad → trazabilidad → escalabilidad

La primera versión no busca solucionar todos los problemas de administración de un restaurante.

Busca solucionar uno:

«Saber quién almorzó, de qué empresa vino y cuándo lo hizo.»

Una vez validado este flujo en condiciones reales, se podrán incorporar nuevas funcionalidades.

Obtener Outlook para Android
# comensalQR
