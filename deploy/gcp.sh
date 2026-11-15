#!/usr/bin/env bash
# Google Cloud setup for earthpull. Run each step by name:
#   deploy/gcp.sh setup        # once: APIs, bucket, Earthdata secrets, image
#   deploy/gcp.sh ui           # deploy the Streamlit UI to Cloud Run (public URL)
#   deploy/gcp.sh trendmaps    # run the global trend-map job (one task per variable)
#   deploy/gcp.sh results      # copy finished maps to ./data/trendmaps
#
# Needs: gcloud installed, `gcloud auth login`, a project with billing (the $300 credit).
set -euo pipefail

PROJECT="${PROJECT:-$(gcloud config get-value project 2>/dev/null)}"
REGION="${REGION:-us-east1}"
BUCKET="${BUCKET:-${PROJECT}-earthpull}"
IMAGE="${REGION}-docker.pkg.dev/${PROJECT}/earthpull/earthpull:latest"
SA="earthpull@${PROJECT}.iam.gserviceaccount.com"
VARS="air_temp,aerosol,precip,soil_moisture,evaporation,surface_air_temp_airs,water_storage,ndvi,land_surface_temp"
NTASKS=9
cd "$(dirname "$0")/.."

[ -n "$PROJECT" ] || { echo "Set a project: gcloud config set project <id>"; exit 1; }

case "${1:-}" in
setup)
  gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com \
    secretmanager.googleapis.com storage.googleapis.com
  gcloud storage buckets describe "gs://${BUCKET}" >/dev/null 2>&1 || \
    gcloud storage buckets create "gs://${BUCKET}" --location="$REGION" --uniform-bucket-level-access
  gcloud iam service-accounts describe "$SA" >/dev/null 2>&1 || \
    gcloud iam service-accounts create earthpull --display-name="earthpull runtime"
  gcloud storage buckets add-iam-policy-binding "gs://${BUCKET}" --member="serviceAccount:${SA}" \
    --role=roles/storage.objectAdmin >/dev/null
  for s in EARTHDATA_USERNAME EARTHDATA_PASSWORD; do
    if ! gcloud secrets describe "$s" >/dev/null 2>&1; then
      read -r -s -p "$s: " val; echo
      printf '%s' "$val" | gcloud secrets create "$s" --data-file=- >/dev/null
    fi
    gcloud secrets add-iam-policy-binding "$s" --member="serviceAccount:${SA}" \
      --role=roles/secretmanager.secretAccessor >/dev/null
  done
  gcloud artifacts repositories describe earthpull --location="$REGION" >/dev/null 2>&1 || \
    gcloud artifacts repositories create earthpull --repository-format=docker --location="$REGION"
  gcloud builds submit --tag "$IMAGE" .
  echo "setup done: bucket gs://${BUCKET}, image ${IMAGE}"
  ;;
ui)
  gcloud builds submit --tag "$IMAGE" .
  gcloud run deploy earthpull-ui --image "$IMAGE" --region "$REGION" --service-account "$SA" \
    --allow-unauthenticated --cpu 2 --memory 4Gi --timeout 3600 --max-instances 2 --concurrency 10 \
    --set-secrets EARTHDATA_USERNAME=EARTHDATA_USERNAME:latest,EARTHDATA_PASSWORD=EARTHDATA_PASSWORD:latest \
    --add-volume name=data,type=cloud-storage,bucket="$BUCKET" --add-volume-mount volume=data,mount-path=/data
  ;;
trendmaps)
  gcloud builds submit --tag "$IMAGE" .
  args="-m,earthpull.trendmap,--var,${VARS},--res,${RES:-0.5},--start,${START:-2003-01-01},--end,${END:-2024-12-31}"
  if gcloud run jobs describe earthpull-trendmaps --region "$REGION" >/dev/null 2>&1; then verb=update; else verb=create; fi
  gcloud run jobs "$verb" earthpull-trendmaps --image "$IMAGE" --region "$REGION" --service-account "$SA" \
    --command python --args "$args" --tasks "$NTASKS" --parallelism "$NTASKS" --max-retries 1 \
    --cpu 8 --memory 32Gi --task-timeout 6h \
    --set-secrets EARTHDATA_USERNAME=EARTHDATA_USERNAME:latest,EARTHDATA_PASSWORD=EARTHDATA_PASSWORD:latest \
    --add-volume name=data,type=cloud-storage,bucket="$BUCKET" --add-volume-mount volume=data,mount-path=/data
  gcloud run jobs execute earthpull-trendmaps --region "$REGION"
  echo "follow logs: gcloud run jobs executions list --job earthpull-trendmaps --region $REGION"
  ;;
results)
  mkdir -p data/trendmaps
  gcloud storage cp "gs://${BUCKET}/trendmaps/*" data/trendmaps/
  ;;
*)
  sed -n '2,8p' "$0"; exit 1 ;;
esac
