bl_info = {
    "name": "Curve Alignment",
    "author": "Vesper",
    "version": (1, 0),
    "blender": (4, 3, 2),
    "location": "View3D > Sidebar > My Tools",
    "description": "Align ends of roads for Overpass Generator",
    "category": "3D View",
}

import bpy
from mathutils import Vector

class SecondaryCurveItem(bpy.types.PropertyGroup):
    curve: bpy.props.PointerProperty(
        name="Secondary Curve",
        type=bpy.types.Object,
        description="Select a secondary Bézier curve object"
    )
    
class CurveProperties(bpy.types.PropertyGroup):
    primary_curve: bpy.props.PointerProperty(
        name="Primary Curve",
        type=bpy.types.Object,
        description="Select the primary Bézier curve object"
    )
    secondary_curves: bpy.props.CollectionProperty(
        name="Secondary Curves",
        type=SecondaryCurveItem,
        description="List of secondary Bézier curve objects"
    )
    num_secondary_curves: bpy.props.IntProperty(
        name="Number of Secondary Curves",
        description="Specify the number of secondary curves",
        default=1,
        min=1,
        update=lambda self, context: self.update_secondary_curves(context)
    )

    def update_secondary_curves(self, context):
        current_count = len(self.secondary_curves)
        target_count = self.num_secondary_curves
        if target_count > current_count:
            for _ in range(target_count - current_count):
                self.secondary_curves.add()
        elif target_count < current_count:
            for _ in range(current_count - target_count):
                self.secondary_curves.remove(len(self.secondary_curves) - 1)

class CURVE_OT_AlignClosestEndpoints(bpy.types.Operator):
    bl_idname = "curve.align_closest_endpoints"
    bl_label = "Align Closest Endpoints"
    bl_description = "Align the closest endpoints of the secondary curve to the primary curve"

    def align_end_points_in_one_curve(self, index, context):
        props = context.scene.curve_props
        primary_curve = props.primary_curve
        secondary_curve = props.secondary_curves[index].curve
        num_secondary_curves = props.num_secondary_curves

        if not primary_curve or not secondary_curve:
            self.report({'ERROR'}, "Both curve objects must be selected.")
            return {'CANCELLED'}
        if primary_curve.type != 'CURVE' or secondary_curve.type != 'CURVE':
            self.report({'ERROR'}, "Both selected objects must be curves.")
            return {'CANCELLED'}

        def get_endpoint_data(curve_obj, at_start=True):
            if not curve_obj.data.splines:
                return None, None, None
            spline = curve_obj.data.splines[0]
            if spline.type != 'BEZIER' or len(spline.bezier_points) < 2:
                return None, None, None
            point = spline.bezier_points[0] if at_start else spline.bezier_points[-1]
            handle = point.handle_right if at_start else point.handle_left
            point_global = curve_obj.matrix_world @ point.co
            handle_global = curve_obj.matrix_world @ handle
            tangent_global = (handle_global - point_global).normalized()
            return point, point_global, tangent_global

        primary_start_point, primary_start_global, primary_start_tangent = get_endpoint_data(primary_curve, at_start=True)
        primary_end_point, primary_end_global, primary_end_tangent = get_endpoint_data(primary_curve, at_start=False)
        if not primary_start_point or not primary_end_point:
            self.report({'ERROR'}, "Failed to retrieve endpoint data from the primary curve.")
            return {'CANCELLED'}

        secondary_start_point, secondary_start_global, secondary_start_tangent = get_endpoint_data(secondary_curve, at_start=True)
        secondary_end_point, secondary_end_global, secondary_end_tangent = get_endpoint_data(secondary_curve, at_start=False)
        if not secondary_start_point or not secondary_end_point:
            self.report({'ERROR'}, "Failed to retrieve endpoint data from the secondary curve.")
            return {'CANCELLED'}

        distances = {
            'primary_start_to_secondary_start': (primary_start_global - secondary_start_global).length,
            'primary_start_to_secondary_end': (primary_start_global - secondary_end_global).length,
            'primary_end_to_secondary_start': (primary_end_global - secondary_start_global).length,
            'primary_end_to_secondary_end': (primary_end_global - secondary_end_global).length,
        }

        min_distance_key = min(distances, key=distances.get)

        if min_distance_key == 'primary_start_to_secondary_start':
            primary_point = primary_start_point
            primary_global = primary_start_global
            primary_tangent = primary_start_tangent
            secondary_point = secondary_start_point
            secondary_global = secondary_start_global
        elif min_distance_key == 'primary_start_to_secondary_end':
            primary_point = primary_start_point
            primary_global = primary_start_global
            primary_tangent = primary_start_tangent
            secondary_point = secondary_end_point
            secondary_global = secondary_end_global
        elif min_distance_key == 'primary_end_to_secondary_start':
            primary_point = primary_end_point
            primary_global = primary_end_global
            primary_tangent = primary_end_tangent
            secondary_point = secondary_start_point
            secondary_global = secondary_start_global
        else:
            primary_point = primary_end_point
            primary_global = primary_end_global
            primary_tangent = primary_end_tangent
            secondary_point = secondary_end_point
            secondary_global = secondary_end_global

        if bpy.context.object.mode == 'EDIT':
            bpy.ops.object.mode_set(mode='OBJECT')
            
        # Decide the new location based on road width
        modifier = primary_curve.modifiers.get("GeometryNodes")

        if modifier is None:
            self.report({'ERROR'}, "Geometry Nodes not found on the object")
        else:
            RoadWidth = modifier["Socket_5"] * 2
 
        position_offset_dir = primary_tangent.cross(Vector((0, 0, 1)))
        position_offset = position_offset_dir * ((RoadWidth * (2 * index + 1)) / (2 * num_secondary_curves) - RoadWidth / 2)
        print(RoadWidth, index, num_secondary_curves, position_offset_dir, position_offset)
        
        secondary_point.co = secondary_curve.matrix_world.inverted() @ (primary_global + position_offset)
        print(secondary_point.co)
        if secondary_point == secondary_start_point:
            secondary_point.handle_right = secondary_point.co - (secondary_curve.matrix_world.inverted().to_3x3() @ primary_tangent)
        else:
            secondary_point.handle_left = secondary_point.co - (secondary_curve.matrix_world.inverted().to_3x3() @ primary_tangent)
        
    def execute(self, context):
        props = context.scene.curve_props
        for i in range(0, props.num_secondary_curves):
            self.align_end_points_in_one_curve(index=i, context=context)
            
        return {'FINISHED'}

class CURVE_PT_CurveAlignmentPanel(bpy.types.Panel):
    bl_label = "Curve Alignment"
    bl_idname = "CURVE_PT_curve_alignment_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Tool'

    def draw(self, context):
        layout = self.layout
        props = context.scene.curve_props

        layout.prop(props, "primary_curve")
        layout.prop(props, "num_secondary_curves")

        for i, item in enumerate(props.secondary_curves):
            layout.prop(item, "curve", text=f"Secondary Curve {i + 1}")

        layout.operator("curve.align_closest_endpoints")
        
classes = [SecondaryCurveItem, CurveProperties, CURVE_OT_AlignClosestEndpoints, CURVE_PT_CurveAlignmentPanel]

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.curve_props = bpy.props.PointerProperty(type=CurveProperties)

def unregister():
    for cls in classes:
        bpy.utils.unregister_class(cls)
    del bpy.types.Scene.curve_props

if __name__ == "__main__":
    register()