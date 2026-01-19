bl_info = {
    "name": "Compositing by Galih 2025",
    "author": "Your Name",
    "version": (1, 38),
    "blender": (4, 5, 0),
    "location": "Compositor > Sidebar > Galih@2025",
    "description": "Proper node connections with Set Alpha -> Denoise -> Output for specific passes",
    "category": "Compositing",
}

import bpy
import os

# Default passes (reordered to match View Layer Passes order)
DEFAULT_PASSES = [
    # Diffuse Passes
    "DiffDir",
    "DiffInd",
    "DiffCol",
    # Glossy Passes
    "GlossDir",
    "GlossInd",
    "GlossCol",
    # Transmission Passes
    "TransDir",
    "TransInd",
    "TransCol",
    # Volume Passes
    "VolumeDir",
    "VolumeInd",
    # Emission Pass
    "Emit",
    # Environment Pass
    "Env",
    # Ambient Occlusion Pass
    "AO",
]

# Generate cryptomatte passes dynamically up to 16 levels
def generate_cryptomatte_passes(max_levels=16):
    """Generate cryptomatte pass names dynamically."""
    crypto_passes = []
    # Object cryptomatte passes
    for i in range(max_levels):
        crypto_passes.append(f"CryptoObject{i:02d}")
    # Material cryptomatte passes  
    for i in range(max_levels):
        crypto_passes.append(f"CryptoMaterial{i:02d}")
    # Asset cryptomatte passes
    for i in range(max_levels):
        crypto_passes.append(f"CryptoAsset{i:02d}")
    return crypto_passes

# Generate cryptomatte passes (up to 16 levels)
CRYPTOMATTE_PASSES = generate_cryptomatte_passes(16)

# Passes that connect directly to File Output (in exact order)
DIRECT_PASSES = ["Shadow Catcher"] + CRYPTOMATTE_PASSES

# EXR passes that should use DWAA codec (non-cryptomatte EXR passes)
EXR_DWAA_PASSES = [
    "Depth",
    "Position", 
    "Normal",
    "Vector",
    "UV",
    "Mist",
]

# Cryptomatte passes that should use PIZ codec
EXR_PIZ_PASSES = CRYPTOMATTE_PASSES

PASS_MAP = {
    "DiffDir": "use_pass_diffuse_direct",
    "DiffInd": "use_pass_diffuse_indirect",
    "DiffCol": "use_pass_diffuse_color",
    "GlossDir": "use_pass_glossy_direct",
    "GlossInd": "use_pass_glossy_indirect",
    "GlossCol": "use_pass_glossy_color",
    "TransDir": "use_pass_transmission_direct",
    "TransInd": "use_pass_transmission_indirect",
    "TransCol": "use_pass_transmission_color",
    "VolumeDir": "use_pass_volume_direct",
    "VolumeInd": "use_pass_volume_indirect",
    "Emit": "use_pass_emission",
    "Env": "use_pass_environment",
    "AO": "use_pass_ao",
}

# Map your short pass names to actual Render Layer socket names in Blender
SOCKET_NAME_MAP = {
    # Diffuse
    "DiffDir": "Diffuse Direct",
    "DiffInd": "Diffuse Indirect",
    "DiffCol": "Diffuse Color",
    # Glossy
    "GlossDir": "Glossy Direct",
    "GlossInd": "Glossy Indirect",
    "GlossCol": "Glossy Color",
    # Transmission
    "TransDir": "Transmission Direct",
    "TransInd": "Transmission Indirect",
    "TransCol": "Transmission Color",
    # Volume
    "VolumeDir": "Volume Direct",
    "VolumeInd": "Volume Indirect",
    # Others
    "Emit": "Emit",               # keep simple
    "Env": "Environment",
    "AO": "AO",
    # EXR / common names (these are usually identical, but map explicitly)
    "Depth": "Depth",
    "Position": "Position",
    "Normal": "Normal",
    "Vector": "Vector",
    "UV": "UV",
    "Mist": "Mist",
    # Shadow variations (try both)
    "Shadow Catcher": "Shadow Catcher",
    "Shadow": "Shadow",
}

