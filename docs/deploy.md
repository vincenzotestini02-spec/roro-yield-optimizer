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
