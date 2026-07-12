# Runpod GPU Mode

Open `launch_gradio_runpod.ipynb` in the Pod's JupyterLab and run its single code cell. It removes any old checkout,
clones the latest repository, installs dependencies, and starts Gradio with a public share URL.

Keep the cell running while using the service. Stop it with the notebook interrupt button. Runtime diagnostics are
shown in the cell and appended to `/workspace/video-subtitle-extractor-runpod.log`. Rerunning the launcher preserves
earlier diagnostics because the log is outside the deleted checkout directory.