# Add cryptomatte passes to SOCKET_NAME_MAP dynamically
for pass_name in CRYPTOMATTE_PASSES:
    SOCKET_NAME_MAP[pass_name] = pass_name

def get_output_socket(node, pass_name):
    """
    Robust lookup for a render-layer output socket:
    - try mapped socket name
    - fallback to pass_name itself
    """
    if not node:
        return None
    mapped = SOCKET_NAME_MAP.get(pass_name, pass_name)
    sock = node.outputs.get(mapped)
    if sock:
        return sock
    # Fallback: try the raw pass_name (some sockets use slightly different labels)
    sock = node.outputs.get(pass_name)
    if sock:
        return sock
    # Fallback: try replacing underscores with spaces
    alt = pass_name.replace("_", " ")
    return node.outputs.get(alt)

class CompositingSettings(bpy.types.PropertyGroup):
    set_alpha_passes: bpy.props.BoolVectorProperty(
        name="Set Alpha Passes",
        description="Select passes that require Set Alpha",
        default=[False] * len(DEFAULT_PASSES),
        size=len(DEFAULT_PASSES),
    )
    denoise_passes: bpy.props.BoolVectorProperty(
        name="Denoise Passes",
        description="Select passes that require Denoise",
        # Updated default: DiffCol (index 2) and GlossCol (index 5) are now False
        default=[True, True, False, True, True, False, True, True, True, True, True, False, False, True],
        size=len(DEFAULT_PASSES),
    )
    use_denoise_albedo: bpy.props.BoolVectorProperty(
        name="Use Denoise Albedo",
        description="Use Denoising Albedo for the selected passes",
        default=[False] * len(DEFAULT_PASSES),
        size=len(DEFAULT_PASSES),
    )
    use_denoise_normal: bpy.props.BoolVectorProperty(
        name="Use Denoise Normal",
        description="Use Denoising Normal for the selected passes",
        default=[False] * len(DEFAULT_PASSES),
        size=len(DEFAULT_PASSES),
    )
    denoise_mode: bpy.props.EnumProperty(
        name="Denoise Mode",
        description="Choose the denoising mode",
        items=[
            ('FAST', 'Fast', 'Use fast denoising'),
            ('ACCURATE', 'Accurate', 'Use accurate denoising'),
        ],
        default='FAST',
    )
    base_path: bpy.props.StringProperty(
        name="Base Path",
        description="Base directory for output files",
        default="//",
        subtype='DIR_PATH',
    )
    use_prefix: bpy.props.BoolProperty(
        name="Use Prefix",
        default=False,
    )
    prefix_text: bpy.props.StringProperty(
        name="Prefix Text",
        default="",
    )
    use_suffix: bpy.props.BoolProperty(
        name="Use Suffix",
        default=False,
    )
    suffix_text: bpy.props.StringProperty(
        name="Suffix Text",
        default="",
    )
    selected_view_layer: bpy.props.EnumProperty(
        name="View Layer",
        description="Select the view layer to use",
        items=lambda self, context: [(vl.name, vl.name, "") for vl in context.scene.view_layers],
    )
    keep_existing_path: bpy.props.BoolProperty(
        name="Keep Existing Nodes",
        description="Whether to keep existing compositing nodes or delete them",
        default=False,
    )

# -------------------------------------------------------
# NEW OPERATOR: Restore Default Settings
# -------------------------------------------------------

class RestoreDefaultSettings(bpy.types.Operator):
    bl_idname = "nodes.restore_default_settings"
    bl_label = "Default"
    bl_description = "Restore default checkbox settings"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.compositing_settings
        
        # Restore default values
        settings.set_alpha_passes = [False] * len(DEFAULT_PASSES)
        settings.denoise_passes = [True, True, False, True, True, False, True, True, True, True, True, False, False, True]
        settings.use_denoise_albedo = [False] * len(DEFAULT_PASSES)
        settings.use_denoise_normal = [False] * len(DEFAULT_PASSES)
        
        return {'FINISHED'}

# -------------------------------------------------------
# UPDATED PREFETCH OPERATOR - Creates Render Layers nodes for each view layer
# -------------------------------------------------------

