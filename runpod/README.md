# Runpod GPU Mode

Before starting the Pod, use an official PyTorch/Jupyter template and add `7860` to **Expose HTTP Ports**. Keep the
default persistent volume mount at `/workspace`.

Open `launch_gradio_runpod.ipynb` in JupyterLab and run every cell in order. The notebook:

1. Checks the GPU and Runpod environment.
2. Clones the repository into `/workspace/video-subtitle-extractor`, or fast-forwards an existing checkout.
3. Installs FFmpeg and Python dependencies.
4. Stores HuggingFace models under `/workspace/hf-cache`.
5. Prompts for Gradio login credentials and an optional HuggingFace token without echoing passwords.
6. Starts Gradio on `0.0.0.0:7860` and prints the Runpod proxy URL.

Keep the final notebook cell running while using the service. Stop it with the notebook interrupt button.
