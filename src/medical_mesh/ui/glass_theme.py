"""Translucent workstation surfaces over a painted, platform-independent backdrop."""
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor,QPainter,QLinearGradient,QRadialGradient,QPainterPath,QPen
from PySide6.QtWidgets import QWidget,QFrame,QGraphicsDropShadowEffect


class GlassBackground(QWidget):
    def paintEvent(self,event):
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        gradient=QLinearGradient(0,0,self.width(),self.height())
        gradient.setColorAt(0,QColor('#d1d5df'));gradient.setColorAt(.55,QColor('#e8e9ed'));gradient.setColorAt(1,QColor('#d1d5df'))
        painter.fillRect(self.rect(),gradient)
        for x,y,r,color in ((.15,.12,650,QColor(206,218,235,18)),(.95,.7,600,QColor(206,218,235,12))):
            glow=QRadialGradient(self.width()*x,self.height()*y,r)
            glow.setColorAt(0,color);glow.setColorAt(1,QColor(255,255,255,0));painter.fillRect(self.rect(),glow)


class OpticalGlass(QWidget):
    """Paint a specular meniscus and reflected light across the glass surface."""
    def paintEvent(self,event):
        super().paintEvent(event)
        painter=QPainter(self);painter.setRenderHint(QPainter.Antialiasing)
        w,h=self.width(),self.height()
        light=QLinearGradient(0,0,w,h*.45)
        light.setColorAt(0,QColor(255,255,255,145));light.setColorAt(.45,QColor(255,255,255,12));light.setColorAt(.7,QColor(255,255,255,75));light.setColorAt(1,QColor(255,255,255,0))
        lens=QPainterPath();lens.moveTo(1,1);lens.lineTo(w-1,1);lens.lineTo(w-1,min(35,h*.35));lens.cubicTo(w*.65,h*.08,w*.35,h*.43,1,h*.25);lens.closeSubpath()
        painter.fillPath(lens,light)
        painter.setPen(QPen(QColor(255,255,255,210),1));painter.drawRoundedRect(self.rect().adjusted(1,1,-2,-2),2,2)
        painter.setPen(QPen(QColor(88,123,157,45),1));painter.drawLine(3,h-3,w-3,h-3)


def glass_card(widget,name):
    widget.setObjectName(name);widget.setAttribute(Qt.WA_StyledBackground,True)
    return widget


