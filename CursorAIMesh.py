"""
CursorAI Mesh - Generate 3D meshes from text prompts and images.
"""

bl_info = {
    "name": "CursorAI Mesh",
    "author": "CursorAI",
    "version": (1, 0, 0),
    "blender": (2, 80, 0),
    "location": "View3D > Sidebar > CursorAI Mesh",
    "description": "Generate 3D meshes from text prompts and images",
    "warning": "",
    "doc_url": "",
    "category": "3D View",
}

import bpy
import os
import json
import time
import requests
import tempfile
import base64
from datetime import datetime
from bpy.props import (
    StringProperty,
    IntProperty,
    EnumProperty,
    BoolProperty,
    CollectionProperty,
    PointerProperty,
    FloatProperty
)
from bpy.types import (
    Panel,
    Operator,
    PropertyGroup,
    AddonPreferences,
    UIList
)

# Constants
MAX_PROMPT_LENGTH = 500
MAX_HISTORY_ITEMS = 5
DEFAULT_API_URL = "https://api.example.com/v1/"

# Helper functions
def get_api_key(context):
    """Get API key from preferences or environment variable"""
    preferences = context.preferences.addons[__name__].preferences
    api_key = preferences.api_key
    
    if not api_key:
        api_key = os.environ.get("CURSOR_AI_API_KEY")
        
    return api_key

def get_api_base_url(context):
    """Get API base URL from preferences"""
    preferences = context.preferences.addons[__name__].preferences
    return preferences.api_base_url

def add_log_entry(context, level, message):
    """Add an entry to the log"""
    logs = context.window_manager.cursorai_logs
    
    # Remove oldest log if we've reached the limit
    if len(logs) >= 100:
        logs.remove(0)
    
    # Add new log entry
    new_log = logs.add()
    new_log.level = level
    new_log.message = message
    new_log.timestamp = datetime.now().strftime("%H:%M:%S")
    
    # Update the index to point to the new log
    context.window_manager.cursorai_log_index = len(logs) - 1

def add_history_item(context, item_type, prompt, image_path, resolution, format):
    """Add an item to the generation history"""
    history = context.window_manager.cursorai_history
    
    # Remove oldest history item if we've reached the limit
    if len(history) >= MAX_HISTORY_ITEMS:
        history.remove(0)
    
    # Add new history item
    new_item = history.add()
    new_item.item_type = item_type
    new_item.prompt = prompt
    new_item.image_path = image_path
    new_item.resolution = resolution
    new_item.format = format
    new_item.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    # Update the index to point to the new item
    context.window_manager.cursorai_history_index = len(history) - 1

def create_mesh_from_data(context, mesh_data, name_prefix="Generated"):
    """Create a mesh object from the API response data"""
    try:
        # Extract mesh data
        vertices = mesh_data.get("vertices")
        faces = mesh_data.get("faces")
        normals = mesh_data.get("normals")
        uvs = mesh_data.get("uvs")
        
        if not vertices or not faces:
            add_log_entry(context, "ERROR", "API response missing vertices or faces data")
            return None
        
        # Create new mesh
        timestamp = datetime.now().strftime("%H%M%S")
        mesh_name = f"{name_prefix}_{timestamp}"
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
        
        # Add CursorAI custom property for identification
        obj["cursorai_generated"] = True
        
        return obj
        
    except Exception as e:
        add_log_entry(context, "ERROR", f"Error creating mesh: {str(e)}")
        return None

def focus_on_object(context, obj):
    """Select and focus the camera on an object"""
    if not obj:
        return
        
    # Select and make active
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    context.view_layer.objects.active = obj
    
    # Focus view on the object
    bpy.ops.view3d.view_selected(use_all_regions=False)

def show_message_box(message, title="Message", icon='INFO'):
    """Show a message box with the given message"""
    def draw(self, context):
        self.layout.label(text=message)
    
    bpy.context.window_manager.popup_menu(draw, title=title, icon=icon)

# Property definitions
class CursorAILogItem(PropertyGroup):
    """Log item properties"""
    timestamp: StringProperty(name="Time")
    level: StringProperty(name="Level")
    message: StringProperty(name="Message")

