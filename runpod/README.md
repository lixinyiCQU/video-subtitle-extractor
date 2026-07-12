# Runpod GPU Mode

Open `launch_gradio_runpod.ipynb` in the Pod's JupyterLab and run its single code cell. It clones the repository on the
first run, fast-forwards it on later runs, installs dependencies, and starts Gradio with a public share URL. Existing
`results/` directories are preserved when the code is updated.

Keep the cell running while using the service. Stop it with the notebook interrupt button. Runtime diagnostics are
shown in the cell and appended to `/workspace/video-subtitle-extractor-runpod.log`. Rerunning the launcher preserves
earlier diagnostics because the log is outside the deleted checkout directory.
