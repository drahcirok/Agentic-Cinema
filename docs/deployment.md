# Despliegue de FrameFlow

## Arquitectura de producción

- **Frontend:** Vercel (Next.js).
- **Backend:** Google Cloud Run (FastAPI).
- **IA:** Vertex AI / Gemini con Application Default Credentials (ADC).
- **Tickets:** Firestore Native Mode, colección `postproduction_tickets`.
- **Videos temporales:** Cloud Storage; se eliminan después del análisis.

SQLite se usa únicamente en desarrollo local. Cloud Run no debe usarlo como
persistencia porque el filesystem de sus instancias es efímero.

## 1. Permisos para el service account de Cloud Run

Asigna al service account que ejecutará Cloud Run estos roles mínimos:

- `roles/aiplatform.user` para Gemini en Vertex AI.
- `roles/datastore.user` para crear, leer y actualizar tickets en Firestore.
- `roles/storage.objectAdmin` **solo en el bucket de videos** para subir y
  eliminar los archivos temporales.

No se almacenan claves JSON en el repositorio ni en variables de entorno:
Cloud Run usa su service account automáticamente mediante ADC.

## 2. Desplegar el backend

Desde la raíz del repositorio, sustituye los valores entre `<>`:

```powershell
gcloud run deploy frameflow-backend `
  --source backend `
  --project <GOOGLE_CLOUD_PROJECT> `
  --region us-central1 `
  --allow-unauthenticated `
  --set-env-vars "GEMINI_BACKEND=vertex_ai,GEMINI_MODEL=gemini-2.5-flash,GOOGLE_CLOUD_PROJECT=<GOOGLE_CLOUD_PROJECT>,GOOGLE_CLOUD_LOCATION=global,GOOGLE_CLOUD_STORAGE_BUCKET=<BUCKET_NAME>,TICKET_STORAGE_BACKEND=firestore,FIRESTORE_COLLECTION=postproduction_tickets,CORS_ALLOWED_ORIGINS=http://localhost:3000"
```

El comando crea la imagen usando [`backend/Dockerfile`](../backend/Dockerfile)
y devuelve la URL pública del servicio. Guarda esa URL; se utilizará en Vercel.

## 3. Desplegar el frontend en Vercel

1. Importa el repositorio en Vercel.
2. Configura **Root Directory** como `frontend`.
3. Añade la variable de entorno de producción:

   ```text
   NEXT_PUBLIC_API_BASE_URL=https://<CLOUD_RUN_URL>/api/v1
   ```

4. Despliega y copia la URL final de Vercel, por ejemplo
   `https://frameflow.vercel.app`.

## 4. Autorizar Vercel con CORS

Actualiza el backend usando la URL real de Vercel. Si deseas conservar las
pruebas locales, separa ambos orígenes con coma:

```powershell
gcloud run services update frameflow-backend `
  --project <GOOGLE_CLOUD_PROJECT> `
  --region us-central1 `
  --update-env-vars "CORS_ALLOWED_ORIGINS=http://localhost:3000,https://<VERCEL_URL>"
```

## 5. Verificación final

```powershell
Invoke-WebRequest https://<CLOUD_RUN_URL>/health |
  Select-Object -ExpandProperty Content
```

La respuesta esperada es:

```json
{"status":"ok","service":"frameflow-backend"}
```

Luego abre Vercel, crea una nota con postproducción requerida y comprueba que
el ticket sigue visible tras recargar la página. Eso confirma la persistencia
en Firestore.