class CursorAIHistoryItem(PropertyGroup):
    """History item properties"""
    item_type: StringProperty(name="Type")
    prompt: StringProperty(name="Prompt")
    image_path: StringProperty(name="Image Path", subtype='FILE_PATH')
    resolution: StringProperty(name="Resolution")
    format: StringProperty(name="Format")
    timestamp: StringProperty(name="Timestamp")

# Operators
class CURSORAI_OT_generate_from_text(Operator):
    """Generate a 3D mesh from a text prompt"""
    bl_idname = "cursorai.generate_from_text"
    bl_label = "Generate from Text"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.cursorai_props
        
        # Check if API key is set
        api_key = get_api_key(context)
        if not api_key:
            add_log_entry(context, "ERROR", "API key not set. Please set it in the add-on preferences or as CURSOR_AI_API_KEY environment variable.")
            show_message_box("API key not set. Check add-on preferences.", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Check if prompt is provided
        if not props.text_prompt or len(props.text_prompt.strip()) == 0:
            add_log_entry(context, "ERROR", "Please enter a prompt.")
            show_message_box("Please enter a prompt.", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Get API base URL
        api_base_url = get_api_base_url(context)
        api_endpoint = f"{api_base_url}generate_mesh"
        
        # Prepare request data
        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "prompt": props.text_prompt,
            "resolution": int(props.resolution),
            "format": props.format
        }
        
        # Log the request
        add_log_entry(context, "INFO", f"Sending request to {api_endpoint} with resolution {props.resolution}")
        
        # Set loading state
        props.is_loading = True
        
        # Make API request with retry logic
        mesh_data = None
        error_message = "Unknown error"
        
        for attempt in range(props.retry_count + 1):
            try:
                # Update status message
                if attempt > 0:
                    props.status_message = f"Retry {attempt}/{props.retry_count}..."
                else:
                    props.status_message = "Generating mesh..."
                
                # Force UI update
                context.area.tag_redraw()
                
                # Make the request
                response = requests.post(
                    api_endpoint,
                    headers=headers,
                    json=payload,
                    timeout=60
                )
                
                if response.status_code == 200:
                    mesh_data = response.json()
                    add_log_entry(context, "INFO", "Received successful response from API")
                    break
                else:
                    error_message = f"API returned status code {response.status_code}: {response.text}"
                    add_log_entry(context, "ERROR", error_message)
            except requests.exceptions.RequestException as e:
                error_message = f"Network error: {str(e)}"
                add_log_entry(context, "ERROR", error_message)
            except json.JSONDecodeError:
                error_message = "Invalid JSON response from API"
                add_log_entry(context, "ERROR", error_message)
                
            if attempt < props.retry_count:
                # Wait before retrying
                time.sleep(2)
                add_log_entry(context, "INFO", f"Attempt {attempt+1} failed. Retrying...")
            
        # Reset loading state
        props.is_loading = False
        props.status_message = ""
        
        if not mesh_data:
            add_log_entry(context, "ERROR", f"Failed to generate mesh: {error_message}")
            show_message_box(f"Failed to generate mesh: {error_message}", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Create the mesh and add to scene
        obj = create_mesh_from_data(context, mesh_data, f"Text_{props.text_prompt[:20]}")
        
        if not obj:
            show_message_box("Failed to create mesh from API response", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Focus on the object
        focus_on_object(context, obj)
        
        # Add to history
        add_history_item(
            context,
            "TEXT",
            props.text_prompt,
            "",
            props.resolution,
            props.format
        )
        
        # Report success
        vertex_count = len(mesh_data.get("vertices", []))
        face_count = len(mesh_data.get("faces", []))
        add_log_entry(context, "INFO", f"Created mesh with {vertex_count} vertices and {face_count} faces")
        
        self.report({'INFO'}, f"Created mesh with {vertex_count} vertices and {face_count} faces")
        return {'FINISHED'}

class CURSORAI_OT_generate_from_image(Operator):
    """Generate a 3D mesh from an image"""
    bl_idname = "cursorai.generate_from_image"
    bl_label = "Generate from Image"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        props = context.scene.cursorai_props
        
        # Check if API key is set
        api_key = get_api_key(context)
        if not api_key:
            add_log_entry(context, "ERROR", "API key not set. Please set it in the add-on preferences or as CURSOR_AI_API_KEY environment variable.")
            show_message_box("API key not set. Check add-on preferences.", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Check if image path is provided
        if not props.image_path or len(props.image_path.strip()) == 0:
            add_log_entry(context, "ERROR", "Please select an image.")
            show_message_box("Please select an image.", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Check if file exists
        if not os.path.exists(bpy.path.abspath(props.image_path)):
            add_log_entry(context, "ERROR", f"Image file not found: {props.image_path}")
            show_message_box(f"Image file not found: {props.image_path}", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Get API base URL
        api_base_url = get_api_base_url(context)
        api_endpoint = f"{api_base_url}image_to_mesh"
        
        # Prepare request data
        headers = {
            "Authorization": f"Bearer {api_key}",
        }
        
        # Read the image file
        try:
            with open(bpy.path.abspath(props.image_path), 'rb') as img_file:
                image_data = img_file.read()
        except Exception as e:
            add_log_entry(context, "ERROR", f"Error reading image file: {str(e)}")
            show_message_box(f"Error reading image file: {str(e)}", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Prepare multipart form data
        files = {
            'image': (os.path.basename(props.image_path), image_data)
        }
        
        form_data = {
            'resolution': props.resolution,
            'format': props.format
        }
        
        # Add optional prompt if provided
        if props.image_prompt and len(props.image_prompt.strip()) > 0:
            form_data['prompt'] = props.image_prompt
        
        # Log the request
        add_log_entry(context, "INFO", f"Sending image to {api_endpoint} with resolution {props.resolution}")
        
        # Set loading state
        props.is_loading = True
        
        # Make API request with retry logic
        mesh_data = None
        error_message = "Unknown error"
        
        for attempt in range(props.retry_count + 1):
            try:
                # Update status message
                if attempt > 0:
                    props.status_message = f"Retry {attempt}/{props.retry_count}..."
                else:
                    props.status_message = "Generating mesh from image..."
                
                # Force UI update
                context.area.tag_redraw()
                
                # Make the request
                response = requests.post(
                    api_endpoint,
                    headers=headers,
                    files=files,
                    data=form_data,
                    timeout=120  # Longer timeout for image processing
                )
                
                if response.status_code == 200:
                    mesh_data = response.json()
                    add_log_entry(context, "INFO", "Received successful response from API")
                    break
                else:
                    error_message = f"API returned status code {response.status_code}: {response.text}"
                    add_log_entry(context, "ERROR", error_message)
            except requests.exceptions.RequestException as e:
                error_message = f"Network error: {str(e)}"
                add_log_entry(context, "ERROR", error_message)
            except json.JSONDecodeError:
                error_message = "Invalid JSON response from API"
                add_log_entry(context, "ERROR", error_message)
                
            if attempt < props.retry_count:
                # Wait before retrying
                time.sleep(2)
                add_log_entry(context, "INFO", f"Attempt {attempt+1} failed. Retrying...")
            
        # Reset loading state
        props.is_loading = False
        props.status_message = ""
        
        if not mesh_data:
            add_log_entry(context, "ERROR", f"Failed to generate mesh: {error_message}")
            show_message_box(f"Failed to generate mesh: {error_message}", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Create the mesh and add to scene
        image_name = os.path.splitext(os.path.basename(props.image_path))[0]
        obj = create_mesh_from_data(context, mesh_data, f"Image_{image_name[:20]}")
        
        if not obj:
            show_message_box("Failed to create mesh from API response", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Focus on the object
        focus_on_object(context, obj)
        
        # Add to history
        add_history_item(
            context,
            "IMAGE",
            props.image_prompt,
            props.image_path,
            props.resolution,
            props.format
        )
        
        # Report success
        vertex_count = len(mesh_data.get("vertices", []))
        face_count = len(mesh_data.get("faces", []))
        add_log_entry(context, "INFO", f"Created mesh with {vertex_count} vertices and {face_count} faces")
        
        self.report({'INFO'}, f"Created mesh with {vertex_count} vertices and {face_count} faces")
        return {'FINISHED'}

class CURSORAI_OT_clear_generated(Operator):
    """Remove all CursorAI generated objects from the scene"""
    bl_idname = "cursorai.clear_generated"
    bl_label = "Clear Generated Objects"
    bl_options = {'REGISTER', 'UNDO'}
    
    def execute(self, context):
        # Find all objects with the CursorAI custom property
        cursorai_objects = [obj for obj in bpy.data.objects if obj.get("cursorai_generated", False)]
        
        if not cursorai_objects:
            add_log_entry(context, "INFO", "No CursorAI generated objects found in the scene")
            show_message_box("No CursorAI generated objects found in the scene", "Info", 'INFO')
            return {'CANCELLED'}
        
        # Select all CursorAI objects
        bpy.ops.object.select_all(action='DESELECT')
        for obj in cursorai_objects:
            obj.select_set(True)
        
        # Delete selected objects
        bpy.ops.object.delete()
        
        # Log the action
        add_log_entry(context, "INFO", f"Removed {len(cursorai_objects)} CursorAI generated objects from the scene")
        
        self.report({'INFO'}, f"Removed {len(cursorai_objects)} objects")
        return {'FINISHED'}

class CURSORAI_OT_use_history_item(Operator):
    """Use a history item to set up a new generation"""
    bl_idname = "cursorai.use_history_item"
    bl_label = "Use History Item"
    bl_options = {'REGISTER'}
    
    index: IntProperty(default=0)
    
    def execute(self, context):
        history = context.window_manager.cursorai_history
        
        if len(history) == 0 or self.index >= len(history):
            show_message_box("Invalid history item", "Error", 'ERROR')
            return {'CANCELLED'}
        
        # Get the selected history item
        item = history[self.index]
        props = context.scene.cursorai_props
        
        # Set properties based on the history item
        props.resolution = item.resolution
        props.format = item.format
        
        if item.item_type == "TEXT":
            props.text_prompt = item.prompt
            # Switch to text tab
            context.scene.cursorai_active_tab = 0
        else:  # IMAGE
            props.image_prompt = item.prompt
            props.image_path = item.image_path
            # Switch to image tab
            context.scene.cursorai_active_tab = 1
        
        add_log_entry(context, "INFO", f"Loaded settings from history item: {item.timestamp}")
        
        return {'FINISHED'}

class CURSORAI_OT_clear_logs(Operator):
    """Clear all log entries"""
    bl_idname = "cursorai.clear_logs"
    bl_label = "Clear Logs"
    bl_options = {'REGISTER'}
    
    def execute(self, context):
        # Clear all logs
        context.window_manager.cursorai_logs.clear()
        context.window_manager.cursorai_log_index = -1
        
        return {'FINISHED'}

# UI List classes
class CURSORAI_UL_history(UIList):
    """History list UI"""
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            
            # Icon based on type
            if item.item_type == "TEXT":
                type_icon = 'FONT_DATA'
            else:  # IMAGE
                type_icon = 'IMAGE'
            
            row.label(text="", icon=type_icon)
            
            # Display different content based on type
            if item.item_type == "TEXT":
                if item.prompt:
                    # Truncate long prompts
                    prompt_display = item.prompt[:25] + "..." if len(item.prompt) > 25 else item.prompt
                    row.label(text=f"{prompt_display}")
                else:
                    row.label(text="[No prompt]")
            else:  # IMAGE
                img_name = os.path.basename(item.image_path) if item.image_path else "[No image]"
                row.label(text=f"{img_name}")
            
            # Add timestamp
            row.label(text=f"{item.timestamp}")
            
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='FILE')

class CURSORAI_UL_logs(UIList):
    """Logs list UI"""
    
    def draw_item(self, context, layout, data, item, icon, active_data, active_propname, index):
        if self.layout_type in {'DEFAULT', 'COMPACT'}:
            row = layout.row(align=True)
            
            # Icon based on log level
            if item.level == "ERROR":
                level_icon = 'ERROR'
            elif item.level == "WARNING":
                level_icon = 'WARNING'
            else:
                level_icon = 'INFO'
            
            row.label(text=f"[{item.timestamp}]", icon=level_icon)
            row.label(text=f"{item.message}")
            
        elif self.layout_type in {'GRID'}:
            layout.alignment = 'CENTER'
            layout.label(text="", icon='TEXT')

# Property group
class CursorAIProperties(PropertyGroup):
    # Text to 3D properties
    text_prompt: StringProperty(
        name="Text Prompt",
        description="Natural language description of the desired mesh",
        default="",
        maxlen=MAX_PROMPT_LENGTH
    )
    
    # Image to 3D properties
    image_path: StringProperty(
        name="Image",
        description="Path to the image",
        default="",
        subtype='FILE_PATH'
    )
    
    image_prompt: StringProperty(
        name="Image Prompt",
        description="Optional text to guide the image-to-mesh generation",
        default="",
        maxlen=MAX_PROMPT_LENGTH
    )
    
    # Shared properties
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
        default=2,
        min=0,
        max=5
    )
    
    # State tracking
    is_loading: BoolProperty(
        name="Is Loading",
        description="Whether an API request is in progress",
        default=False
    )
    
    status_message: StringProperty(
        name="Status Message",
        description="Current status message",
        default=""
    )

# Add-on preferences
class CURSORAI_preferences(AddonPreferences):
    """CursorAI Mesh add-on preferences"""
    bl_idname = __name__
    
    api_key: StringProperty(
        name="API Key",
        description="API key for authentication",
        default="",
        subtype='PASSWORD'
    )
    
    api_base_url: StringProperty(
        name="API Base URL",
        description="Base URL for the API",
        default=DEFAULT_API_URL,
    )
    
    def draw(self, context):
        layout = self.layout
        layout.label(text="CursorAI Mesh Settings:")
        
        layout.prop(self, "api_key")
        layout.prop(self, "api_base_url")
        
        layout.separator()
        layout.label(text="Note: You can also set the API key as an environment variable:")
        layout.label(text="CURSOR_AI_API_KEY=your_key_here")

# Panels
class CURSORAI_PT_main_panel(Panel):
    """CursorAI Mesh main panel"""
    bl_label = "CursorAI Mesh"
    bl_idname = "CURSORAI_PT_main_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CursorAI Mesh"
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.cursorai_props
        
        # Status/loading indicator
        if props.is_loading:
            row = layout.row()
            row.label(text=props.status_message)
            row.label(text="", icon='SORTTIME')
        
        # Tab buttons
        row = layout.row()
        row.prop(context.scene, "cursorai_active_tab", expand=True)
        
        # Draw the appropriate panel based on active tab
        if context.scene.cursorai_active_tab == 0:  # Text to 3D
            self.draw_text_panel(context, layout)
        elif context.scene.cursorai_active_tab == 1:  # Image to 3D
            self.draw_image_panel(context, layout)
        
        # Clear generated objects button
        layout.separator()
        layout.operator("cursorai.clear_generated", icon='TRASH')
        
        # History section
        if len(context.window_manager.cursorai_history) > 0:
            box = layout.box()
            box.label(text="Generation History:")
            
            row = box.row()
            row.template_list(
                "CURSORAI_UL_history", "",
                context.window_manager, "cursorai_history",
                context.window_manager, "cursorai_history_index"
            )
            
            # Use history item button
            selected_idx = context.window_manager.cursorai_history_index
            if selected_idx >= 0 and selected_idx < len(context.window_manager.cursorai_history):
                box.operator("cursorai.use_history_item", text="Use These Settings").index = selected_idx
    
    def draw_text_panel(self, context, layout):
        props = context.scene.cursorai_props
        
        # Text prompt
        layout.label(text="Character Description:")
        layout.prop(props, "text_prompt", text="")
        
        # Options
        box = layout.box()
        box.label(text="Generation Options:")
        
        row = box.row()
        row.label(text="Resolution:")
        row.prop(props, "resolution", text="")
        
        row = box.row()
        row.label(text="Format:")
        row.prop(props, "format", text="")
        
        row = box.row()
        row.label(text="Retries:")
        row.prop(props, "retry_count", text="")
        
        # Generate button
        layout.operator("cursorai.generate_from_text", icon='SHADERFX')
    
    def draw_image_panel(self, context, layout):
        props = context.scene.cursorai_props
        
        # Image path
        layout.label(text="Reference Image:")
        layout.prop(props, "image_path", text="")
        
        # Optional prompt
        layout.label(text="Additional Guidance (Optional):")
        layout.prop(props, "image_prompt", text="")
        
        # Options
        box = layout.box()
        box.label(text="Generation Options:")
        
        row = box.row()
        row.label(text="Resolution:")
        row.prop(props, "resolution", text="")
        
        row = box.row()
        row.label(text="Format:")
        row.prop(props, "format", text="")
        
        row = box.row()
        row.label(text="Retries:")
        row.prop(props, "retry_count", text="")
        
        # Generate button
        layout.operator("cursorai.generate_from_image", icon='MOD_BUILD')

class CURSORAI_PT_logs_panel(Panel):
    """CursorAI Mesh logs panel"""
    bl_label = "CursorAI Logs"
    bl_idname = "CURSORAI_PT_logs_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "CursorAI Mesh"
    bl_options = {'DEFAULT_CLOSED'}
    
    def draw(self, context):
        layout = self.layout
        
        # Log list
        row = layout.row()
        row.template_list(
            "CURSORAI_UL_logs", "",
            context.window_manager, "cursorai_logs",
            context.window_manager, "cursorai_log_index"
        )
        
        # Clear logs button
        layout.operator("cursorai.clear_logs", icon='X')

# Registration
classes = (
    CursorAILogItem,
    CursorAIHistoryItem,
    CursorAIProperties,
    CURSORAI_preferences,
    CURSORAI_OT_generate_from_text,
    CURSORAI_OT_generate_from_image,
    CURSORAI_OT_clear_generated,
    CURSORAI_OT_use_history_item,
    CURSORAI_OT_clear_logs,
    CURSORAI_UL_history,
    CURSORAI_UL_logs,
    CURSORAI_PT_main_panel,
    CURSORAI_PT_logs_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    
    # Register properties
    bpy.types.Scene.cursorai_props = PointerProperty(type=CursorAIProperties)
    bpy.types.Scene.cursorai_active_tab = bpy.props.IntProperty(
        name="Active Tab",
        default=0,
        min=0,
        max=1,
        description="Active panel tab"
    )
    
    # Register collection properties for logs and history
    bpy.types.WindowManager.cursorai_logs = CollectionProperty(type=CursorAILogItem)
    bpy.types.WindowManager.cursorai_log_index = IntProperty(name="Log Index")
    
    bpy.types.WindowManager.cursorai_history = CollectionProperty(type=CursorAIHistoryItem)
    bpy.types.WindowManager.cursorai_history_index = IntProperty(name="History Index")

def unregister():
    # Unregister properties
    del bpy.types.Scene.cursorai_props
    del bpy.types.Scene.cursorai_active_tab
    del bpy.types.WindowManager.cursorai_logs
    del bpy.types.WindowManager.cursorai_log_index
    del bpy.types.WindowManager.cursorai_history
    del bpy.types.WindowManager.cursorai_history_index
    
    # Unregister classes
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

if __name__ == "__main__":
    register()


"""
USAGE INSTRUCTIONS:

1. Installation:
   - Save this file as CursorAIMesh.py
   - In Blender, go to Edit > Preferences > Add-ons
   - Click "Install..." and select this file
   - Enable the "CursorAI Mesh" add-on

2. Configuration:
   - In the add-on preferences, enter your API key
   - Or set the CURSOR_AI_API_KEY environment variable before starting Blender
   - Optionally update the API base URL if using a custom service

3. Text to 3D Usage:
   - Open the 3D View sidebar (N-panel)
   - Find the "CursorAI Mesh" tab
   - Enter a text prompt describing the character or object
   - Adjust resolution and other settings as needed
   - Click "Generate from Text"

4. Image to 3D Usage:
   - Switch to the "Image to 3D" tab
   - Browse for a reference image (.jpg or .png)
   - Optionally add a text prompt to guide the generation
   - Adjust resolution and other settings
   - Click "Generate from Image"

5. Example Text Prompts:
   - "A stylized human character with armor and a sword"
   - "A cute cartoon robot with big eyes and antenna"
   - "A detailed dragon with scales, wings and a long tail"

6. Example Image Paths:
   - C:/Users/username/Pictures/reference.jpg
   - /home/username/images/character.png
   - Relative paths like //textures/reference.jpg (relative to .blend file)

7. Troubleshooting:
   - If mesh not generated: Check API key, network connection, and logs
   - If API fails: Check endpoint URL, request payload format, and retry
   - If mesh appears incomplete: Try increasing resolution
   - Check the "CursorAI Logs" panel for detailed error messages
   - Clear the API key and re-enter it if authentication issues persist

Note: Actual results will vary based on the API implementation.
""" 