class PrefetchPasses(bpy.types.Operator):
    bl_idname = "nodes.prefetch_passes"
    bl_label = "Prefetch Passes"
    bl_description = "Create Render Layers nodes for all available view layers"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        scene = context.scene
        
        # Ensure we're in compositing mode with nodes enabled
        scene.use_nodes = True
        node_tree = scene.node_tree
        
        # Get all available view layers
        view_layers = context.scene.view_layers
        
        if not view_layers:
            self.report({'WARNING'}, "No view layers found in scene")
            return {'CANCELLED'}
        
        # Remove existing render layer nodes to avoid duplicates
        existing_render_nodes = [node for node in node_tree.nodes if node.type == 'R_LAYERS']
        for node in existing_render_nodes:
            node_tree.nodes.remove(node)
        
        # Starting position for the first node
        x_pos = -1600
        y_pos = 0
        
        # Create a Render Layers node for each view layer
        for view_layer in view_layers:
            # Create the Render Layers node
            render_node = node_tree.nodes.new('CompositorNodeRLayers')
            render_node.name = f"RenderLayers_{view_layer.name}"
            render_node.label = f"RenderLayers_{view_layer.name}"
            render_node.location = (x_pos, y_pos)
            render_node.layer = view_layer.name
            
            # Position the next node to the right
            x_pos += 300
        
        self.report({'INFO'}, f"Created {len(view_layers)} Render Layers nodes")
        return {'FINISHED'}

# -------------------------------------------------------
# EXISTING OPERATORS (unchanged)
# -------------------------------------------------------

class ToggleAllSetAlpha(bpy.types.Operator):
    bl_idname = "nodes.toggle_all_set_alpha"
    bl_label = "Toggle All Set Alpha"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.compositing_settings
        current_state = settings.set_alpha_passes[0]
        new_state = not current_state
        for i in range(len(DEFAULT_PASSES)):
            settings.set_alpha_passes[i] = new_state
        return {'FINISHED'}

class ToggleAllDenoise(bpy.types.Operator):
    bl_idname = "nodes.toggle_all_denoise"
    bl_label = "Toggle All Denoise"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.compositing_settings
        current_state = settings.denoise_passes[0]
        new_state = not current_state
        for i in range(len(DEFAULT_PASSES)):
            settings.denoise_passes[i] = new_state
        return {'FINISHED'}

class ToggleAllAlbedo(bpy.types.Operator):
    bl_idname = "nodes.toggle_all_albedo"
    bl_label = "Toggle All Albedo"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.compositing_settings
        current_state = settings.use_denoise_albedo[0]
        new_state = not current_state
        for i in range(len(DEFAULT_PASSES)):
            settings.use_denoise_albedo[i] = new_state
        return {'FINISHED'}

class ToggleAllNormal(bpy.types.Operator):
    bl_idname = "nodes.toggle_all_normal"
    bl_label = "Toggle All Normal"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.compositing_settings
        current_state = settings.use_denoise_normal[0]
        new_state = not current_state
        for i in range(len(DEFAULT_PASSES)):
            settings.use_denoise_normal[i] = new_state
        return {'FINISHED'}

class UncheckAllPasses(bpy.types.Operator):
    bl_idname = "nodes.uncheck_all_passes"
    bl_label = "Uncheck All"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        settings = context.scene.compositing_settings
        for i in range(len(DEFAULT_PASSES)):
            settings.set_alpha_passes[i] = False
            settings.denoise_passes[i] = False
            settings.use_denoise_albedo[i] = False
            settings.use_denoise_normal[i] = False
        return {'FINISHED'}

# -------------------------------------------------------
# UPDATED AUTO COMPOSITING SETUP - Generates nodes for ALL view layers with SEPARATE OUTPUT NODES
# -------------------------------------------------------