STYLE='''
QMainWindow { color:#253d54; }
QWidget { font-family:"Microsoft YaHei UI","Segoe UI"; font-size:12px; color:#253d54; }
QWidget#ribbon, QWidget#settingsCard, QWidget#inspectorCard, QWidget#canvasCard, QWidget#reviewCard {
 background:rgba(255,255,255,185); border:1px solid rgba(255,255,255,235); border-radius:14px;
}
QLabel { background:transparent; border:0; }
QLabel#brand { font-size:23px; font-weight:700; color:#173a59; }
QLabel#brandIcon { font-size:25px; color:white; font-weight:700; background:#268caa; border-radius:12px; padding:7px 13px; }
QLabel#subtitle { color:#7890a3; font-size:11px; }
QLabel#modelName { color:#55758c; padding:5px 10px; background:rgba(255,255,255,150); border-radius:8px; }
QLabel#stateBadge { color:#267f82; padding:7px 12px; background:rgba(214,241,235,200); border:1px solid #c2e6e0; border-radius:12px; }
QLabel#sectionTitle { color:#324f67; font-size:14px; font-weight:700; padding:3px 0; }
QLabel#sectionHint { color:#8096a7; font-size:11px; }
QLabel#summaryStrip { color:#617d92; padding:5px 12px; }
QLabel#canvasNotice { color:#6f879a; padding:7px 10px; }
QPushButton,QToolButton { background:rgba(255,255,255,190); border:1px solid #d4e1ea; border-radius:7px; padding:7px 10px; min-height:18px; }
QPushButton:hover,QToolButton:hover { background:#edf8fc; border-color:#75bbcf; }
QPushButton:pressed,QToolButton:pressed { background:#daedf5; }
QPushButton:disabled,QToolButton:disabled { color:#a6b4c0; background:rgba(235,241,246,120); border-color:#e0e8ee; }
QPushButton#primaryAction { background:#218ca4; color:white; border-color:#218ca4; font-weight:600; }
QPushButton#primaryAction:hover { background:#197a94; }
QPushButton#primaryAction:disabled { background:#c6dce2; border-color:#c6dce2; color:#f3f8fa; }
QPushButton#acceptAction { background:#e0f3ea; border-color:#aed8c3; color:#27765b; }
QToolButton#stepTab { padding:9px 19px; background:transparent; border:0; border-bottom:3px solid transparent; border-radius:0; color:#688397; }
QToolButton#stepTab:checked { color:#177e9a; border-bottom:3px solid #289bb6; background:rgba(225,244,249,150); font-weight:700; }
QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox { background:rgba(255,255,255,205); border:1px solid #d3e1ea; border-radius:6px; padding:5px 7px; min-height:18px; selection-background-color:#268eaa; }
QComboBox:focus,QLineEdit:focus,QSpinBox:focus,QDoubleSpinBox:focus { border-color:#54adc4; }
QComboBox::drop-down { width:20px; border:0; }
QComboBox QAbstractItemView { background:white; color:#253d54; selection-background-color:#dceff6; }
QScrollArea,QStackedWidget { border:0; background:transparent; }
QScrollArea > QWidget > QWidget { background:transparent; }
QGroupBox { border:1px solid #dce7ee; border-radius:8px; margin-top:15px; padding:10px; background:rgba(255,255,255,80); }
QGroupBox::title { subcontrol-origin:margin; left:10px; color:#51718a; }
QListWidget,QTableWidget,QPlainTextEdit,QTextBrowser { background:rgba(255,255,255,150); alternate-background-color:#f0f6fa; border:1px solid #e0e9ef; border-radius:7px; selection-background-color:#dbf0f7; selection-color:#1d5f78; }
QListWidget::item { padding:7px 4px; border-bottom:1px solid #edf2f6; }
QListWidget::item:selected { background:#dff1f7; color:#146f89; border-radius:4px; }
QHeaderView::section { background:#eef5f9; color:#648197; border:0; padding:7px; }
QTabWidget::pane { border:0; background:transparent; }
QTabBar::tab { background:transparent; color:#7c92a4; padding:9px 10px; border-bottom:2px solid transparent; }
QTabBar::tab:selected { color:#217e99; border-bottom:2px solid #39a1b8; }
QCheckBox { spacing:7px; padding:4px 0; }
QCheckBox::indicator { width:15px; height:15px; border:1px solid #b7cddc; border-radius:4px; background:white; }
QCheckBox::indicator:checked { background:#258faa; border:3px solid #d2edf3; }
QScrollBar:vertical { width:7px; background:transparent; margin:2px; }
QScrollBar::handle:vertical { background:#c5d8e3; min-height:30px; border-radius:3px; }
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical { height:0; }
QSplitter::handle { background:transparent; width:9px; }
QProgressBar { border:0; background:#e1edf3; border-radius:5px; max-height:10px; color:transparent; }
QProgressBar::chunk { background:#309cb4; border-radius:5px; }
QToolTip { background:#f8fcff; color:#2e516b; border:1px solid #bed7e4; padding:6px; }
'''

# Compact engineering ribbon: translucent silver surfaces with sharp optical edges.
STYLE+='''
QWidget { font-size:11px; color:#263b51; }
QWidget#ribbon { border-radius:2px; border:1px solid #9aabbc;
 background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 rgba(255,255,255,245),stop:.12 rgba(227,239,250,222),stop:.48 rgba(204,220,236,220),stop:.5 rgba(193,211,229,220),stop:1 rgba(229,239,249,237)); }
QWidget#settingsCard,QWidget#inspectorCard,QWidget#canvasCard,QWidget#reviewCard {
 border-radius:2px; border:1px solid #a3b3c3;
 background:qlineargradient(x1:0,y1:0,x2:1,y2:1,stop:0 rgba(255,255,255,220),stop:.4 rgba(232,241,250,200),stop:1 rgba(213,228,242,215)); }
QLabel#brand {font-size:12px;font-weight:600;color:#334e69;}
QLabel#brandIcon {font-size:12px;border-radius:4px;padding:2px 7px;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #64b4e8,stop:.5 #247bb7,stop:1 #164b80);}
QLabel#modelName {padding:1px 8px;border-radius:2px;background:transparent;}
QLabel#stateBadge {min-width:140px;padding:1px 8px;border-radius:2px;background:transparent;border:0;color:#45677d;}
QLabel#sectionTitle {font-size:12px;padding:2px 0;}
QLabel#sectionHint {font-size:10px;color:#60798f;}
QLabel#summaryStrip {font-size:10px;padding:1px 7px;background:rgba(235,243,250,210);border-top:1px solid #b7c7d6;}
QLabel#canvasNotice {font-size:10px;padding:2px 5px;}
QWidget#ribbonGroup {border:0;border-right:1px solid #a9bbcd;border-radius:0;background:transparent;}
QLabel#groupCaption {font-size:10px;color:#596f85;border-top:1px solid rgba(255,255,255,160);padding:1px;}
QToolButton#ribbonCommand {min-width:62px;max-width:85px;min-height:52px;padding:3px 5px;background:transparent;border:1px solid transparent;border-radius:2px;}
QToolButton#ribbonCommand:hover,QToolButton#railCommand:hover {border:1px solid #e3b65b;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fff6d9,stop:1 #f6d98d);}
QToolButton#stepTab {padding:0 12px;font-size:12px;min-height:15px;border:1px solid transparent;border-bottom:0;border-radius:2px;color:#3c556d;}
QToolButton#stepTab:checked {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 white,stop:1 #dce9f6);border:1px solid #9cafc2;border-bottom:0;color:#164c79;}
QWidget#viewRail {background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #edf3f9,stop:.5 #d6e3f0,stop:1 #c0cfde);border:1px solid #a0b2c3;}
QToolButton#railCommand {padding:4px 1px;min-height:42px;border-radius:2px;background:transparent;border:1px solid transparent;}
QLabel#dockTitle {font-weight:600;padding:4px;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f9fcff,stop:.48 #dce8f4,stop:.5 #c5d5e5,stop:1 #e5eef7);border:1px solid #a6b6c7;}
QPushButton,QToolButton {border-radius:2px;padding:3px 7px;min-height:17px;}
QPushButton#primaryAction {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f7fcff,stop:.48 #d9ecfa,stop:.5 #bed9ed,stop:1 #dfedf8);color:#245b86;border:1px solid #96b6d0;}
QComboBox,QLineEdit,QSpinBox,QDoubleSpinBox {border-radius:2px;padding:3px 5px;min-height:16px;}
QTabBar::tab {padding:5px 9px;border:1px solid transparent;border-bottom:0;}
QTabBar::tab:selected {color:#244f75;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 white,stop:1 #dce9f4);border:1px solid #aebfd0;border-bottom:0;}
QTreeWidget {background:rgba(248,251,255,220);border:1px solid #b0bfce;alternate-background-color:#edf3f9;}
QTreeWidget::item {padding:3px;}
QHeaderView::section {padding:3px;background:#e4edf6;border-right:1px solid #c1cedb;}
QListWidget::item {padding:4px 2px;}
QSplitter::handle {width:3px;height:3px;background:#bdcbd9;}
QCheckBox::indicator {border-radius:2px;width:12px;height:12px;}
'''

