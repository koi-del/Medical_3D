"""Dock-like sidebars with independent collapse, close and restore controls."""
from PySide6.QtCore import Qt,Signal,QTimer
from PySide6.QtWidgets import QWidget,QVBoxLayout,QHBoxLayout,QLabel,QToolButton,QSizePolicy,QSplitter


class Sidebar(QWidget):
    open_changed=Signal(bool)

    def __init__(self,title,content,side,minimum,maximum,parent=None):
        super().__init__(parent)
        self.title=title;self.side=side;self.minimum=minimum;self.maximum=maximum
        self.collapsed=False;self.closed=False
        self.setObjectName('sidebar')
        outer=QHBoxLayout(self);outer.setContentsMargins(0,0,0,0);outer.setSpacing(0)
        self.body=QWidget();body_layout=QVBoxLayout(self.body);body_layout.setContentsMargins(0,0,0,0);body_layout.setSpacing(0)
        header=QWidget();header.setObjectName('sidebarHeader');row=QHBoxLayout(header);row.setContentsMargins(4,1,2,1);row.setSpacing(1)
        label=QLabel(title);row.addWidget(label,1)
        self.close_button=QToolButton();self.close_button.setText('×');self.close_button.setToolTip('关闭'+title+'；可从顶部“侧栏”菜单恢复');self.close_button.setObjectName('sidebarClose');self.close_button.clicked.connect(self.close_sidebar);row.addWidget(self.close_button)
        body_layout.addWidget(header);body_layout.addWidget(content,1)
        self.edge=QToolButton();self.edge.setObjectName('sidebarEdge');self.edge.setFixedWidth(17);self.edge.setSizePolicy(QSizePolicy.Fixed,QSizePolicy.Expanding)
        self.edge.clicked.connect(self.toggle_collapse)
        if side=='right':outer.addWidget(self.edge);outer.addWidget(self.body,1)
        else:outer.addWidget(self.body,1);outer.addWidget(self.edge)
        self._apply()

    def _apply(self):
        self.body.setVisible(not self.collapsed)
        self.setMinimumWidth(17 if self.collapsed else self.minimum)
        self.setMaximumWidth(17 if self.collapsed else self.maximum)
        arrow=('›' if self.side=='right' else '‹')
        self.edge.setText(('‹' if self.side=='right' else '›') if self.collapsed else arrow)
        self.edge.setToolTip(('展开' if self.collapsed else '收起')+self.title)

    def toggle_collapse(self):
        parent=self.parentWidget()
        if isinstance(parent,QSplitter) and not self.collapsed:self._expanded_width=parent.sizes()[parent.indexOf(self)]
        self.collapsed=not self.collapsed;self._apply();self._redistribute()

    def _redistribute(self):
        parent=self.parentWidget()
        if not isinstance(parent,QSplitter):return
        sizes=parent.sizes();index=parent.indexOf(self)
        desired=17 if self.collapsed else max(self.minimum,getattr(self,'_expanded_width',self.minimum))
        sizes[index]=desired
        if len(sizes)>1:sizes[1]=max(50,parent.width()-parent.handleWidth()*(len(sizes)-1)-sum(v for i,v in enumerate(sizes) if i!=1))
        parent.setSizes(sizes);parent.updateGeometry()
        QTimer.singleShot(0,lambda:parent.setSizes(sizes))

    def close_sidebar(self):
        self.closed=True;self.hide();self.open_changed.emit(False)

    def set_open(self,opened):
        self.closed=not opened
        if opened:self.collapsed=False;self._apply();self.show();self._redistribute()
        else:self.hide()
        self.open_changed.emit(opened)
