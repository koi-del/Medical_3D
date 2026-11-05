"""Original vector glyphs for the workstation ribbon; no vendor assets."""
from PySide6.QtCore import QByteArray,Qt
from PySide6.QtGui import QIcon,QPixmap,QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QStyle

def technical_icon(kind):
    shapes={
        QStyle.SP_DialogOpenButton:'<path d="M5 15h12l5 5h20v22H5z"/><path d="M5 26h39l-7 16H5z" fill="url(#a)"/>',
        QStyle.SP_DialogSaveButton:'<path d="M8 6h28l6 6v30H8z"/><path d="M15 6h19v14H15zM15 29h20v13H15z" fill="#e5f8ff"/><path d="M28 8v9"/>',
        QStyle.SP_BrowserReload:'<path d="M38 18A16 16 0 1 0 39 32" fill="none" stroke="url(#a)" stroke-width="6"/><path d="M39 6v15H25z"/>',
        QStyle.SP_ArrowBack:'<path d="M21 8 5 24l16 16V29h21V19H21z"/>',
        QStyle.SP_FileDialogDetailedView:'<path d="M10 5h24l6 7v32H10z"/><path d="M16 15h17M16 23h17M16 31h17" stroke="#eaffff" stroke-width="3"/>',
        QStyle.SP_FileDialogContentsView:'<path d="m24 5 17 10v19L24 44 7 34V15z"/><path d="m7 15 17 10 17-10M24 25v19M7 34l17-19 17 19" fill="none" stroke="#d8ffff"/>',
        QStyle.SP_ComputerIcon:'<path d="m24 5 18 10-5 22-20 6L6 24z"/><path d="m24 5-7 38M6 24l36-9M6 24l31 13M24 5l13 32" fill="none" stroke="#ccffff"/>',
        QStyle.SP_FileDialogInfoView:'<path d="M7 5v37h36" fill="none" stroke-width="3"/><path d="m10 33 9-11 9 5 12-17" fill="none" stroke="url(#a)" stroke-width="5"/><circle cx="28" cy="27" r="4" fill="#efba5c"/>',
        QStyle.SP_DriveHDIcon:'<path d="M7 9h24v29H7z"/><path d="M17 18h25v25H17z" fill="url(#a)"/><path d="m22 26 5-5 5 5m-5-5v15" fill="none" stroke="#eaffff" stroke-width="3"/>',
        QStyle.SP_TitleBarMaxButton:'<path d="M6 18V7h12m12 0h12v11m0 12v12H30m-12 0H6V30" fill="none" stroke-width="4"/><path d="m24 14 10 6v12l-10 6-10-6V20z"/>',
        QStyle.SP_DesktopIcon:'<path d="M6 13h10l4-6h11l4 6h9v27H6z"/><circle cx="25" cy="26" r="10" fill="#d8f4ff"/><circle cx="25" cy="26" r="6" fill="#267ba2"/>',
        QStyle.SP_FileDialogListView:'<path d="m24 5 17 10v19L24 44 7 34V15zM7 15l17 10 17-10M24 25v19M7 34l17-19 17 19" fill="none" stroke-width="2.5"/>',
    }
    glyph=shapes.get(kind,'<path d="m24 6 17 28H7z"/>')
    svg=f'''<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48"><defs>
    <linearGradient id="g" x2="0" y2="1"><stop stop-color="#a9e5fa"/><stop offset=".45" stop-color="#479ecb"/><stop offset=".5" stop-color="#2379b0"/><stop offset="1" stop-color="#326ba0"/></linearGradient>
    <linearGradient id="a" x2="0" y2="1"><stop stop-color="#a3e5bd"/><stop offset="1" stop-color="#389c84"/></linearGradient></defs>
    <g transform="translate(0 1)" stroke="#366581" stroke-width="1.2" stroke-linejoin="round" fill="url(#g)">{glyph}</g></svg>'''
    pixmap=QPixmap(96,96);pixmap.fill(Qt.transparent);painter=QPainter(pixmap);QSvgRenderer(QByteArray(svg.encode())).render(painter);painter.end()
    return QIcon(pixmap)
