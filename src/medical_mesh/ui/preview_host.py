"""Standalone integration host. Member 2 can register Member1Panel in its window."""
import sys
from pathlib import Path
import numpy as np
import pyvista as pv
from pyvistaqt import QtInteractor
from PySide6.QtWidgets import QApplication,QMainWindow,QSplitter
from .member1_panel import Member1Panel
from .selection import selection_geometry
from .display_mesh import display_mesh


class ViewerAdapter:
    def __init__(self,parent):
        self.plotter=QtInteractor(parent)
        self.other_plotter=QtInteractor(parent)
        self.interactor=QSplitter()
        self.interactor.addWidget(self.plotter.interactor)
        self.interactor.addWidget(self.other_plotter.interactor)
        self.other_plotter.interactor.hide()
        self.other_plotter.set_background('#172334')
        self.comparing=False
        self.syncing=False
        self.other_mesh=None
        self.other_full_mesh=None
        self.current_asset=None
        self.simplify_display=True
        self.mesh_cache={}
        self.display_mesh=None
        self.display_notice=''
        for plotter in (self.plotter,self.other_plotter):
            plotter.iren.add_observer('InteractionEvent',self._sync_comparison)
            plotter.iren.add_observer('EndInteractionEvent',self._sync_comparison)
        QApplication.instance().aboutToQuit.connect(self.other_plotter.close)
        self.version=None
        self.highlight_actors=[]
        self.focus_points=None
        self.base_mesh=None
        self.local_view=False
        self.plotter.set_background("#172334")

    def clear_highlights(self):
        if self.local_view and self.base_mesh is not None and 'base_mesh' in self.plotter.actors:
            self.plotter.actors['base_mesh'].mapper.dataset=self.display_mesh
        self.local_view=False
        if self.other_mesh is not None and 'other_mesh' in self.other_plotter.actors:
            self.other_plotter.actors['other_mesh'].mapper.dataset=self.other_mesh
        for name in self.highlight_actors:self.plotter.remove_actor(name,render=False)
        self.highlight_actors=[]
        self.focus_points=None

    def set_asset(self,asset,wireframe=False):
        self.current_asset=asset
        reset=self.version!=asset.asset_id
        self.plotter.clear()
        cache_key=(asset.version,self.simplify_display)
        if cache_key not in self.mesh_cache:
            full=pv.PolyData(asset.vertices.copy(),np.column_stack((np.full(len(asset.faces),3),asset.faces)).ravel())
            self.mesh_cache[cache_key]=(full,display_mesh(full,self.simplify_display))
            while len(self.mesh_cache)>2:self.mesh_cache.pop(next(iter(self.mesh_cache)))
        self.base_mesh,self.display_mesh=self.mesh_cache[cache_key]
        self.display_notice=(f'视图简化：显示 {self.display_mesh.n_cells} / 原始 {self.base_mesh.n_cells} 面；检测、选孔及导出使用原网格。'
                             if self.display_mesh is not self.base_mesh else '显示原网格。')
        self.plotter.add_mesh(self.display_mesh,name='base_mesh',color="#95d9d2",show_edges=wireframe,style="wireframe" if wireframe else "surface",
                              smooth_shading=True,lighting=True,ambient=.15,diffuse=.8,specular=.2)
        self.plotter.enable_lightkit()
        self.plotter.add_axes()
        if reset:self.plotter.reset_camera()
        self.version=asset.asset_id
        self.plotter.render()

    def _sync_comparison(self,*_):
        if self.comparing and not self.syncing:
            self.syncing=True
            try:self.plotter.render();self.other_plotter.render()
            finally:self.syncing=False

    @staticmethod
    def _change_faces(plotter,asset,ids,name,color):
        if not ids:return
        faces=asset.faces[ids]
        mesh=pv.PolyData(asset.vertices.copy(),np.column_stack((np.full(len(faces),3),faces)).ravel())
        actor=plotter.add_mesh(mesh,name=name,color=color,show_edges=True,line_width=2,
            lighting=False,pickable=False,reset_camera=False,render=False)
        actor.mapper.SetResolveCoincidentTopologyToPolygonOffset()
        actor.mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-3,-3)
        tri=asset.vertices[faces]
        collapsed=np.flatnonzero(np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1)==0)
        if len(collapsed):
            edges=sorted({tuple(sorted((int(a),int(b)))) for face in faces[collapsed]
                          for a,b in zip(face,np.roll(face,-1)) if a!=b})
            if edges:plotter.add_mesh(ViewerAdapter.line_mesh(asset.vertices,edges),name=name+'_lines',
                color=color,line_width=10,lighting=False,pickable=False,reset_camera=False,render=False)
            points=np.unique(faces[collapsed])
            plotter.add_mesh(pv.PolyData(asset.vertices[points].copy()),name=name+'_points',color=color,
                point_size=14,render_points_as_spheres=True,pickable=False,reset_camera=False,render=False)

    def set_comparison(self,review,side=0,dual=True,show_changes=True,wireframe=False):
        was_comparing=self.comparing
        for name in list(self.plotter.actors):
            if name.startswith('change_') or name=='comparison_label':self.plotter.remove_actor(name,render=False)
        self.comparing=review is not None and dual
        self.other_plotter.interactor.setVisible(self.comparing)
        if self.comparing and (not was_comparing or min(self.interactor.sizes())==0):
            half=max(1,self.interactor.width()//2);self.interactor.setSizes([half,half])
        if review is None:
            self.other_plotter.clear();self.other_mesh=None;self.other_full_mesh=None;return
        changes=review.result['metrics']['changes']
        assets=[review.candidate,review.input_asset]
        labels=['AFTER (preview)','BEFORE (input)']
        # Current diagnostic selection always belongs to the main/left view.
        self.plotter.add_text(labels[side],name='comparison_label',font_size=11,position='upper_left',color='white')
        if self.comparing:
            other=assets[1-side]
            self.other_plotter.clear()
            mesh=pv.PolyData(other.vertices.copy(),np.column_stack((np.full(len(other.faces),3),other.faces)).ravel())
            self.other_full_mesh=mesh
            mesh=display_mesh(mesh,self.simplify_display)
            self.other_mesh=mesh
            opacity=self.plotter.actors['base_mesh'].prop.opacity
            self.other_plotter.add_mesh(mesh,name='other_mesh',color='#95d9d2',smooth_shading=True,
                style='wireframe' if wireframe else 'surface',show_edges=wireframe,opacity=opacity,reset_camera=False)
            self.other_plotter.enable_lightkit()
            self.other_plotter.add_text(labels[1-side],font_size=11,position='upper_left',color='white')
            self.other_plotter.add_axes()
            self.other_plotter.camera=self.plotter.camera
        if show_changes:
            for plotter,index in [(self.plotter,side)]+([(self.other_plotter,1-side)] if self.comparing else []):
                asset=assets[index]
                ids=changes['added_face_ids'] if index==0 else changes['removed_face_ids']
                self._change_faces(plotter,asset,ids,'change_added' if index==0 else 'change_removed',
                                   '#50e3a4' if index==0 else '#fa6678')
                flipped=changes['flipped_output_face_ids'] if index==0 else changes['flipped_input_face_ids']
                self._change_faces(plotter,asset,flipped,'change_flipped','#ffbb48')
        self.plotter.render()
        if self.comparing:self.other_plotter.render()

    def highlight(self,asset,face_ids,edges):
        # Backwards-compatible minimal viewer interface for external hosts.
        self.highlight_diagnostics(asset,[dict(kind='duplicate',faces=face_ids,edges=edges,vertices=[])])

    def _add(self,mesh,name,**kwargs):
        actor=self.plotter.add_mesh(mesh,name=name,reset_camera=False,pickable=False,**kwargs)
        self.highlight_actors.append(name)
        return actor

    @staticmethod
    def line_mesh(vertices,edges):
        # Empty PolyData + explicit points avoids automatic vertex cells.
        edges=np.asarray(edges,dtype=int)
        ids,inverse=np.unique(edges,return_inverse=True)
        lines=pv.PolyData()
        lines.points=vertices[ids].copy()
        lines.lines=np.column_stack((np.full(len(edges),2),inverse.reshape(-1,2))).ravel()
        return lines

    def highlight_diagnostics(self,asset,selected):
        self.clear_highlights()
        geometry=selection_geometry(asset,selected)
        if geometry['faces']:
            faces=asset.faces[geometry['faces']]
            mesh=pv.PolyData(asset.vertices.copy(),np.column_stack((np.full(len(faces),3),faces)).ravel())
            actor=self._add(mesh,'selected_faces',color="#ff735c",show_edges=True,line_width=2,lighting=False)
            actor.mapper.SetResolveCoincidentTopologyToPolygonOffset()
            actor.mapper.SetRelativeCoincidentTopologyPolygonOffsetParameters(-2,-2)
        for key,color,name in [('edges','#ffd166','selected_edges'),('collapsed_edges','#ec79ff','collapsed_edges')]:
            if geometry[key]:
                self._add(self.line_mesh(asset.vertices,geometry[key]),name,color=color,line_width=9,
                          render_lines_as_tubes=True,lighting=False)
        if geometry['points']:
            self._add(pv.PolyData(asset.vertices[geometry['points']].copy()),'selected_points',color='#ec79ff',
                      point_size=16,render_points_as_spheres=True,lighting=False)
        for i,(origin,normal,length) in enumerate(geometry['normals']):
            self._add(pv.Arrow(start=origin,direction=normal,scale=length*.65,tip_radius=.045,shaft_radius=.012),f'normal_{i}',color='#49dbff',lighting=False)
        for i,(origin,direction) in enumerate(geometry['traversals']):
            self._add(pv.Arrow(start=origin,direction=direction,scale=float(np.linalg.norm(direction)),tip_radius=.045,shaft_radius=.012),
                      f'traversal_{i}',color='#ffad42',lighting=False)
        if geometry['focus_ids']:
            self.focus_points=asset.vertices[geometry['focus_ids']]
        self.plotter.render()

    def focus_selection(self,asset,zoom=1.):
        if self.focus_points is None:return
        center=self.focus_points.mean(axis=0)
        direction=center-asset.vertices.mean(axis=0)
        if np.linalg.norm(direction)<1e-10:direction=np.array([1.,1.,1.])
        direction=direction/np.linalg.norm(direction)
        tangent=np.cross(direction,[0.,0.,1.])
        if np.linalg.norm(tangent)<.1:tangent=np.cross(direction,[0.,1.,0.])
        direction=direction+.8*tangent/np.linalg.norm(tangent)
        direction=direction/np.linalg.norm(direction)
        span=float(np.linalg.norm(np.ptp(self.focus_points,axis=0)))
        scale=float(np.linalg.norm(np.ptp(asset.vertices,axis=0)))
        # Local surface context avoids the far wall visually filling a hole,
        # and an oblique camera makes normal arrows visible as arrows.
        radius=max(span*1.4,scale*.04)
        patch=self.base_mesh.clip_surface(pv.Sphere(radius=radius,center=center,theta_resolution=48,phi_resolution=48),invert=True)
        if patch.n_cells:
            self.plotter.actors['base_mesh'].mapper.dataset=patch
            self.local_view=True
        if self.comparing and self.other_mesh is not None:
            other_patch=self.other_full_mesh.clip_surface(pv.Sphere(radius=radius,center=center,theta_resolution=48,phi_resolution=48),invert=True)
            if other_patch.n_cells:self.other_plotter.actors['other_mesh'].mapper.dataset=other_patch
        distance=max(span*2.3,scale*.12)*zoom
        up=np.array([0.,0.,1.]) if abs(direction[2])<.9 else np.array([0.,1.,0.])
        self.plotter.camera_position=[center+direction*distance,center,up]
        self.plotter.camera.parallel_scale=max(span*.7,scale*.04)*zoom
        self.plotter.reset_camera_clipping_range();self.plotter.render()
        self._sync_comparison()

    def focus_review_changes(self,review):
        changes=review.result['metrics']['changes']
        points=[]
        for asset,fields in [(review.input_asset,('removed_face_ids','flipped_input_face_ids')),
                             (review.candidate,('added_face_ids','flipped_output_face_ids'))]:
            ids=sorted({i for field in fields for i in changes[field]})
            if ids:points.append(asset.vertices[asset.faces[ids]].reshape(-1,3))
        if points:
            self.focus_points=np.vstack(points)
            self.focus_selection(self.current_asset)

    def overview(self):
        if self.base_mesh is not None:self.plotter.actors['base_mesh'].mapper.dataset=self.display_mesh
        if self.other_mesh is not None and 'other_mesh' in self.other_plotter.actors:
            self.other_plotter.actors['other_mesh'].mapper.dataset=self.other_mesh
        self.local_view=False
        self.plotter.reset_camera();self.plotter.render()
        self._sync_comparison()

    def set_view(self,index):
        [self.plotter.view_isometric,self.plotter.view_xy,self.plotter.view_yz,self.plotter.view_xz][index]()
        self.plotter.render()
        self._sync_comparison()

    def set_opacity(self,value):
        if 'base_mesh' in self.plotter.actors:
            self.plotter.actors['base_mesh'].prop.opacity=value
            self.plotter.render()
        if self.comparing and 'other_mesh' in self.other_plotter.actors:
            self.other_plotter.actors['other_mesh'].prop.opacity=value
            self.other_plotter.render()

    def enable_boundary_picking(self,callback):
        self.plotter.disable_picking()
        if callback is not None:
            # Picking must use exact cells, not clustered display coordinates.
            if self.base_mesh is not None:self.plotter.actors['base_mesh'].mapper.dataset=self.base_mesh
            self.display_notice='选孔期间显示原网格；检测与导出使用原始数据。'
            self.plotter.enable_surface_point_picking(callback=callback,show_message=False,show_point=False,
                                                      left_clicking=False,picker='cell')
        elif self.base_mesh is not None and not self.local_view:
            self.plotter.actors['base_mesh'].mapper.dataset=self.display_mesh
            self.display_notice=(f'视图简化：显示 {self.display_mesh.n_cells} / 原始 {self.base_mesh.n_cells} 面；检测和导出使用原网格。'
                                 if self.display_mesh is not self.base_mesh else '显示原网格。')
            self.plotter.render()

    def save_snapshot(self,path):
        if self.comparing:self.interactor.grab().save(str(path))
        else:self.plotter.screenshot(path)


def main():
    app=QApplication.instance() or QApplication(sys.argv)
    class PreviewWindow(QMainWindow):
        def closeEvent(self,event):
            if panel.process:
                panel.cancel();panel.process.waitForFinished(1000)
            super().closeEvent(event)
    window=PreviewWindow();window.setWindowTitle("医学三维模型修复 · 成员1子系统")
    viewer=ViewerAdapter(window)
    panel=Member1Panel(viewer,Path.cwd()/"results"/"gui_session")
    window.setCentralWidget(panel);window.resize(1280,900);window.show()
    app.aboutToQuit.connect(viewer.plotter.close)
    return app.exec()
