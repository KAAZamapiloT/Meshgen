# MeshGenerator

A Blender add-on that generates 3D meshes from natural language prompts using an API.

## Features

- Generate 3D meshes by describing them in natural language
- Configurable mesh resolution (256, 512, 1024)
- Support for different response formats (JSON, OBJ, glTF)
- Integrated in Blender's 3D View N-panel under "CursorAI Mesh" tab
- Robust error handling and retry mechanisms

## Installation

1. Download this repository as a ZIP file
2. In Blender, go to Edit > Preferences > Add-ons
3. Click "Install..." and select the downloaded ZIP file
4. Enable the "MeshGenerator" add-on

## Configuration

Before using the add-on, you need to set up your API key:

1. In Blender's Add-on Preferences, find and expand the MeshGenerator add-on
2. Enter your API key in the "API Key" field
3. Optionally update the API endpoint URL if you're using a custom service

Alternatively, you can set the API key as an environment variable:
```
MESHGEN_API_KEY=your_key_here
```

## Usage

1. Open the 3D View sidebar (N-panel)
2. Find the "CursorAI Mesh" tab
3. Enter a natural language prompt describing the character or object
4. Adjust resolution and other settings as needed
5. Click "Generate Mesh"

## Example Prompts

- "A stylized human character with armor"
- "A cute cartoon robot with big eyes"
- "A detailed dragon with wings and a long tail"

## Expected Output

- At 256 resolution: ~2,000-10,000 vertices, ~4,000-20,000 faces
- At 512 resolution: ~8,000-40,000 vertices, ~16,000-80,000 faces
- At 1024 resolution: ~32,000-160,000 vertices, ~64,000-320,000 faces

**Note:** Actual mesh statistics will vary based on the API implementation. 