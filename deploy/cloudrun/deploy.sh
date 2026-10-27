#!/usr/bin/env bash
# Deploys the Unlimited-OCR web UI to Cloud Run with an NVIDIA L4 GPU, scaling to zero when idle.
# Run from Google Cloud Shell:  bash deploy/cloudrun/deploy.sh
# Override defaults with env vars, e.g.  REGION=us-central1 bash deploy/cloudrun/deploy.sh
set -euo pipefail

PROJECT_ID="${PROJECT_ID:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-europe-west1}"
SERVICE="${SERVICE:-unlimited-ocr}"
AR_REPO="${AR_REPO:-ocr}"
SECRET="${SECRET:-unlimited-ocr-password}"
OCR_USER="${OCR_USER:-ocr}"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${AR_REPO}/${SERVICE}:latest"

confirm() {
  read -r -p "$1 [e/h] " ans
  [[ "$ans" =~ ^[eEyY]$ ]] || { echo "İptal edildi."; exit 1; }
}

if [[ -z "$PROJECT_ID" ]]; then
  echo "Proje seçili değil. Önce: gcloud config set project PROJE_ID"
  exit 1
fi
PROJECT_NUMBER="$(gcloud projects describe "$PROJECT_ID" --format='value(projectNumber)')"
RUNTIME_SA="${PROJECT_NUMBER}-compute@developer.gserviceaccount.com"

cat <<EOF

Proje   : $PROJECT_ID
Bölge   : $REGION
Servis  : $SERVICE  (L4 GPU, 4 CPU, 16 GiB, min 0 / max 1 instance)
İmaj    : $IMAGE

Yapılacaklar: API'leri açmak, Artifact Registry deposu, şifre secret'ı,
Cloud Build ile imaj (~20-40 dk), Cloud Run deploy.
Ücret: sadece instance açıkken (L4 + CPU/RAM, kabaca ~1 USD/saat),
imaj depolama ayda ~1-2 USD.
EOF
confirm "Devam edilsin mi?"

echo "==> API'ler açılıyor"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com \
  cloudbuild.googleapis.com secretmanager.googleapis.com --project "$PROJECT_ID"

echo "==> Artifact Registry deposu"
gcloud artifacts repositories describe "$AR_REPO" --location "$REGION" --project "$PROJECT_ID" >/dev/null 2>&1 \
  || gcloud artifacts repositories create "$AR_REPO" --repository-format docker \
       --location "$REGION" --project "$PROJECT_ID"

echo "==> Şifre secret'ı"
if ! gcloud secrets describe "$SECRET" --project "$PROJECT_ID" >/dev/null 2>&1; then
  openssl rand -base64 18 | tr -d '\n' \
    | gcloud secrets create "$SECRET" --data-file=- --replication-policy automatic --project "$PROJECT_ID"
fi
gcloud secrets add-iam-policy-binding "$SECRET" --project "$PROJECT_ID" \
  --member "serviceAccount:${RUNTIME_SA}" --role roles/secretmanager.secretAccessor >/dev/null

echo "==> Cloud Build izinleri (varsayılan compute servis hesabı)"
for role in roles/artifactregistry.writer roles/logging.logWriter roles/storage.objectViewer; do
  gcloud projects add-iam-policy-binding "$PROJECT_ID" --member "serviceAccount:${RUNTIME_SA}" \
    --role "$role" --condition None >/dev/null
done

echo "==> İmaj oluşturuluyor (Cloud Build, 20-40 dk sürebilir)"
gcloud builds submit "$SRC_DIR" --tag "$IMAGE" --project "$PROJECT_ID" \
  --machine-type e2-highcpu-8 --disk-size 200 --timeout 3600s

echo "==> Cloud Run deploy"
if ! gcloud run deploy "$SERVICE" --image "$IMAGE" --region "$REGION" --project "$PROJECT_ID" \
    --gpu 1 --gpu-type nvidia-l4 --no-gpu-zonal-redundancy \
    --cpu 4 --memory 16Gi --no-cpu-throttling \
    --min-instances 0 --max-instances 1 --concurrency 4 --timeout 3600 \
    --set-env-vars "OCR_USER=${OCR_USER}" --set-secrets "OCR_PASSWORD=${SECRET}:latest" \
    --allow-unauthenticated; then
  cat <<EOF

Deploy başarısız. En sık sebep GPU kotası. Kota istemek için:
  https://console.cloud.google.com/iam-admin/quotas?project=${PROJECT_ID}
  arama: "Total Nvidia L4 GPU allocation without zonal redundancy" (Cloud Run Admin API, bölge ${REGION})
Kota gelince bu script'i tekrar çalıştırın (imaj tekrar oluşturulur; atlamak için
yukarıdaki 'gcloud run deploy' komutunu tek başına çalıştırabilirsiniz).
EOF
  exit 1
fi

URL="$(gcloud run services describe "$SERVICE" --region "$REGION" --project "$PROJECT_ID" --format 'value(status.url)')"
cat <<EOF

Hazır: $URL
Kullanıcı adı : $OCR_USER
Şifre         : gcloud secrets versions access latest --secret $SECRET --project $PROJECT_ID

İlk istekte instance açılır ve model 1-2 dk içinde yüklenir. Son istekten bir süre sonra
instance kapanır ve ücret durur (min-instances=0).

Org politikası herkese açık erişimi engellediyse URL 403 verir. O durumda Cloud Shell'den:
  gcloud run services proxy $SERVICE --region $REGION --project $PROJECT_ID --port 8080
çalıştırıp Cloud Shell "Web Preview > Preview on port 8080" ile açın.

Her şeyi silmek için:
  gcloud run services delete $SERVICE --region $REGION --project $PROJECT_ID --quiet
  gcloud artifacts repositories delete $AR_REPO --location $REGION --project $PROJECT_ID --quiet
  gcloud secrets delete $SECRET --project $PROJECT_ID --quiet
EOF
