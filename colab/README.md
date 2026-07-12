# Colab GPU Mode

Open `launch_gradio_colab.ipynb` in Google Colab, select a GPU runtime, and run all cells.

The notebook:

1. Optionally mounts Google Drive for HuggingFace model cache.
2. Clones this GitHub repository.
3. Installs and upgrades dependencies so they match Colab's preinstalled Google packages.
4. Starts the Gradio UI with a public share URL.

In the `Video URL` tab, paste one URL per line to run a batch. The result selector switches between completed videos,
and the export control downloads title-based metadata/subtitle files or a ZIP when multiple videos complete.

Cookies pasted or uploaded through the Gradio UI are only written to temporary files during the current request. They are not committed to GitHub. Avoid saving cookie files to Google Drive unless you intentionally want to keep them there.
