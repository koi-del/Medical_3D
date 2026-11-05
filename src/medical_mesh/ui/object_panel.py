"""Version-bound display controls and factual model properties."""
import numpy as np
from PySide6.QtCore import Qt,Signal
from PySide6.QtGui import QColor,QBrush
from PySide6.QtWidgets import (QWidget,QVBoxLayout,QHBoxLayout,QTreeWidget,QTreeWidgetItem,
    QLabel,QLineEdit,QPushButton,QSpinBox,QColorDialog,QFormLayout)


def version_of(asset):
    return getattr(asset,'version',getattr(asset,'version_id',None))


def geometry_properties(asset):
    """Bound intermediate allocation even for large meshes; no volume assumption."""
    area=0.;edge_sum=0.
    for start in range(0,len(asset.faces),50000):
        tri=asset.vertices[asset.faces[start:start+50000]]
        area+=float(np.linalg.norm(np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0]),axis=1).sum()/2)
        edge_sum+=sum(float(np.linalg.norm(tri[:,i]-tri[:,j],axis=1).sum()) for i,j in ((0,1),(1,2),(2,0)))
    known=asset.unit_status=='confirmed'
    unit=(getattr(asset,'source_unit',None) or getattr(asset,'unit_name',None)) if known else None
    return dict(vertices=len(asset.vertices),faces=len(asset.faces),area=area,
        face_edge_mean=edge_sum/(3*len(asset.faces)),minimum=asset.vertices.min(axis=0).tolist(),
        maximum=asset.vertices.max(axis=0).tolist(),dimensions=np.ptp(asset.vertices,axis=0).tolist(),unit=unit or '原坐标单位（未确认）')


class ObjectPanel(QWidget):
    display_changed=Signal()

    def __init__(self,parent=None):
        super().__init__(parent);self.entries=[];self.styles={};self.properties={};self._key=None;self._binding=False
        layout=QVBoxLayout(self);layout.setContentsMargins(0,0,0,0);layout.setSpacing(3)
        self.tree=QTreeWidget();self.tree.setHeaderLabels(['模型 / 结果','状态','颜色']);self.tree.setRootIsDecorated(False);self.tree.setMinimumHeight(90);self.tree.setColumnWidth(0,165);self.tree.setColumnWidth(1,95);self.tree.setColumnWidth(2,42)
        self.tree.itemChanged.connect(self._visibility_changed);self.tree.currentItemChanged.connect(self._select);self.tree.itemDoubleClicked.connect(self._double_click);layout.addWidget(self.tree,1)
        form=QFormLayout();form.setContentsMargins(5,1,5,1)
        self.name=QLineEdit();self.name.setPlaceholderText('显示名称（不修改源文件）');self.name.editingFinished.connect(self._rename);form.addRow('显示名称',self.name)
        row=QHBoxLayout();self.color=QPushButton('模型颜色');self.color.clicked.connect(self.choose_color);row.addWidget(self.color)
        self.opacity=QSpinBox();self.opacity.setRange(0,100);self.opacity.setSuffix(' %');self.opacity.setToolTip('仅调整所选对象的透明度；0%完全透明');self.opacity.valueChanged.connect(self._opacity_changed);row.addWidget(QLabel('不透明度'));row.addWidget(self.opacity);form.addRow(row);layout.addLayout(form)
        self.info=QLabel('打开模型后显示点数、面数、面积和包围盒。');self.info.setWordWrap(True);self.info.setTextInteractionFlags(Qt.TextSelectableByMouse);layout.addWidget(self.info)
        self.set_controls(False)

    def set_controls(self,enabled):
        for widget in (self.name,self.color,self.opacity):widget.setEnabled(enabled)

    def selected(self):
        item=self.tree.currentItem()
        return next((entry for entry in self.entries if version_of(entry['asset'])==item.data(0,Qt.UserRole)),None) if item else None

    def bind(self,entries):
        key=tuple((version_of(e['asset']),e['label'],e['state']) for e in entries)
        if key==self._key:return
        previous=self.selected();selected=version_of(previous['asset']) if previous else None
        self.entries=entries;self._key=key;self._binding=True;self.tree.clear()
        for index,entry in enumerate(entries):
            version=version_of(entry['asset']);style=self.styles.setdefault(version,dict(visible=True,color='#76bcb2' if index==0 else '#e0af69',opacity=100,alias=''))
            item=QTreeWidgetItem([style['alias'] or entry['label'],entry['state'],'■']);item.setData(0,Qt.UserRole,version);item.setFlags(item.flags()|Qt.ItemIsUserCheckable);item.setCheckState(0,Qt.Checked if style['visible'] else Qt.Unchecked);item.setForeground(2,QBrush(QColor(style['color'])));item.setToolTip(0,'版本 '+version+'\n勾选控制三维显示；双击颜色列修改颜色。');self.tree.addTopLevelItem(item)
            if version==selected:self.tree.setCurrentItem(item)
        self._binding=False
        if self.tree.currentItem() is None and entries:self.tree.setCurrentItem(self.tree.topLevelItem(0))
        self._select();self.display_changed.emit()

    def _select(self,*_):
        entry=self.selected();self.set_controls(bool(entry))
        if not entry:return
        version=version_of(entry['asset']);style=self.styles[version];self._binding=True
        self.name.setText(style['alias'] or entry['label']);self.opacity.setValue(style['opacity']);self.color.setStyleSheet('border-bottom:3px solid '+style['color']);self._binding=False
        if version not in self.properties:self.properties[version]=geometry_properties(entry['asset'])
        p=self.properties[version];fmt=lambda a:' × '.join(f'{x:.5g}' for x in a)
        self.info.setText(f"顶点 {p['vertices']:,} · 三角面 {p['faces']:,}\n单位：{p['unit']}\n表面积：{p['area']:.6g}（单位²） · 面边均长：{p['face_edge_mean']:.5g}\n包围盒尺寸：{fmt(p['dimensions'])}\n最小坐标：{fmt(p['minimum'])}\n最大坐标：{fmt(p['maximum'])}")
        self.info.setMinimumHeight(self.info.fontMetrics().lineSpacing()*7+8)
        self.info.setToolTip('面积及边长基于原网格，不使用简化显示网格。面边均长按每个面的三条边统计，共享边重复计数。围合体积仅在质量报告确认单闭合壳体时提供。')

    def _visibility_changed(self,item,column):
        if self._binding or column!=0:return
        self.styles[item.data(0,Qt.UserRole)]['visible']=item.checkState(0)==Qt.Checked;self.display_changed.emit()

    def _rename(self):
        entry=self.selected()
        if not entry:return
        style=self.styles[version_of(entry['asset'])];style['alias']=self.name.text().strip() or entry['label'];self.tree.currentItem().setText(0,style['alias']);self.display_changed.emit()

    def _opacity_changed(self,value):
        if self._binding:return
        entry=self.selected()
        if entry:self.styles[version_of(entry['asset'])]['opacity']=value;self.display_changed.emit()

    def _double_click(self,item,column):
        if column==2:self.choose_color()

    def choose_color(self):
        entry=self.selected()
        if not entry:return
        color=QColorDialog.getColor(QColor(self.styles[version_of(entry['asset'])]['color']),self,'设置模型显示颜色')
        if color.isValid():self.set_color(color.name())

    def set_color(self,color):
        entry=self.selected()
        if not entry or not QColor(color).isValid():return
        self.styles[version_of(entry['asset'])]['color']=QColor(color).name();self.tree.currentItem().setForeground(2,QBrush(QColor(color)));self._select();self.display_changed.emit()