class AutoCompositingSetup(bpy.types.Operator):
    bl_idname = "nodes.auto_compositing_setup"
    bl_label = "GENERATE NODES"
    bl_options = {'REGISTER', 'UNDO'}

    def execute(self, context):
        context.scene.use_nodes = True
        node_tree = context.scene.node_tree
        settings = context.scene.compositing_settings

        # Get settings
        set_alpha_passes = [pass_name for pass_name, enabled in zip(DEFAULT_PASSES, settings.set_alpha_passes) if enabled]
        denoise_passes = [pass_name for pass_name, enabled in zip(DEFAULT_PASSES, settings.denoise_passes) if enabled]
        use_denoise_albedo = [enabled for enabled in settings.use_denoise_albedo]
        use_denoise_normal = [enabled for enabled in settings.use_denoise_normal]
        denoise_mode = settings.denoise_mode

        # Clear all nodes only if "Keep existing path" is OFF
        if not settings.keep_existing_path:
            node_tree.nodes.clear()

        # Get all view layers
        view_layers = context.scene.view_layers
        
        if not view_layers:
            self.report({'ERROR'}, "No view layers found in scene")
            return {'CANCELLED'}

        def get_modified_name(base_name, view_layer_name):
            modified = ""
            if settings.use_prefix:
                modified += settings.prefix_text
                if settings.prefix_text:
                    modified += "_"
            # Add view layer name as prefix
            modified += view_layer_name + "_"
            modified += base_name
            if settings.use_suffix:
                if settings.suffix_text:
                    modified += "_"
                modified += settings.suffix_text
            return modified

        # Track created nodes for organization
        all_created_nodes = []

        # Process each view layer
        for view_layer_idx, view_layer in enumerate(view_layers):
            # Create Render Layers node for this view layer
            render_layers = node_tree.nodes.new('CompositorNodeRLayers')
            render_layers.name = f"RenderLayers_{view_layer.name}"
            render_layers.label = f"RenderLayers_{view_layer.name}"
            render_layers.location = (-1600, -view_layer_idx * 1200)
            render_layers.layer = view_layer.name
            all_created_nodes.append(render_layers)

            # Get the base path from settings
            base_path = settings.base_path
            
            # If base_path is empty, use default
            if not base_path or base_path == "//":
                base_path = "/tmp"
            
            # Convert relative paths to absolute
            if base_path.startswith("//"):
                base_path = bpy.path.abspath(base_path)
            
            # Normalize the path to ensure it's a clean base path
            base_path = base_path.rstrip(os.path.sep)
            
            # Ensure base_path doesn't end with view layer name already
            # If it does, remove it to avoid stacking
            base_dir = os.path.basename(base_path)
            if base_dir == view_layer.name:
                base_path = os.path.dirname(base_path)
            
            # Also check for CH_Beauty type patterns and remove them
            for pass_name in DEFAULT_PASSES + ["Beauty", "Shadow_Catcher"]:
                pattern = f"{view_layer.name}_{pass_name}"
                if base_dir == pattern:
                    base_path = os.path.dirname(base_path)
                    break

            # Create PNG File Output node for this view layer with view layer subdirectory
            # Always build from the clean base path
            png_base_path = os.path.join(base_path, view_layer.name)
            png_output = node_tree.nodes.new('CompositorNodeOutputFile')
            png_output.name = f"PNG_Output_{view_layer.name}"
            png_output.label = f"PNG {view_layer.name}"
            png_output.location = (600, -view_layer_idx * 700)
            png_output.format.file_format = 'PNG'
            png_output.format.color_mode = 'RGBA'
            png_output.format.color_depth = '16'
            png_output.format.compression = 15
            png_output.format.color_management = 'FOLLOW_SCENE'
            png_output.base_path = png_base_path
            png_output.width = 100000
            png_output.use_custom_color = True
            png_output.color = (0.2, 0.6, 0.2)  # Green color for PNG nodes

            # Create EXR DWAA File Output node for this view layer (non-cryptomatte EXR passes)
            exr_dwaa_folder_name = f"{view_layer.name}_EXR"
            exr_dwaa_full_path = os.path.join(base_path, view_layer.name, exr_dwaa_folder_name, exr_dwaa_folder_name)
            exr_dwaa_output = node_tree.nodes.new('CompositorNodeOutputFile')
            exr_dwaa_output.name = f"EXR_{view_layer.name}"
            exr_dwaa_output.label = f"EXR {view_layer.name}"
            exr_dwaa_output.location = (600, -view_layer_idx * 700 - 300)
            exr_dwaa_output.format.file_format = 'OPEN_EXR_MULTILAYER'
            exr_dwaa_output.format.color_depth = '16'
            exr_dwaa_output.format.exr_codec = 'DWAA'  # DWAA codec for non-cryptomatte EXR passes
            exr_dwaa_output.format.color_management = 'FOLLOW_SCENE'
            exr_dwaa_output.base_path = exr_dwaa_full_path
            exr_dwaa_output.use_custom_color = True
            exr_dwaa_output.color = (0.607, 0.176, 0.153)  # Red color for EXR nodes
            exr_dwaa_output.width = 100000

            # Create EXR PIZ File Output node for this view layer (cryptomatte passes)
            exr_piz_folder_name = f"{view_layer.name}_Cryptomatte"
            exr_piz_full_path = os.path.join(base_path, view_layer.name, exr_piz_folder_name, exr_piz_folder_name)
            exr_piz_output = node_tree.nodes.new('CompositorNodeOutputFile')
            exr_piz_output.name = f"Cryptomatte_{view_layer.name}"
            exr_piz_output.label = f"Cryptomatte {view_layer.name}"
            exr_piz_output.location = (600, -view_layer_idx * 700 - 600)
            exr_piz_output.format.file_format = 'OPEN_EXR_MULTILAYER'
            exr_piz_output.format.color_depth = '32'  # Full float for cryptomatte
            exr_piz_output.format.exr_codec = 'PIZ'  # PIZ codec for cryptomatte
            exr_piz_output.format.color_management = 'FOLLOW_SCENE'
            exr_piz_output.base_path = exr_piz_full_path
            exr_piz_output.use_custom_color = True
            exr_piz_output.color = (0.176, 0.176, 0.607)  # Blue color for cryptomatte EXR nodes
            exr_piz_output.width = 100000

            # Get required passes for this view layer
            alpha_socket = get_output_socket(render_layers, "Alpha")
            if not alpha_socket:
                self.report({'WARNING'}, f"Missing Alpha pass in Render Layers for {view_layer.name}")
                continue

            albedo_socket = get_output_socket(render_layers, 'Denoising Albedo')
            normal_socket = get_output_socket(render_layers, 'Denoising Normal')

            # Connect Beauty pass for this view layer to PNG output with double naming
            beauty_socket = get_output_socket(render_layers, "Image")
            if beauty_socket:
                modified_beauty_name = get_modified_name("Beauty", view_layer.name)
                # Create double naming structure: CH_Beauty/CH_Beauty
                beauty_slot = f"{modified_beauty_name}/{modified_beauty_name}"
                output_slot = png_output.file_slots.new(beauty_slot)
                node_tree.links.new(beauty_socket, output_slot)
            else:
                self.report({'WARNING'}, f"Missing Image (Beauty) pass for {view_layer.name}")

            # Process default passes for this view layer to PNG output with double naming
            x, y = -1200, -view_layer_idx * 1200 + 400
            for i, pass_name in enumerate(DEFAULT_PASSES):
                if pass_name in EXR_DWAA_PASSES or pass_name in EXR_PIZ_PASSES:
                    continue  # Skip EXR passes
                    
                pass_socket = get_output_socket(render_layers, pass_name)
                if not pass_socket:
                    # Only show warning for passes that are actually enabled in settings
                    if (pass_name in set_alpha_passes or pass_name in denoise_passes or 
                        use_denoise_albedo[i] or use_denoise_normal[i]):
                        self.report({'WARNING'}, f"Missing pass: {pass_name} for {view_layer.name}")
                    continue

                modified_name = get_modified_name(pass_name, view_layer.name)
                # Create double naming structure: CH_PassName/CH_PassName
                slot_name = f"{modified_name}/{modified_name}"
                output_slot = png_output.file_slots.new(slot_name)

                if pass_name in denoise_passes:
                    denoise = node_tree.nodes.new('CompositorNodeDenoise')
                    denoise.location = (x + 200, y)
                    denoise.prefilter = denoise_mode
                    all_created_nodes.append(denoise)

                    if use_denoise_albedo[i] and albedo_socket:
                        node_tree.links.new(albedo_socket, denoise.inputs['Albedo'])
                    if use_denoise_normal[i] and normal_socket:
                        node_tree.links.new(normal_socket, denoise.inputs['Normal'])

                    if pass_name in set_alpha_passes:
                        set_alpha = node_tree.nodes.new('CompositorNodeSetAlpha')
                        set_alpha.location = (x, y)
                        all_created_nodes.append(set_alpha)
                        node_tree.links.new(pass_socket, set_alpha.inputs['Image'])
                        node_tree.links.new(alpha_socket, set_alpha.inputs['Alpha'])
                        node_tree.links.new(set_alpha.outputs['Image'], denoise.inputs['Image'])
                        node_tree.links.new(denoise.outputs['Image'], output_slot)
                    else:
                        node_tree.links.new(pass_socket, denoise.inputs['Image'])
                        node_tree.links.new(denoise.outputs['Image'], output_slot)
                else:
                    if pass_name in set_alpha_passes:
                        set_alpha = node_tree.nodes.new('CompositorNodeSetAlpha')
                        set_alpha.location = (x, y)
                        all_created_nodes.append(set_alpha)
                        node_tree.links.new(pass_socket, set_alpha.inputs['Image'])
                        node_tree.links.new(alpha_socket, set_alpha.inputs['Alpha'])
                        node_tree.links.new(set_alpha.outputs['Image'], output_slot)
                    else:
                        node_tree.links.new(pass_socket, output_slot)

                y -= 250

            # Connect Shadow Catcher to PNG output for this view layer with double naming
            shadow_socket = get_output_socket(render_layers, "Shadow Catcher") or get_output_socket(render_layers, "Shadow")
            if shadow_socket:
                modified_shadow_name = get_modified_name("Shadow_Catcher", view_layer.name)
                # Create double naming structure: CH_Shadow_Catcher/CH_Shadow_Catcher
                shadow_slot = f"{modified_shadow_name}/{modified_shadow_name}"
                output_slot = png_output.file_slots.new(shadow_slot)
                node_tree.links.new(shadow_socket, output_slot)

            # Connect non-cryptomatte EXR passes to DWAA output node for this view layer
            for pass_name in EXR_DWAA_PASSES:
                pass_socket = get_output_socket(render_layers, pass_name)
                if pass_socket:
                    # For EXR multilayer, we just use the pass name as the layer name
                    output_slot = exr_dwaa_output.file_slots.new(pass_name)
                    node_tree.links.new(pass_socket, output_slot)
                else:
                    self.report({'WARNING'}, f"Missing EXR DWAA pass: {pass_name} for {view_layer.name}")

            # Connect cryptomatte passes to PIZ output node for this view layer
            for pass_name in EXR_PIZ_PASSES:
                pass_socket = get_output_socket(render_layers, pass_name)
                if pass_socket:
                    # For EXR multilayer, we just use the pass name as the layer name
                    output_slot = exr_piz_output.file_slots.new(pass_name)
                    node_tree.links.new(pass_socket, output_slot)
                else:
                    # Don't warn about missing cryptomatte passes - they might not be enabled in view layer
                    continue

        self.report({'INFO'}, f"Generated compositing setup for {len(view_layers)} view layers with separate output nodes")
        return {'FINISHED'}

