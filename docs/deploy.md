# Deploying the app (owner steps)

You only do this once, at the end. It takes about 10 minutes.

## 1. Put the code on GitHub

1. Go to <https://github.com/new>.
2. Repository name: `roro-yield-optimizer`. Visibility: **Public**. Do **not** tick "Add a README".
3. Click **Create repository**.
4. In a terminal inside the project folder run (replace `YOUR-USERNAME`):

   ```bash
   git remote add origin https://github.com/YOUR-USERNAME/roro-yield-optimizer.git
   git push -u origin main
   ```

   A browser window may ask you to log in to GitHub: accept.

## 2. Publish the app on Streamlit Community Cloud

1. Go to <https://share.streamlit.io> and click **Sign in with GitHub**.
2. Click **Create app** → **Deploy a public app from GitHub**.
3. Repository: `YOUR-USERNAME/roro-yield-optimizer` · Branch: `main` · Main file path: `streamlit_app.py`.
4. **Advanced settings** → Python version **3.11**.
5. Optional: choose a nice URL, e.g. `roro-yield-optimizer.streamlit.app`.
6. Click **Deploy**. First build takes 2–5 minutes.
7. Copy the URL and send it back so it can go at the top of the README.

## Updating later

Every `git push` to `main` updates the live app automatically.

## Second app for v2

v2 lives on the `v2` branch and runs as its own app, next to the v1 app.

1. Go to <https://share.streamlit.io> and click **Create app** → **Deploy a public app from GitHub**.
2. Repository: the same repo (`YOUR-USERNAME/roro-yield-optimizer`) · Branch: **`v2`** · Main file path: `streamlit_app.py`.
3. **Advanced settings** → Python version **3.11**.
4. Suggested URL: `roro-yield-optimizer-v2.streamlit.app`.
5. Click **Deploy**.

After the first load, send the URL back so the advisor verdict and the Reveal wait can be timed on the live host. The target is about 1.5 s per advisor verdict; if it is slower, the options are a lower `RORO_ADVISOR_K` or a paid host, to be decided before any spend.

## v3 on Hugging Face Spaces

v3 runs as its own Docker Space. Nothing here touches the Streamlit apps.

1. Create an account on <https://huggingface.co>.
2. Open **New Space**, pick the **Docker** SDK with a blank template and the free **CPU basic** hardware.
3. Create a token with write access under **Settings → Access Tokens**. Keep it private.
4. From the repository root, in Git Bash, run `scripts/deploy_hf.sh https://huggingface.co/spaces/YOUR-USERNAME/YOUR-SPACE`. Use your username and the token when Git asks for a password.
5. Follow the build in the Space's **Logs** tab. When it ends, `/api/health` answers `{"status":"ok"}`.
6. Time the live app: `.venv/Scripts/python.exe -m benchmarks.measure_live https://YOUR-USERNAME-YOUR-SPACE.hf.space --verdicts 10`.

## v3 on Google Cloud Run (no local tools needed)

Hugging Face now requires a paid plan for Docker Spaces, so v3 runs on Cloud Run. Cloud Run builds the image from GitHub with the repository's `Dockerfile`. The trigger publishes every push to the `v3` branch (the owner's choice). Work happens on a stage branch such as `v3-stage-1`, which reaches `v3` only when the owner approves. The `v3-live` branch is no longer used.

1. Open <https://console.cloud.google.com>, create a project named `roro-yield-optimizer` and link a billing account. A card is needed even within the free tier.
2. **Billing → Budgets & alerts → Create budget**: amount €1, alerts at 50% and 100%, email to you.
3. **Cloud Run → Deploy container → Service**, then **Continuously deploy from a repository (source or function)** → **Set up with Cloud Build**. Connect GitHub, pick `roro-yield-optimizer`, branch `^v3$`, build type **Dockerfile**, source location `/Dockerfile`.
4. Settings:
   - Service name `roro-yield-optimizer`, region `europe-west1 (Belgium)`.
   - Authentication: **Allow public access**.
   - Billing: **Instance-based**. Calculations run between requests, so the CPU must stay on while an instance is up.
   - Service scaling: minimum instances **0**, maximum instances **1**. Jobs live in the memory of one instance, so it must stay a single instance.
   - Container port **7860**, memory **2 GiB**, CPU **1**, request timeout **300** s, **Startup CPU boost** on.
5. Click **Create**. The first build takes a few minutes. When it ends, open the service URL and check `/api/health`.
6. Time the live app: `.venv/Scripts/python.exe -m benchmarks.measure_live https://YOUR-SERVICE-URL --verdicts 10`.

To publish a finished stage: `git push origin v3-stage-N:v3`, only with the owner's approval.
