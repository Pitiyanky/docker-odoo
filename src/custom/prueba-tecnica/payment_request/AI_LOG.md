## Herramientas
- AI Studio - Gemini 3.8 Flash

---

## Prompts clave (3 a 5)

1. **Estructura base y modelos de aprobación**
   - *Prompt:* "Generar módulo payment_request en Odoo 19 con vistas modernas (<list>, sin attrs), manejo de grupos Solicitante/Aprobador/Tesorería, secuencia anual SP/%(year)s/0001 y wizards de rechazo y pago."
   - *Qué devolvió y qué se hizo:* Generó el esqueleto del módulo y los modelos base. Se adaptó la lógica para cumplir estrictamente con los requerimientos de la prueba técnica de Binaural.

2. **Aprobación Secuencial Multi-Paso**
   - *Prompt:* "Adaptar el flujo de aprobación para soportar pasos secuenciales como en purchase.approval.terms, donde un pago grande requiera pasar por el Paso 1 (Jefe) y luego Paso 2 (Gerente), guardando historial de validaciones."
   - *Qué devolvió y qué se hizo:* Creó los modelos `payment.approval.policy`, `payment.approval.policy.line` y `payment.historical.validation`. Se integró el avance secuencial paso a paso y la reasignación de actividades en el chatter.

4. **Concurrencia con Bloqueo de Base de Datos**
   - *Prompt:* "Implementar SELECT ... FOR UPDATE NOWAIT en action_approve y en el wizard de pago para cumplir con el Tramo C de concurrencia en base de datos."
   - *Qué devolvió y qué se hizo:* Escribió la consulta SQL con cursor. Al probarla inicialmente falló en tests unitarios, lo que requirió añadir `self.flush_recordset()` antes de la consulta.

---

## Lo que la IA hizo mal

1. **Uso de campos obsoletos en `res.groups` en Odoo 19:**
   - *Error:* La IA incluyó `<field name="category_id" .../>` y `<field name="users" .../>` en `security_groups.xml`.
   - *Detección:* Odoo 19 arrojó `ValueError: Invalid field 'category_id' in 'res.groups'` y `Invalid field 'users' in 'res.groups'`. En Odoo 19 `category_id` fue eliminado y `users` fue renombrado a `user_ids`. Se corrigió eliminando ambos campos para seguir la práctica limpia de Odoo.

2. **Nombre del campo Many2many de grupos en `res.users`:**
   - *Error:* En el test unitario inicial, la IA escribió `'groups_id'` al crear los usuarios de prueba.
   - *Detección:* Falló con `ValueError: Invalid field 'groups_id' in 'res.users'`. En Odoo 19 el campo pasó a ser `group_ids`. Se implementó una detección dinámica en el test para máxima compatibilidad.

3. **Olvidar `self.flush_recordset()` antes del `SELECT FOR UPDATE`:**
   - *Error:* Al invocar `req.action_submit()`, el cambio a `to_approve` quedó en la caché del ORM en memoria y no en PostgreSQL. Cuando el método ejecutó la consulta SQL directa `SELECT id, state ... FOR UPDATE`, Postgres devolvió `draft` y la prueba `test_06` falló con un falso error de concurrencia.
   - *Detección:* Revisión del traceback en los tests de Docker (`UserError: La solicitud ya fue aprobada o procesada concurrentemente`). Se resolvió forzando `self.flush_recordset()` antes de ejecutar la consulta SQL.

4. **Campo incorrecto en `account.payment`:**
   - *Error:* La IA utilizó `'ref': f"{request.name} - {request.concept}"` al crear el pago.
   - *Detección:* Traceback en runtime: `ValueError: Invalid field 'ref' in 'account.payment'`. En Odoo el campo de glosa o concepto en pagos es `memo`.

5. **Etiquetas HTML en `message_post`:**
   - *Error:* La IA colocó etiquetas `<b>` dentro del string de `body` en `message_post`.
   - *Detección:* Odoo 19 auto-escapa HTML no marcado con `Markup`, mostrando las etiquetas literales `<b>` en la interfaz. Se reemplazó por texto limpio.

---

## Lo que escribiste tú sin IA

- **Análisis del caso de negocio de Carolina Méndez:** Formulación de las preguntas críticas sobre retenciones fiscales, conciliación contra facturas y definición de los umbrales de aprobación.
- **Regla de integridad:** Asegurar que bajo ninguna circunstancia el usuario solicitante pueda aprobar su propia solicitud, independientemente de los grupos que posea.
- **Depuración y análisis de trazas:** Diagnóstico de los fallos de caché del ORM de Odoo frente a consultas SQL crudas en los tests de integración.