# E-3D reference: neutral blue-grey chrome, pale lavender property pages,
# and the saturated Windows blue used for selected model rows.
STYLE+='''
QWidget {color:#182f51;}
QWidget#ribbon {border:1px solid #a1a7b1;background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f5f6f8,stop:.18 #d7dce5,stop:.55 #e4e8eb,stop:1 #f3f7f6);}
QWidget#settingsCard,QWidget#inspectorCard,QWidget#reviewCard {border:1px solid #a9aeb8;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #e5e6ef,stop:1 #f0f0f6);}
QWidget#canvasCard {background:#d2d4d9;border:1px solid #92979f;}
QWidget#viewRail {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #e7e9eb,stop:.48 #c2c4c7,stop:1 #e6e7e9);border-color:#92979f;}
QWidget#sidebarHeader,QLabel#dockTitle {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #fafafa,stop:.48 #e3e4e6,stop:.5 #c3c5c9,stop:1 #ededee);border:1px solid #a6a9af;color:#122844;}
QToolButton#sidebarClose {padding:0;min-width:16px;max-width:16px;min-height:16px;max-height:16px;border:1px solid transparent;background:transparent;font-size:15px;}
QToolButton#sidebarClose:hover {background:#eac4c2;border-color:#c9817b;}
QToolButton#sidebarEdge {padding:0;min-width:15px;max-width:15px;min-height:25px;border:1px solid #b1bdcf;border-radius:0;color:#7c91ab;font-size:25px;background:qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 #edf5ff,stop:.5 #c4dcfa,stop:1 #e6effc);}
QToolButton#sidebarEdge:hover {color:#006fbc;background:#d4e8ff;}
QToolButton#stepTab:checked,QTabBar::tab:selected {background:qlineargradient(x1:0,y1:0,x2:0,y2:1,stop:0 #f8fbff,stop:1 #e5e8ee);color:#102a4e;border-color:#9da7b7;}
QTreeWidget,QListWidget,QTableWidget {background:#fff;selection-background-color:#0078d7;selection-color:white;border-color:#b4b8c2;}
QTreeWidget::item:selected,QListWidget::item:selected {background:#0078d7;color:white;}
QHeaderView::section {background:#f0f0f5;color:#182f51;border-right:1px solid #a8afbd;}
QLabel#summaryStrip {background:#d1d5df;border-color:#9ca5b5;color:#233f67;}
QSplitter::handle {background:#b7bbc4;}
QMenu {background:#f3f4f7;border:1px solid #9ea9ba;padding:4px;}
QMenu::item {padding:6px 22px;}
QMenu::item:selected {background:#cce4fc;color:#10375e;}
'''
