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
import requests
import json
import os
from bpy.props import StringProperty, IntProperty, EnumProperty

class MESHGEN_OT_generate_mesh(bpy.types.Operator):
    """Generate a mesh from a natural language prompt"""
    bl_idname = "meshgen.generate_mesh"
    bl_label = "Generate Mesh"
    bl_options = {'REGISTER', 'UNDO'}
    
    prompt: StringProperty(
        name="Prompt",
        description="Natural language description of the desired mesh",
        default=""
    )
    
    resolution: EnumProperty(
        name="Resolution",
        description="Resolution of the generated mesh",
        items=[
            ('256', "256", "Low resolution"),
            ('512', "512", "Medium resolution"),
            ('1024', "1024", "High resolution"),
        ],
        default='512'
    )
    
    format: EnumProperty(
        name="Format",
        description="Format of the mesh data",
        items=[
            ('json', "JSON", "JSON format"),
            ('obj', "OBJ", "OBJ format"),
            ('gltf', "glTF", "glTF format"),
        ],
        default='json'
    )
    
    retry_count: IntProperty(
        name="Retry Count",
        description="Number of retries if API call fails",
        default=1,
        min=0,
        max=5
    )
    
    def execute(self, context):
        preferences = context.preferences.addons[__name__].preferences
        api_endpoint = preferences.api_endpoint
        api_key = preferences.api_key
        
        # Check if API key is set
        if not api_key:
            api_key = os.environ.get("MESHGEN_API_KEY")
            if not api_key:
                self.report({'ERROR'}, "API key not set. Please set it in the add-on preferences or as MESHGEN_API_KEY environment variable.")
                return {'CANCELLED'}
        
        # Check if prompt is provided
        if not self.prompt:
            self.report({'ERROR'}, "Please enter a prompt.")
            return {'CANCELLED'}
        
        # Prepare request data
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "prompt": self.prompt,
            "resolution": int(self.resolution),
            "format": self.format
        }
        
        # Make API request with retry logic
        mesh_data = None
        error_message = "Unknown error"
        
        for attempt in range(self.retry_count + 1):
            try:
                response = requests.post(
                    api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=30
                )
                
                if response.status_code == 200:
                    mesh_data = response.json()
                    break
                else:
                    error_message = f"API returned status code {response.status_code}: {response.text}"
            except requests.exceptions.RequestException as e:
                error_message = f"Network error: {str(e)}"
            except json.JSONDecodeError:
                error_message = "Invalid JSON response from API"
                
            if attempt < self.retry_count:
                self.report({'WARNING'}, f"Attempt {attempt+1} failed. Retrying...")
            
        if not mesh_data:
            self.report({'ERROR'}, f"Failed to generate mesh: {error_message}")
            return {'CANCELLED'}
        
        try:
            # Extract mesh data
            vertices = mesh_data.get("vertices")
            faces = mesh_data.get("faces")
            normals = mesh_data.get("normals")
            uvs = mesh_data.get("uvs")
            
            if not vertices or not faces:
                self.report({'ERROR'}, "API response missing vertices or faces data")
                return {'CANCELLED'}
            
            # Create new mesh
            mesh_name = f"Generated_{self.prompt[:20]}"
            mesh = bpy.data.meshes.new(mesh_name)
            
            # Create the object and link it to the scene
            obj = bpy.data.objects.new(mesh_name, mesh)
            context.collection.objects.link(obj)
            
            # Create mesh from vertices and faces
            mesh.from_pydata(vertices, [], faces)
            
            # Set normals if provided
            if normals and len(normals) == len(vertices):
                mesh.create_normals_split()
                for i, normal in enumerate(normals):
                    for poly in mesh.polygons:
                        for loop_idx in poly.loop_indices:
                            loop = mesh.loops[loop_idx]
                            if loop.vertex_index == i:
                                loop.normal = normal
                mesh.use_auto_smooth = True
            
            # Set UVs if provided
            if uvs and len(uvs) == len(vertices):
                uv_layer = mesh.uv_layers.new(name="UVMap")
                for poly in mesh.polygons:
                    for loop_idx in range(poly.loop_start, poly.loop_start + poly.loop_total):
                        vertex_idx = mesh.loops[loop_idx].vertex_index
                        uv_layer.data[loop_idx].uv = (uvs[vertex_idx][0], uvs[vertex_idx][1])
            
            # Update mesh
            mesh.update()
            mesh.validate()
            
            # Select and focus on the new object
            bpy.ops.object.select_all(action='DESELECT')
            obj.select_set(True)
            context.view_layer.objects.active = obj
            bpy.ops.view3d.view_selected(use_all_regions=False)
            
            # Report success
            vertex_count = len(vertices)
            face_count = len(faces)
            self.report({'INFO'}, f"Created mesh with {vertex_count} vertices and {face_count} faces")
            
            return {'FINISHED'}
            
        except Exception as e:
            self.report({'ERROR'}, f"Error creating mesh: {str(e)}")
            return {'CANCELLED'}


