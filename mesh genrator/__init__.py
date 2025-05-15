"""
MeshGenerator - Generate 3D meshes from natural language prompts via API calls.
"""

bl_info = {
    "name": "MeshGenerator",
    "author": "CursorAI",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > MeshGenerator",
    "description": "Generate 3D meshes from natural language prompts",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

import bpy
from . import MeshGenerator

def register():
    MeshGenerator.register()

def unregister():
    MeshGenerator.unregister()

if __name__ == "__main__":
    register() 