class COMPOSITING_PT_AutoSetupPanel(bpy.types.Panel):
    bl_label = "Set Alpha & Denoise"
    bl_idname = "COMPOSITING_PT_auto_setup"
    bl_space_type = 'NODE_EDITOR'
    bl_region_type = 'UI'
    bl_category = "Galih@2025"

    def draw(self, context):
        layout = self.layout
        settings = context.scene.compositing_settings
        
        # Default to active view layer if none selected
        if not settings.selected_view_layer:
            settings.selected_view_layer = context.view_layer.name
        
        layout.prop(settings, "selected_view_layer", text="View Layer")

        # -------------------------------------------------------
        # UPDATED PREFETCH BUTTON - Now creates Render Layers nodes for all view layers
        # -------------------------------------------------------
        layout.operator("nodes.prefetch_passes", text="Prefetch Passes", icon='FILE_REFRESH')

        view_layer = context.scene.view_layers.get(settings.selected_view_layer)
        enabled_passes = []
        if view_layer:
            render_layers = next((node for node in context.scene.node_tree.nodes if node.type == 'R_LAYERS' and node.layer == view_layer.name), None)
            enabled_passes = []
            for pass_name in DEFAULT_PASSES:
                if render_layers:
                    # use robust socket lookup
                    if get_output_socket(render_layers, pass_name):
                        enabled_passes.append(pass_name)
                else:
                    prop = PASS_MAP.get(pass_name, '')
                    if prop:
                        if getattr(view_layer.cycles, prop, False):
                            enabled_passes.append(pass_name)

        grid = layout.grid_flow(row_major=True, columns=5, align=True)
        grid.label(text="Pass")
        grid.label(text="Set Alpha")
        grid.label(text="Denoise")
        grid.label(text="Albedo")
        grid.label(text="Normal")

        for i, pass_name in enumerate(DEFAULT_PASSES):
            if pass_name in enabled_passes:
                grid.label(text=pass_name)
                grid.prop(settings, "set_alpha_passes", index=i, text="")
                grid.prop(settings, "denoise_passes", index=i, text="")
                grid.prop(settings, "use_denoise_albedo", index=i, text="")
                grid.prop(settings, "use_denoise_normal", index=i, text="")

        row = layout.row(align=True)
        row.operator(ToggleAllSetAlpha.bl_idname, text="Set Alpha")
        row.operator(ToggleAllDenoise.bl_idname, text="Denoise")
        row.operator(ToggleAllAlbedo.bl_idname, text="Albedo")
        row.operator(ToggleAllNormal.bl_idname, text="Normal")

        layout.separator()
        row = layout.row(align=True)
        row.operator(UncheckAllPasses.bl_idname, text="Uncheck All")
        row.operator(RestoreDefaultSettings.bl_idname, text="Default")
        
        # Output Path Settings
        layout.separator()
        box = layout.box()
        box.label(text="Output Path Settings", icon='FILE_FOLDER')
        box.prop(settings, "base_path", text="Base Path")
        
        layout.prop(settings, "keep_existing_path")
        layout.prop(settings, "denoise_mode", text="Denoise Mode")
        layout.prop(settings, "use_prefix")
        if settings.use_prefix:
            layout.prop(settings, "prefix_text", text="Prefix")
        layout.prop(settings, "use_suffix")
        if settings.use_suffix:
            layout.prop(settings, "suffix_text", text="Suffix")
        layout.separator()
        layout.operator(AutoCompositingSetup.bl_idname, text="GENERATE NODES", icon='NODE_COMPOSITING')

