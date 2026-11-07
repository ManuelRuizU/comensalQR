
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
- Ver el nombre del trabajador.
- Ver la empresa.
- Saber si puede registrar el almuerzo.
- Registrar el consumo.

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

🚫 Prevención de doble registro

Un trabajador solamente puede tener un consumo registrado por día en el MVP.

Si intenta registrarse nuevamente:

⚠️ ALMUERZO YA REGISTRADO

Juan Pérez
Constructora ABC

Registrado:
13:07

El sistema no debe crear un segundo consumo.

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

---

🛠️ Tecnología

Backend

Python + Django

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
