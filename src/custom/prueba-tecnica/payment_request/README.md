---

### 1. `payment_request/README.md`

```markdown
# Solicitudes de Pago a Proveedores (`payment_request`)

Módulo desarrollado para Odoo 19 que implementa un flujo completo, seguro y auditable de solicitudes de pago a proveedores con políticas de aprobación escalonadas, control multi-moneda (USD/VES) y prevención de pagos no autorizados en contabilidad.

---

## 1. Tramos Completados

### ✅ Tramo A (Básico y Seguridad)
- **Modelo `payment.request`**: Con herencia de `mail.thread` y `mail.activity.mixin`. Secuencia anual automática (`SP/%(year)s/0001`).
- **Seguridad**: Grupos definidos (*Solicitante*, *Aprobador*, *Tesorería*, *Gerencia*).
- **Reglas de Registro**: El solicitante únicamente puede visualizar sus propias solicitudes.
- **Validaciones de Negocio**:
  - Monto estrictamente mayor a 0 (bloqueo por constraint).
  - Bloqueo de edición si la solicitud ya fue enviada o procesada.
  - El solicitante no puede aprobar su propia solicitud (ni por interfaz ni por método Python).
- **Vistas en Odoo 19**: Lista (`<list>`), Formulario con barra de estado dinámica y filtros de búsqueda/agrupación.

### ✅ Tramo B (Políticas, Wizards y Reporte)
- **Aprobación Escalonada**: Asignación automática del aprobador inicial según el monto configurado y generación de actividades en Chatter.
- **Wizard de Rechazo (`payment.request.reject.wizard`)**: Motivo obligatorio que se publica automáticamente en el historial del Chatter.
- **Wizard de Pago (`payment.request.pay.wizard`)**: Permite a Tesorería seleccionar el diario de egreso y genera el pago contable vinculado.
- **Prevención de Doble Pago**: Bloqueo a nivel de ORM y base de datos que impide liquidar una solicitud más de una vez.
- **Reporte QWeb PDF**: Documento imprimible para la carpeta física del proveedor con firmas, datos fiscales y trazabilidad de aprobación.

### ✅ Tramo C (Multi-Compañía, Concurrencia y Multi-Moneda)
- **Conversión de Divisas (USD $\rightarrow$ VES)**: Solicitudes en USD liquidadas en diarios en VES con conversión automática a la tasa vigente del día del pago.
- **Multi-Compañía Estricto**: Políticas y solicitudes aisladas mediante reglas de registro (`ir.rule`).
- **Control de Concurrencia Pesimista**: Bloqueo atómico a nivel de PostgreSQL (`SELECT ... FOR UPDATE NOWAIT`) que evita que dos aprobadores o tesoreros actúen en paralelo sobre el mismo registro.
- **Integridad Transaccional**: Si la creación del pago contable falla, la solicitud no pasa a estado "Pagada".
- **Control Anti-Fraude en Contabilidad**: Bloqueo de creación directa de pagos de proveedores en *Contabilidad > Proveedores > Pagos* para usuarios no gerentes.

---

## 2. Supuestos y Preguntas al Cliente (Caso Carolina Méndez)

### Preguntas para Carolina:
1. **Facturas Existentes vs. Desembolsos Libres:** ¿Las solicitudes de pago deben permitir seleccionar facturas de proveedor ya cargadas en Odoo para conciliarlas automáticamente, o son exclusivamente para anticipos, compras menores y pagos sin factura previa?
2. **Umbral de Pagos Grandes:** ¿Cuál es el monto exacto a partir del cual una solicitud deja de requerir únicamente al Jefe de Área y pasa a necesitar la aprobación de Gerencia General?

### Supuestos Adoptados para Avanzar:
1. **Políticas Secuenciales:** Se modeló `payment.approval.policy` con líneas secuenciales (`sequence`). Pagos grandes transitan paso a paso (ej. Paso 1: Jefe de Área $\rightarrow$ Paso 2: Gerencia).
2. **Tasa de la Fecha de Desembolso:** El wizard de pago convierte el monto utilizando el conversor nativo de Odoo (`res.currency._convert`) tomando la fecha del diario de pago.
3. **Bloqueo de Bypass en Contabilidad:** Asumimos que la fuga de control reportada por WhatsApp también ocurría si Tesorería creaba pagos manuales directamente en Contabilidad; por ello, se bloqueó la creación directa de pagos salientes a proveedores salvo que provengan de una solicitud aprobada o sean hechos por Gerencia.

---

## 3. Cómo Probar el Módulo

### Ejecución de Pruebas Automatizadas
Ejecuta los tests unitarios en una base limpia:
```bash
./odoo test -d prueba_limpia -m payment_request
```
*Cobertura: 9 pruebas unitarias que validan restricciones de monto, permisos, no edición, concurrencia, doble pago, multi-compañía y aprobación secuencial.*

### Flujo Manual Paso a Paso
1. Iniciar sesión con un usuario **Solicitante**:
   - Ir a **Solicitudes de Pago > Solicitudes > Nuevo**.
   - Ingresar proveedor, monto y concepto. Clic en **Enviar Solicitud**.
   - El estado cambia a `En Aprobación`, se asigna el primer aprobador y se bloquea la edición de campos.
2. Iniciar sesión con el usuario **Aprobador Asignado**:
   - Abrir la solicitud. Comprobar que solo el aprobador en turno puede hacer clic en **Aprobar Paso** o **Rechazar**.
   - Al aprobar, la solicitud avanza al siguiente paso o finaliza en `Aprobada`.
3. Iniciar sesión con **Tesorería**:
   - Abrir la solicitud aprobada y hacer clic en **Generar Pago a Proveedor**.
   - Elegir el diario (por ejemplo, en VES para una solicitud en USD). Verificar el cálculo de la tasa.
   - Confirmar: se genera el registro contable `account.payment` y la solicitud queda en `Pagada`.
4. Verificar el botón **Imprimir > Solicitud de Pago** para generar el comprobante PDF.