def register():
    bpy.utils.register_class(CompositingSettings)
    bpy.utils.register_class(AutoCompositingSetup)
    bpy.utils.register_class(UncheckAllPasses)
    bpy.utils.register_class(ToggleAllSetAlpha)
    bpy.utils.register_class(ToggleAllDenoise)
    bpy.utils.register_class(ToggleAllAlbedo)
    bpy.utils.register_class(ToggleAllNormal)
    bpy.utils.register_class(RestoreDefaultSettings)
    bpy.utils.register_class(PrefetchPasses)
    bpy.utils.register_class(COMPOSITING_PT_AutoSetupPanel)
    bpy.types.Scene.compositing_settings = bpy.props.PointerProperty(type=CompositingSettings)

def unregister():
    bpy.utils.unregister_class(CompositingSettings)
    bpy.utils.unregister_class(AutoCompositingSetup)
    bpy.utils.unregister_class(UncheckAllPasses)
    bpy.utils.unregister_class(ToggleAllSetAlpha)
    bpy.utils.unregister_class(ToggleAllDenoise)
    bpy.utils.unregister_class(ToggleAllAlbedo)
    bpy.utils.unregister_class(ToggleAllNormal)
    bpy.utils.unregister_class(RestoreDefaultSettings)
    bpy.utils.unregister_class(PrefetchPasses)
    bpy.utils.unregister_class(COMPOSITING_PT_AutoSetupPanel)
    del bpy.types.Scene.compositing_settings

if __name__ == "__main__":
    register()