class MESHGEN_PT_panel(bpy.types.Panel):
    """MeshGenerator UI Panel"""
    bl_label = "MeshGenerator"
    bl_idname = "MESHGEN_PT_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CursorAI Mesh"
    
    def draw(self, context):
        layout = self.layout
        scene = context.scene
        
        # Prompt input
        layout.label(text="Character Description:")
        row = layout.row()
        row.prop(scene, "meshgen_prompt", text="")
        
        # Options
        box = layout.box()
        box.label(text="Generation Options:")
        
        row = box.row()
        row.label(text="Resolution:")
        row.prop(scene, "meshgen_resolution", text="")
        
        row = box.row()
        row.label(text="Format:")
        row.prop(scene, "meshgen_format", text="")
        
        row = box.row()
        row.label(text="Retries:")
        row.prop(scene, "meshgen_retry_count", text="")
        
        # Generate button
        layout.separator()
        op = layout.operator("meshgen.generate_mesh", text="Generate Mesh")
        op.prompt = scene.meshgen_prompt
        op.resolution = scene.meshgen_resolution
        op.format = scene.meshgen_format
        op.retry_count = scene.meshgen_retry_count


class MESHGEN_preferences(bpy.types.AddonPreferences):
    """MeshGenerator add-on preferences"""
    bl_idname = __name__
    
    api_key: StringProperty(
        name="API Key",
        description="API key for authentication",
        default="",
        subtype='PASSWORD'
    )
    
    api_endpoint: StringProperty(
        name="API Endpoint",
        description="URL of the mesh generation API",
        default="https://api.example.com/v1/mesh",
    )
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="MeshGenerator Settings:")
        
        layout.prop(self, "api_key")
        layout.prop(self, "api_endpoint")
        
        layout.separator()
        layout.label(text="Note: You can also set the API key as an environment variable:")
        layout.label(text="MESHGEN_API_KEY=your_key_here")


# Scene properties
def register_properties():
    bpy.types.Scene.meshgen_prompt = StringProperty(
        name="Prompt",
        description="Natural language description of the desired mesh",
        default=""
    )
    
    bpy.types.Scene.meshgen_resolution = EnumProperty(
        name="Resolution",
        description="Resolution of the generated mesh",
        items=[
            ('256', "256", "Low resolution"),
            ('512', "512", "Medium resolution"),
            ('1024', "1024", "High resolution"),
        ],
        default='512'
    )
    
    bpy.types.Scene.meshgen_format = EnumProperty(
        name="Format",
        description="Format of the mesh data",
        items=[
            ('json', "JSON", "JSON format"),
            ('obj', "OBJ", "OBJ format"),
            ('gltf', "glTF", "glTF format"),
        ],
        default='json'
    )
    
    bpy.types.Scene.meshgen_retry_count = IntProperty(
        name="Retry Count",
        description="Number of retries if API call fails",
        default=1,
        min=0,
        max=5
    )


def unregister_properties():
    del bpy.types.Scene.meshgen_prompt
    del bpy.types.Scene.meshgen_resolution
    del bpy.types.Scene.meshgen_format
    del bpy.types.Scene.meshgen_retry_count


classes = (
    MESHGEN_OT_generate_mesh,
    MESHGEN_PT_panel,
    MESHGEN_preferences,
)


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_properties()


def unregister():
    unregister_properties()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)


if __name__ == "__main__":
    register()


"""
USAGE INSTRUCTIONS:

1. Installation:
   - Save this file as MeshGenerator.py
   - In Blender, go to Edit > Preferences > Add-ons
   - Click "Install..." and select this file
   - Enable the "MeshGenerator" add-on

2. Configuration:
   - Set your API key in the add-on preferences
   - Or set the MESHGEN_API_KEY environment variable
   - Optionally configure the API endpoint URL

3. Usage:
   - Open the 3D View sidebar (N-panel)
   - Find the "CursorAI Mesh" tab
   - Enter a natural language prompt describing the character
   - Adjust resolution and other settings as needed
   - Click "Generate Mesh"

4. Example prompts:
   - "A stylized human character with armor"
   - "A cute cartoon robot with big eyes"
   - "A detailed dragon with wings and a long tail"

5. Expected output:
   - At 256 resolution: ~2,000-10,000 vertices, ~4,000-20,000 faces
   - At 512 resolution: ~8,000-40,000 vertices, ~16,000-80,000 faces
   - At 1024 resolution: ~32,000-160,000 vertices, ~64,000-320,000 faces

Note: Actual mesh stats will vary based on the API implementation.
""" 